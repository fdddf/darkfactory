"""darkfactory - run the line, replay a decision, verify the trail."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .audit import AuditLog
from .blackbox import get as get_fixer
from .blackbox.fixture import FixtureFixer
from .deploy import StubDeployer
from .enrich import NullEnricher, TavilyEnricher
from .inspection import NemotronJudge, StubJudge
from .oracle import StubTestRunner
from .runners import PhpUnitRunner
from .pipeline import Line
from .platform import load_env_file
from .policy import Policy
from .precheck import StubTestGenerator
from .schema import BugReport, Decision

GREEN, RED, YELLOW, DIM, BOLD, OFF = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"
)
COLOUR = {"allow": GREEN, "reject": RED, "escalate": YELLOW, "researched": DIM}


def _judge_name(choice: str) -> str:
    """"auto" means: use the real model when a key is actually present."""
    if choice != "auto":
        return choice
    import os
    return "nemotron" if os.environ.get("NEBIUS_API_KEY") else "stub"


def _enrich_name(choice: str) -> str:
    if choice != "auto":
        return choice
    import os
    return "tavily" if os.environ.get("TAVILY_API_KEY") else "none"


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_line(fx: dict, args) -> tuple[Line, BugReport]:
    bug = BugReport(**fx["bug"])
    policy = Policy.load(args.policy)
    judge = StubJudge() if _judge_name(args.judge) == "stub" else NemotronJudge()

    if args.runner == "phpunit":
        runner = PhpUnitRunner(args.repo)
        ok, why = runner.availability()
        if not ok:
            raise SystemExit(f"phpunit runner unavailable: {why}")
    else:
        runner = StubTestRunner(fx.get("oracle", {}))

    if args.fixer == "fixture":
        fixer = FixtureFixer(Path(args.fixtures) / fx["patch"]) if fx.get("patch") else None
    else:
        fixer = get_fixer(args.fixer)

    line = Line(
        policy=policy,
        audit=AuditLog(args.audit),
        generator=StubTestGenerator(fx.get("precheck", {})),
        fixer=fixer,
        runner=runner,
        judge=judge,
        deployer=StubDeployer(slo_breach=fx.get("deploy", {}).get("slo_breach", False)),
        enricher=TavilyEnricher() if _enrich_name(args.enrich) == "tavily" else NullEnricher(),
        repo=args.repo,
    )
    return line, bug


def cmd_run(args) -> int:
    paths = sorted(Path(args.fixtures).glob("*.json")) if args.all else [Path(args.bug)]
    worst = 0
    for p in paths:
        fx = _load_fixture(p)
        line, bug = _build_line(fx, args)
        print(f"\n{BOLD}▶ {bug.id}  {bug.title}{OFF}")
        print(f"{DIM}  {bug.source}{OFF}")
        outcome = line.run(bug)
        c = COLOUR[str(outcome.decision)]
        print(f"  {c}{BOLD}{str(outcome.decision).upper()}{OFF} at {outcome.stopped_at}"
              f" — {outcome.reason}")
        if outcome.escalated_to_human:
            print(f"  {DIM}handed to a human; nothing shipped{OFF}")
            worst = max(worst, 1)
    print(f"\n{DIM}audit trail: {args.audit}{OFF}")
    return 0 if not args.strict else worst


def cmd_verify(args) -> int:
    ok, problems = AuditLog(args.audit).verify()
    if ok:
        print(f"{GREEN}chain intact{OFF} — every entry hashes to the one after it")
        return 0
    print(f"{RED}chain broken{OFF}")
    for p in problems:
        print(f"  {RED}✗{OFF} {p}")
    return 1


def cmd_replay(args) -> int:
    entries = AuditLog(args.audit).for_bug(args.bug_id)
    if not entries:
        print(f"no entries for {args.bug_id}")
        return 1
    print(f"{BOLD}{args.bug_id}{OFF}")
    for e in entries:
        ts = datetime.fromtimestamp(e.ts).strftime("%H:%M:%S")
        c = COLOUR.get(e.decision, DIM)
        print(f"  {DIM}{ts}{OFF}  {c}{e.decision:<9}{OFF} {e.stage:<11} {e.summary}")
        if args.verbose and e.payload:
            for line in json.dumps(e.payload, indent=2, ensure_ascii=False).splitlines():
                print(f"    {DIM}{line}{OFF}")
    print(f"\n  {DIM}head hash {entries[-1].entry_hash[:16]}…{OFF}")
    return 0


def cmd_quarantine(args) -> int:
    from . import quarantine
    from .runners import PhpUnitRunner

    runner = PhpUnitRunner(args.repo)
    ok, why = runner.availability()
    if not ok:
        print(f"{RED}cannot scan{OFF}: {why}")
        return 1

    print(f"{DIM}running {len(args.selectors)} selector(s) x {args.rounds}…{OFF}")
    flaky, counts = quarantine.scan(runner, args.selectors, args.rounds)

    if not flaky:
        print(f"{GREEN}no flaky tests{OFF} across {args.rounds} rounds")
        return 0

    print(f"{YELLOW}{len(flaky)} test(s) disagreed with themselves:{OFF}")
    for tid in flaky:
        print(f"  {YELLOW}~{OFF} {tid}  {DIM}{counts[tid]}{OFF}")

    if args.write:
        added = quarantine.write_to_policy(flaky, args.policy)
        print(f"\n{DIM}added {added} to quarantined_tests in {args.policy}{OFF}")
    else:
        print(f"\n{DIM}re-run with --write to record these in {args.policy}{OFF}")
    return 0


def cmd_seed(args) -> int:
    """Turn real WordPress fix commits into bugs we can run the line on."""
    from . import seed as seeding
    from .runners import PhpUnitRunner

    repo = Path(args.repo)
    runner = PhpUnitRunner(repo, timeout=args.timeout)
    ok, why = runner.availability()
    if not ok:
        print(f"{RED}cannot seed{OFF}: {why}")
        return 1

    protected = [r["glob"] for r in Policy.load(args.policy)["protected_paths"]]
    def usable(c):
        return not any(f.removeprefix("src/") == g for f in c.src_files for g in protected)

    seeding.restore(repo)
    cands = [c for c in seeding.find_candidates(repo, limit=args.history) if usable(c)]
    print(f"{DIM}{len(cands)} candidate commit(s); verifying…{OFF}\n")

    made = 0
    for cand in cands[: args.scan]:
        if made >= args.count:
            break
        try:
            result = seeding.build_fixture(cand, repo, runner)
        except Exception as exc:
            result = {"ok": False, "why": f"{type(exc).__name__}: {exc}"}
        seeding.restore(repo)

        if not result["ok"]:
            print(f"  {DIM}skip {cand.sha[:10]} {result['why'][:70]}{OFF}")
            continue

        made += 1
        name = f"real_{cand.sha[:8]}"
        path = seeding.write_fixture(result, Path(args.out), name)
        print(f"  {GREEN}✓{OFF} {path.name}  {BOLD}{cand.subject[:54]}{OFF}")
        print(f"    {DIM}{cand.src_files[0]}  red: {result['red_tests'][0][:70]}{OFF}")

    print(f"\n{made} fixture(s) written to {args.out}/")
    return 0 if made else 1


def cmd_reset(args) -> int:
    """Clear the trail and scan history. Never touches credentials."""
    from .platform import Store

    Path(args.audit).unlink(missing_ok=True)
    store = Store()
    store.reset_runs()
    kept = sum(len(v) for v in store.overrides.values())
    print(f"{GREEN}reset{OFF} — audit trail and scan history cleared")
    print(f"{DIM}kept {len(store.repos)} repositor(y|ies) and {kept} stored credential(s){OFF}")
    return 0


def cmd_serve(args) -> int:
    from .server import serve
    return serve(args)


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    ap = argparse.ArgumentParser(prog="darkfactory", description=__doc__)
    ap.add_argument("--audit", default="audit/trail.jsonl")
    ap.add_argument("--policy", default="policy.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run one bug, or all of them, through the line")
    r.add_argument("bug", nargs="?", help="path to a fixture json")
    r.add_argument("--all", action="store_true")
    r.add_argument("--fixtures", default="fixtures")
    r.add_argument("--fixer", default="fixture", choices=["fixture", "devin", "tokenfactory"])
    r.add_argument("--judge", default="auto", choices=["auto", "stub", "nemotron"])
    r.add_argument("--runner", default="stub", choices=["stub", "phpunit"])
    r.add_argument("--enrich", default="auto", choices=["auto", "none", "tavily"],
                   help="research escalations with Tavily and cite the sources")
    r.add_argument("--repo", default="wp", help="wordpress-develop checkout")
    r.add_argument("--strict", action="store_true", help="non-zero exit if anything escalated")
    r.set_defaults(func=cmd_run)

    v = sub.add_parser("verify", help="check the hash chain")
    v.set_defaults(func=cmd_verify)

    p = sub.add_parser("replay", help="show every decision taken for one bug")
    p.add_argument("bug_id")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_replay)

    rs = sub.add_parser("reset", help="clear the trail and scans, keep repos and keys")
    rs.set_defaults(func=cmd_reset)

    sv = sub.add_parser("serve", help="the platform: repositories, scans, reports")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8800)
    sv.add_argument("--fixtures", default="fixtures")
    sv.add_argument("--repo", default="wp")
    sv.add_argument("--runner", default="stub", choices=["stub", "phpunit"])
    sv.add_argument("--judge", default="auto", choices=["auto", "stub", "nemotron"])
    sv.add_argument("--enrich", default="auto", choices=["auto", "none", "tavily"])
    sv.set_defaults(func=cmd_serve)

    sd = sub.add_parser("seed", help="make bugs by reverting real WordPress fixes")
    sd.add_argument("--repo", default="wp")
    sd.add_argument("--out", default="fixtures")
    sd.add_argument("--count", type=int, default=3, help="fixtures to produce")
    sd.add_argument("--scan", type=int, default=25, help="candidates to verify")
    sd.add_argument("--history", type=int, default=900)
    sd.add_argument("--timeout", type=int, default=240)
    sd.set_defaults(func=cmd_seed)

    q = sub.add_parser("quarantine", help="find tests that cannot serve as an oracle")
    q.add_argument("selectors", nargs="+")
    q.add_argument("--repo", default="wp")
    q.add_argument("--rounds", type=int, default=3)
    q.add_argument("--write", action="store_true")
    q.set_defaults(func=cmd_quarantine)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
