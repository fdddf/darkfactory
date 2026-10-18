"""Platform state: repositories, scans, integrations.

The console showed one run of the line. This is the surface around it -
which repositories are connected, what scans have happened, which services
are wired up, and what each scan concluded.

State lives in one JSON file. A hackathon does not need Postgres, and a
file keeps the whole platform inspectable with `cat`.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STATE_FILE = Path(os.environ.get("DF_STATE", "state/platform.json"))
ENV_FILE = Path(os.environ.get("DF_ENV", ".env"))


def load_env_file(path: Path = ENV_FILE) -> int:
    """Read KEY=value lines into the environment.

    Credentials belong somewhere no command can delete. The console writes
    to platform.json for convenience, but .env is the durable copy and is
    read first on every start.
    """
    if not path.exists():
        return 0
    n = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip().strip("\"'")
        if name and value and not os.environ.get(name):
            os.environ[name] = value
            n += 1
    return n


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass
class Repository:
    id: str
    name: str
    url: str
    path: str
    provider: str = "local"
    default_branch: str = "trunk"
    connected_at: float = field(default_factory=time.time)
    auto_scan: bool = False
    # Which commit the last scan covered, so a watcher knows what is new.
    last_scanned_sha: str = ""
    last_scan_id: str = ""
    seeded_bugs: int = 0

    @property
    def short(self) -> str:
        return self.name.split("/")[-1]


@dataclass
class Scan:
    id: str
    repo_id: str
    trigger: str                 # manual | auto | webhook
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    status: str = "running"      # running | done | failed
    shipped: int = 0
    refused: int = 0
    escalated: int = 0
    bugs: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    chain_ok: bool = True
    runner: str = "stub"
    note: str = ""

    @property
    def duration(self) -> float:
        return (self.finished_at or time.time()) - self.started_at


DEFAULT_INTEGRATIONS: dict[str, dict[str, Any]] = {
    "token_factory": {
        "label": "Nebius Token Factory",
        "role": "All model inference. OpenAI-compatible.",
        "env": ["NEBIUS_API_KEY", "MODEL_INSPECTOR"],
        "endpoint": "https://api.tokenfactory.nebius.com/v1/",
        "docs": "https://docs.tokenfactory.nebius.com",
        "required": True,
    },
    "nemotron": {
        "label": "NVIDIA Nemotron",
        "role": "Semantic half of diff inspection.",
        "env": ["MODEL_INSPECTOR"],
        "endpoint": "via Token Factory",
        "docs": "https://build.nvidia.com",
        "required": False,
    },
    "sandboxes": {
        "label": "Nebius Sandboxes",
        "role": "VM isolation for the black box fixer.",
        "env": ["NEBIUS_PROJECT_ID"],
        "endpoint": "https://api.tokenfactory.nebius.com/sandboxes",
        "docs": "https://docs.tokenfactory.nebius.com/sandboxes/overview",
        "required": False,
    },
    "tavily": {
        "label": "Tavily",
        "role": "Advisory research attached to every escalation.",
        "env": ["TAVILY_API_KEY"],
        "endpoint": "https://api.tavily.com/search",
        "docs": "https://docs.tavily.com",
        "required": False,
    },
    "n8n": {
        "label": "n8n",
        "role": "Pipeline orchestration with an error branch per gate.",
        "env": ["N8N_API_URL", "N8N_API_KEY"],
        "endpoint": "http://localhost:5678",
        "docs": "https://docs.n8n.io",
        "required": False,
    },
    "devin": {
        "label": "Devin",
        "role": "A black box implementation. Parallel sessions per bug.",
        "env": ["DEVIN_API_KEY"],
        "endpoint": "https://api.devin.ai",
        "docs": "https://docs.devin.ai",
        "required": False,
    },
}


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------


class Store:
    """Everything the platform knows, in one file, guarded by one lock."""

    def __init__(self, path: Path = STATE_FILE) -> None:
        self.path = Path(path)
        self.lock = threading.RLock()
        self.repos: dict[str, Repository] = {}
        self.scans: dict[str, Scan] = {}
        self.overrides: dict[str, dict[str, str]] = {}
        load_env_file()
        self._load()

    # -- persistence ------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.repos = {k: Repository(**v) for k, v in raw.get("repos", {}).items()}
        self.scans = {k: Scan(**v) for k, v in raw.get("scans", {}).items()}
        self.overrides = raw.get("overrides", {})

        # Put stored secrets back into the environment. Without this a
        # restart leaves the console reporting "connected" from the saved
        # state while the layers that read os.environ quietly find nothing -
        # the worst kind of failure, because it looks like success.
        for group in self.overrides.values():
            for name, value in group.items():
                if value and not os.environ.get(name):
                    os.environ[name] = value

    def save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({
                "repos": {k: asdict(v) for k, v in self.repos.items()},
                "scans": {k: asdict(v) for k, v in self.scans.items()},
                "overrides": self.overrides,
            }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    # -- repositories -----------------------------------------------------

    def connect_repo(self, url: str, path: str = "", name: str = "") -> Repository:
        """Attach a checkout. A local path is used as-is; a URL is cloned."""
        path = path.strip()
        url = url.strip()

        if not path:
            slug = url.rstrip("/").removesuffix(".git").split("/")[-1] or "repo"
            path = f"repos/{slug}"

        target = Path(path)
        if not target.exists():
            if not url:
                raise ValueError(f"{path} does not exist and no clone URL was given")
            target.parent.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run(
                ["git", "clone", "--depth", "50", url, str(target)],
                capture_output=True, text=True, timeout=600,
            )
            if proc.returncode != 0:
                raise ValueError(f"clone failed: {proc.stderr.strip()[:300]}")

        if not name:
            name = url.rstrip("/").removesuffix(".git").split("/")[-2:] if "/" in url else []
            name = "/".join(name) if name else target.name

        repo = Repository(
            id=uuid.uuid4().hex[:8],
            name=name,
            url=url or f"file://{target.resolve()}",
            path=str(target),
            provider="github" if "github.com" in url else "local",
            default_branch=_branch(target),
        )
        with self.lock:
            self.repos[repo.id] = repo
            self.save()
        return repo

    def forget_repo(self, repo_id: str) -> None:
        with self.lock:
            self.repos.pop(repo_id, None)
            self.save()

    # -- scans ------------------------------------------------------------

    def open_scan(self, repo_id: str, trigger: str, runner: str) -> Scan:
        scan = Scan(id=uuid.uuid4().hex[:8], repo_id=repo_id, trigger=trigger,
                    runner=runner)
        with self.lock:
            self.scans[scan.id] = scan
            self.save()
        return scan

    def close_scan(self, scan: Scan, chain_ok: bool) -> None:
        with self.lock:
            scan.finished_at = time.time()
            scan.status = "done"
            scan.chain_ok = chain_ok
            repo = self.repos.get(scan.repo_id)
            if repo:
                repo.last_scan_id = scan.id
                repo.last_scanned_sha = _head(Path(repo.path))
            self.save()

    def reset_runs(self) -> None:
        """Clear scan history for a clean demo. Repositories and credentials
        stay: wiping those is not what anyone means by "reset"."""
        with self.lock:
            self.scans.clear()
            for repo in self.repos.values():
                repo.last_scan_id = ""
            self.save()

    def recent_scans(self, limit: int = 20) -> list[Scan]:
        return sorted(self.scans.values(), key=lambda s: s.started_at, reverse=True)[:limit]

    # -- integrations -----------------------------------------------------

    def integrations(self) -> list[dict]:
        out = []
        for key, spec in DEFAULT_INTEGRATIONS.items():
            over = self.overrides.get(key, {})
            present = []
            for var in spec["env"]:
                value = over.get(var) or os.environ.get(var, "")
                present.append({
                    "name": var,
                    "set": bool(value),
                    "source": "console" if over.get(var) else ("env" if value else ""),
                    "hint": _mask(value),
                })
            out.append({
                "key": key, **{k: v for k, v in spec.items() if k != "env"},
                "vars": present,
                "connected": all(v["set"] for v in present) if present else False,
            })
        return out

    def set_secret(self, key: str, var: str, value: str) -> None:
        with self.lock:
            self.overrides.setdefault(key, {})[var] = value
            # Make it live for this process so a scan picks it up at once.
            if value:
                os.environ[var] = value
            self.save()


# --------------------------------------------------------------------------


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-3:]}"


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                              text=True, timeout=20)
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")[:10]


def _branch(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "trunk"
