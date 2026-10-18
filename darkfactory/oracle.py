"""Oracle: behavioural evidence that the bug is gone and nothing else broke.

Three rules decide this, and the audit records all three:

  1. The reproducing test goes red to green.
  2. The tests covering the changed code stay green.
  3. The patch does not touch the tests. An oracle the fixer can edit is
     not an oracle.

We do not run twenty thousand tests. We run the ones that cover the change,
and the trail says how that set was chosen - scoping the suite is a decision
the line justifies, not a shortcut around one.

A test that is not stable cannot serve as evidence either way, so known
flaky tests are quarantined by name in the policy and their results are
recorded as suppressed rather than silently dropped.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path

from .policy import Policy
from .schema import Decision, OracleResult, Patch
from .inspection.diffparse import normalize, parse

# WordPress mirrors its source layout under tests/phpunit/tests/, which is
# why the cheap mapping is a real one and not a guess.
SOURCE_ROOTS = ("wp-includes", "wp-admin")
# Always runs: cheap, stable, and catches a tree that will not boot at all.
SMOKE = "tests/phpunit/tests/basic.php"
COVERAGE_MAP = "coverage-map.json"


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------


def _candidates_from_coverage(changed: list[str], repo: Path) -> list[str] | None:
    """Exact mapping produced by a pcov baseline run: source file -> tests.

    Preferred when present. Same interface as the heuristic, better evidence.
    """
    path = repo / COVERAGE_MAP
    if not path.exists():
        return None
    try:
        mapping = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    hits: set[str] = set()
    for src in changed:
        hits.update(mapping.get(src, []))
    return sorted(hits)


def _candidates_from_paths(changed: list[str]) -> list[str]:
    """WordPress mirrors its source layout under tests/phpunit/tests/.

    wp-includes/formatting.php      -> tests/.../formatting[.php]
    wp-admin/includes/misc.php      -> tests/.../admin/includesMisc.php
    """
    out: set[str] = {SMOKE}
    for raw in changed:
        p = Path(normalize(raw))
        if not p.parts or p.parts[0] not in SOURCE_ROOTS:
            continue
        stem = p.stem
        out.add(f"tests/phpunit/tests/{stem}")
        out.add(f"tests/phpunit/tests/{stem}.php")
        if p.parts[0] == "wp-admin":
            if len(p.parts) > 2 and p.parts[1] == "includes":
                out.add(f"tests/phpunit/tests/admin/includes{stem[:1].upper()}{stem[1:]}.php")
            out.add(f"tests/phpunit/tests/admin/{stem}.php")
            out.add("tests/phpunit/tests/admin")
    return sorted(out)


def select_tests(patch: Patch, repo: Path) -> tuple[list[str], str, list[str]]:
    """Returns (selectors that exist, strategy, candidates that did not exist)."""
    changed = [f.path for f in parse(patch.diff).files]

    candidates = _candidates_from_coverage(changed, repo)
    strategy = "coverage-map-v1"
    if candidates is None:
        candidates, strategy = _candidates_from_paths(changed), "path-heuristic-v1"

    resolved, missing = [], []
    for c in candidates:
        (resolved if (repo / c).exists() else missing).append(c)

    return resolved, strategy, missing


# --------------------------------------------------------------------------
# Quarantine
# --------------------------------------------------------------------------


def is_quarantined(test_id: str, policy: Policy) -> bool:
    return any(
        fnmatch.fnmatch(test_id, pattern)
        for pattern in policy.get("quarantined_tests", [])
    )


def partition_failures(failed_ids: list[str], policy: Policy) -> tuple[list[str], list[str]]:
    """Split failures into ones that count and ones the policy suppresses."""
    real, suppressed = [], []
    for tid in failed_ids:
        (suppressed if is_quarantined(tid, policy) else real).append(tid)
    return real, suppressed


# --------------------------------------------------------------------------
# Anti-tamper
# --------------------------------------------------------------------------


def _touches_tests(patch: Patch, policy: Policy) -> bool:
    for f in parse(patch.diff).files:
        path = normalize(f.path)
        for glob in policy["test_paths"]:
            if fnmatch.fnmatch(path, glob) or path.startswith("tests/"):
                return True
    return False


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------


class StubTestRunner:
    """Replays a scripted result so the line runs without PHP."""

    name = "stub"

    def __init__(self, scripted: dict) -> None:
        self.scripted = scripted

    def run(self, repo: str, selectors: list[str]) -> tuple[bool, str]:
        return self.scripted.get("green", True), self.scripted.get("output", "OK")

    def run_detailed(self, selectors: list[str]):
        from .runners.phpunit import SuiteResult

        green = self.scripted.get("green", True)
        return SuiteResult(
            ok=green, ran=True, tests=self.scripted.get("tests", 1),
            failures=0 if green else 1,
            reason=self.scripted.get("output", "OK"),
        )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def run(
    patch: Patch,
    policy: Policy,
    runner,
    repo: str | Path = ".",
    repro_test: str | None = None,
) -> OracleResult:
    repo = Path(repo)
    runner_name = getattr(runner, "name", type(runner).__name__)

    untouched = not _touches_tests(patch, policy)
    selected, strategy, missing = select_tests(patch, repo)
    quarantine_patterns = policy.get("quarantined_tests", [])

    def _result(decision, reason, repro_ok=False, reg_ok=False, **extra) -> OracleResult:
        return OracleResult(
            decision=decision,
            repro_red_to_green=repro_ok,
            regression_green=reg_ok,
            test_files_untouched=untouched,
            tests_selected=selected,
            selection_strategy=strategy,
            quarantined=quarantine_patterns,
            reason=reason,
            runner=runner_name,
            **extra,
        )

    # Rule 3 first: it costs nothing and it is the cheapest way to be cheated.
    if not untouched:
        return _result(Decision.REJECT, "the patch modifies test files")

    detailed = hasattr(runner, "run_detailed")

    # Rule 1: the reproducing test must now pass.
    repro_selectors = [repro_test] if repro_test else []
    repro_suppressed: list[str] = []
    if repro_selectors:
        if detailed:
            r = runner.run_detailed(repro_selectors)
            # Quarantine cuts both ways. A test that cannot be trusted to
            # fail cannot be trusted to pass either, so it is excluded here
            # too rather than being allowed to veto the fix.
            real, repro_suppressed = partition_failures(r.failed_ids, policy)
            repro_ok = r.ran and not real
            repro_note = r.summary()
        else:
            repro_ok, repro_note = runner.run(str(repo), repro_selectors)
    else:
        repro_ok, repro_note = False, "no reproducing test was carried forward from pre-check"

    if not repro_ok:
        return _result(Decision.REJECT, f"the reproducing test is not green: {repro_note}")

    # Rule 2: the covering tests must hold.
    if not detailed:
        reg_ok, note = runner.run(str(repo), selected)
        return _result(
            Decision.ALLOW if reg_ok else Decision.REJECT,
            "repro went red to green and regression held" if reg_ok
            else f"the selected regression tests are not green: {note}",
            repro_ok=True, reg_ok=reg_ok, runner_summary=note,
        )

    suite = runner.run_detailed(selected)

    if not suite.ran:
        # No evidence is not the same as good evidence.
        return _result(
            Decision.ESCALATE,
            f"regression suite produced no evidence: {suite.reason}"
            + (f" (unresolved selectors: {', '.join(missing)})" if missing else ""),
            repro_ok=True, runner_summary=suite.summary(),
        )

    real, suppressed = partition_failures(suite.failed_ids, policy)
    reg_ok = not real

    if reg_ok:
        reason = "repro went red to green and regression held"
        if suppressed:
            reason += f"; {len(suppressed)} quarantined failure(s) suppressed by policy"
    else:
        reason = f"the selected regression tests are not green: {', '.join(real[:5])}"

    return _result(
        Decision.ALLOW if reg_ok else Decision.REJECT,
        reason,
        repro_ok=True,
        reg_ok=reg_ok,
        tests_run=suite.tests,
        failures=real,
        quarantine_suppressed=list(dict.fromkeys(repro_suppressed + suppressed)),
        runner_summary=suite.summary(),
    )
