"""Platform HTTP API.

Serves the React build in production and proxies nothing in development -
Vite proxies /api here instead. Standard library only, so the whole thing
starts on a Nebius VM with python3 and no wheel to compile.
"""

from __future__ import annotations

import json
import mimetypes
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .audit import AuditLog
from .blackbox.fixture import FixtureFixer
from .deploy import StubDeployer
from .enrich import NullEnricher, TavilyEnricher
from .cli import _enrich_name, _judge_name
from .inspection import NemotronJudge, StubJudge
from .oracle import StubTestRunner
from .pipeline import Line
from .platform import Store
from .policy import Policy
from .precheck import StubTestGenerator
from .runners import PhpUnitRunner
from .schema import BugReport, Stage, to_jsonable

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"


class Platform:
    """One process: the store, the event bus, and whatever scan is running."""

    def __init__(self, args) -> None:
        self.args = args
        self.store = Store()
        self.lock = threading.Lock()
        self.subscribers: list[queue.Queue] = []
        self.history: list[dict] = []
        self.running: str | None = None       # scan id
        self.patches: dict[str, dict] = {}
        self.findings: dict[str, list] = {}
        self.watcher: threading.Thread | None = None

    # -- events -----------------------------------------------------------

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self.lock:
            for event in self.history:
                q.put(event)
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def emit(self, kind: str, data: dict) -> None:
        event = {"kind": kind, "ts": time.time(), **to_jsonable(data)}
        with self.lock:
            if kind == "scan_start":
                self.history.clear()
            self.history.append(event)
            del self.history[:-500]
            targets = list(self.subscribers)
        for q in targets:
            q.put(event)

    # -- fixtures ---------------------------------------------------------

    def fixture_files(self) -> list[Path]:
        return sorted(Path(self.args.fixtures).glob("*.json"))

    def bugs(self) -> list[dict]:
        out = []
        for path in self.fixture_files():
            fx = json.loads(path.read_text(encoding="utf-8"))
            bug = fx["bug"]
            out.append({
                "file": path.name, "id": bug["id"], "title": bug["title"],
                "source": bug.get("source", ""), "body": bug.get("body", ""),
                "seed": fx.get("seed", {}), "has_patch": bool(fx.get("patch")),
            })
        return out

    def _diff(self, fx: dict, key: str) -> str:
        rel = fx.get(key) or (fx.get("seed") or {}).get(key)
        if not rel:
            return ""
        p = Path(self.args.fixtures) / rel
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # -- scanning ---------------------------------------------------------

    def start_scan(self, repo_id: str, trigger: str = "manual",
                   runner: str | None = None, enrich: str | None = None) -> dict:
        with self.lock:
            if self.running:
                return {"error": "a scan is already running", "scan_id": self.running}

        repo = self.store.repos.get(repo_id)
        if repo is None:
            return {"error": "unknown repository"}

        runner = runner or self.args.runner
        enrich = enrich or self.args.enrich
        scan = self.store.open_scan(repo_id, trigger, runner)
        with self.lock:
            self.running = scan.id

        threading.Thread(target=self._scan_worker, args=(scan, repo, runner, enrich),
                         daemon=True).start()
        return {"scan_id": scan.id}

    def _scan_worker(self, scan, repo, runner_kind: str, enrich: str) -> None:
        try:
            audit = AuditLog(self.args.audit)
            policy = Policy.load(self.args.policy)
            judge = StubJudge() if _judge_name(self.args.judge) == "stub" else NemotronJudge()
            enricher = TavilyEnricher() if _enrich_name(enrich) == "tavily" else NullEnricher()

            self.emit("scan_start", {
                "scan_id": scan.id, "repo": repo.name, "repo_id": repo.id,
                "trigger": scan.trigger, "runner": runner_kind, "enrich": enrich,
                "policy": policy.summary(),
                "protected_paths": len(policy["protected_paths"]),
                "head": repo.last_scanned_sha or "-", "branch": repo.default_branch,
            })

            findings: list[dict] = []
            for path in self.fixture_files():
                fx = json.loads(path.read_text(encoding="utf-8"))
                bug = BugReport(**fx["bug"])
                scan.bugs.append(bug.id)

                runner = (PhpUnitRunner(repo.path) if runner_kind == "phpunit"
                          else StubTestRunner(fx.get("oracle", {})))

                fixer = None
                if fx.get("patch"):
                    fixer = FixtureFixer(Path(self.args.fixtures) / fx["patch"])
                    with self.lock:
                        self.patches[bug.id] = {
                            "proposed": self._diff(fx, "patch"),
                            "reference": self._diff(fx, "reference_fix"),
                            "regression": self._diff(fx, "regression_diff"),
                        }

                def observe(kind: str, data: dict, _bug=bug) -> None:
                    if kind == "stage_done" and data.get("stage") == "inspection":
                        detail = data.get("detail")
                        fs = (to_jsonable(detail).get("deterministic", {}).get("findings", [])
                              + to_jsonable(detail).get("semantic", {}).get("findings", []))
                        for f in fs:
                            f = {**f, "bug_id": _bug.id, "bug_title": _bug.title}
                            findings.append(f)
                        with self.lock:
                            self.findings[_bug.id] = fs
                    self.emit(kind, {**data, "scan_id": scan.id})

                outcome = Line(
                    policy=policy, audit=audit,
                    generator=StubTestGenerator(fx.get("precheck", {})),
                    fixer=fixer, runner=runner, judge=judge,
                    deployer=StubDeployer(
                        slo_breach=fx.get("deploy", {}).get("slo_breach", False)),
                    enricher=enricher, repo=repo.path, observer=observe,
                ).run(bug)

                if str(outcome.decision) == "allow":
                    scan.shipped += 1
                elif str(outcome.decision) == "reject":
                    scan.refused += 1
                else:
                    scan.escalated += 1

            scan.findings = findings
            ok, problems = audit.verify()
            self.store.close_scan(scan, ok)
            self.emit("scan_done", {
                "scan_id": scan.id, "chain_ok": ok, "problems": problems,
                "shipped": scan.shipped, "refused": scan.refused,
                "escalated": scan.escalated, "findings": len(findings),
                "duration": round(scan.duration, 1),
            })
        except Exception as exc:
            scan.status = "failed"
            scan.note = f"{type(exc).__name__}: {exc}"
            self.store.save()
            self.emit("scan_failed", {"scan_id": scan.id, "message": scan.note})
        finally:
            with self.lock:
                self.running = None

    # -- auto scan --------------------------------------------------------

    def start_watcher(self, interval: int = 20) -> None:
        """Poll connected repositories and scan when HEAD moves."""
        if self.watcher:
            return

        def work() -> None:
            while True:
                time.sleep(interval)
                for repo in list(self.store.repos.values()):
                    if not repo.auto_scan or self.running:
                        continue
                    from .platform import _head
                    head = _head(Path(repo.path))
                    if not head:
                        continue
                    if not repo.last_scanned_sha:
                        # First sighting is a baseline, not a change. Without
                        # this, turning auto scan on starts a scan at once and
                        # every restart starts another.
                        repo.last_scanned_sha = head
                        self.store.save()
                        continue
                    if head != repo.last_scanned_sha:
                        self.emit("auto_trigger", {
                            "repo": repo.name, "from": repo.last_scanned_sha,
                            "to": head,
                        })
                        self.start_scan(repo.id, trigger="auto")

        self.watcher = threading.Thread(target=work, daemon=True)
        self.watcher.start()


# --------------------------------------------------------------------------


def make_handler(pf: Platform):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a) -> None:
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload, code: int = 200) -> None:
            self._send(code, json.dumps(payload, ensure_ascii=False).encode(),
                       "application/json; charset=utf-8")

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        # -- GET ----------------------------------------------------------

        def do_GET(self) -> None:
            u = urlparse(self.path)
            q = parse_qs(u.query)
            r = u.path

            if r == "/api/overview":
                scans = pf.store.recent_scans(8)
                return self._json({
                    "repos": [vars(x) for x in pf.store.repos.values()],
                    "scans": [vars(s) for s in scans],
                    "running": pf.running,
                    "bugs": len(pf.fixture_files()),
                    "integrations": pf.store.integrations(),
                    "policy": Policy.load(pf.args.policy).summary(),
                    "defaults": {"runner": pf.args.runner, "judge": pf.args.judge,
                                 "enrich": pf.args.enrich},
                })

            if r == "/api/repos":
                return self._json([vars(x) for x in pf.store.repos.values()])

            if r == "/api/scans":
                return self._json([vars(s) for s in pf.store.recent_scans(50)])

            if r == "/api/scan":
                scan = pf.store.scans.get((q.get("id") or [""])[0])
                return self._json(vars(scan) if scan else {"error": "unknown scan"})

            if r == "/api/bugs":
                return self._json(pf.bugs())

            if r == "/api/findings":
                with pf.lock:
                    return self._json(pf.findings)

            if r == "/api/patch":
                with pf.lock:
                    return self._json(pf.patches.get((q.get("bug") or [""])[0], {}))

            if r == "/api/trail":
                log = AuditLog(pf.args.audit)
                ok, problems = log.verify()
                return self._json({"entries": [to_jsonable(e) for e in log.read()],
                                   "chain_ok": ok, "problems": problems})

            if r == "/api/integrations":
                return self._json(pf.store.integrations())

            if r == "/api/events":
                return self._events()

            if r == "/api/tamper":
                path = Path(pf.args.audit)
                if not path.exists():
                    return self._json({"ok": False, "why": "no trail yet"})
                text = path.read_text(encoding="utf-8")
                for needle in ("reject", "escalate"):
                    if f'"decision":"{needle}"' in text:
                        text = text.replace(f'"decision":"{needle}"', '"decision":"allow"', 1)
                        break
                else:
                    return self._json({"ok": False, "why": "nothing to flip"})
                path.write_text(text, encoding="utf-8")
                ok, problems = AuditLog(pf.args.audit).verify()
                return self._json({"ok": True, "chain_ok": ok, "problems": problems})

            return self._static(r)

        # -- POST ---------------------------------------------------------

        def do_POST(self) -> None:
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            r = u.path

            if r == "/api/repos":
                try:
                    repo = pf.store.connect_repo(
                        body.get("url", ""), body.get("path", ""), body.get("name", ""))
                except Exception as exc:
                    return self._json({"error": str(exc)}, 400)
                return self._json(vars(repo))

            if r == "/api/repo/auto":
                repo = pf.store.repos.get(body.get("id", ""))
                if not repo:
                    return self._json({"error": "unknown repository"}, 404)
                repo.auto_scan = bool(body.get("auto_scan"))
                pf.store.save()
                if repo.auto_scan:
                    pf.start_watcher()
                return self._json(vars(repo))

            if r == "/api/scan":
                return self._json(pf.start_scan(
                    body.get("repo_id", ""), body.get("trigger", "manual"),
                    body.get("runner"), body.get("enrich")))

            if r == "/api/integration":
                pf.store.set_secret(body.get("key", ""), body.get("var", ""),
                                    body.get("value", ""))
                return self._json({"integrations": pf.store.integrations()})

            if r == "/api/brief":
                findings = body.get("findings") or []
                if not findings:
                    return self._json({"briefs": []})
                from .schema import Finding, Severity
                objs = [Finding(rule=f.get("rule", ""),
                                severity=Severity(f.get("severity", "info")),
                                file=f.get("file", ""), line=int(f.get("line") or 0),
                                evidence=f.get("evidence", ""),
                                rationale=f.get("rationale", ""),
                                layer=f.get("layer", "")) for f in findings]
                return self._json({"briefs": to_jsonable(TavilyEnricher().brief(objs))})

            if r == "/api/decision":
                entry = AuditLog(pf.args.audit).append(
                    body.get("bug_id", "?"), Stage.OUTCOME,
                    body.get("decision", "reviewed"),
                    body.get("note") or "reviewed by a human",
                    {"actor": "human", "via": "console"})
                return self._json({"seq": entry.seq, "hash": entry.entry_hash})

            return self._json({"error": "not found"}, 404)

        def do_DELETE(self) -> None:
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/api/repos":
                pf.store.forget_repo((q.get("id") or [""])[0])
                return self._json({"ok": True})
            return self._json({"error": "not found"}, 404)

        # -- plumbing ------------------------------------------------------

        def _static(self, route: str) -> None:
            rel = route.lstrip("/") or "index.html"
            target = (DIST / rel).resolve()
            if str(target).startswith(str(DIST.resolve())) and target.is_file():
                ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if target.suffix in (".js", ".mjs"):
                    ctype = "text/javascript; charset=utf-8"
                return self._send(200, target.read_bytes(), ctype)
            # Client-side routing: unknown paths fall back to the SPA shell.
            index = DIST / "index.html"
            if index.is_file():
                return self._send(200, index.read_bytes(), "text/html; charset=utf-8")
            return self._json({"error": "build the frontend first: cd web && npm run build"}, 404)

        def _events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            q = pf.subscribe()
            try:
                while True:
                    try:
                        event = q.get(timeout=15)
                        self.wfile.write(
                            f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return
            finally:
                pf.unsubscribe(q)

    return Handler


class QuietServer(ThreadingHTTPServer):
    """A browser closing a keep-alive socket is not an error.

    Navigating away drops the event stream, and the stock handler prints a
    full traceback for every one of those. On a projector that reads as a
    crash, so connection teardown is swallowed and everything else still
    gets reported.
    """

    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)

def serve(args) -> int:
    pf = Platform(args)

    # A first run with nothing connected is a dead console, so adopt the
    # checkout the CLI already points at.
    if not pf.store.repos and Path(args.repo).exists():
        try:
            pf.store.connect_repo("", args.repo, name="WordPress/wordpress-develop")
        except Exception:
            pass
    pf.start_watcher()

    server = QuietServer((args.host, args.port), make_handler(pf))
    built = (DIST / "index.html").exists()
    print(f"  platform   http://{args.host}:{args.port}/"
          f"{'' if built else '   (run: cd web && npm run build)'}")
    print(f"  defaults   runner={args.runner} judge={args.judge} enrich={args.enrich}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0
