"""Pre-check: the gate that decides whether the black box runs at all.

"Trivial" has one operational meaning here: we can generate a test that
reproduces the bug. Four gates, all must pass. Three attempts, then the bug
goes to a person and the box never starts.

Gate 4 is the one worth defending in review: a test that errors out has not
reproduced anything. Only an assertion failure is evidence of the bug.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .schema import BugReport, Decision, GateResult, PrecheckResult

MAX_ATTEMPTS = 3

# A test that dies on a parse error or a missing class is not a reproduction.
_FATAL = re.compile(r"(Fatal error|Class .* not found|Error: |Parse error)", re.I)
_ASSERTION = re.compile(r"(Failed asserting|AssertionFailedError|FAILURES!)", re.I)


def gate_syntax(test_path: Path) -> GateResult:
    if not os.environ.get("DF_REAL_PHP"):
        return GateResult("syntax", True, "skipped (no PHP toolchain in stub mode)")
    proc = subprocess.run(["php", "-l", str(test_path)], capture_output=True, text=True)
    return GateResult("syntax", proc.returncode == 0, proc.stdout.strip()[:200])


def gate_runs(output: str, exit_code: int) -> GateResult:
    ok = exit_code != 255 and "Cannot open file" not in output
    return GateResult("runs", ok, "PHPUnit loaded and executed the test")


def gate_is_red(output: str, exit_code: int) -> GateResult:
    ok = exit_code != 0
    return GateResult(
        "is_red", ok,
        "test fails against the unpatched tree" if ok
        else "test passes already, so it does not reproduce the bug",
    )


def gate_red_for_the_right_reason(output: str) -> GateResult:
    """An assertion failure is evidence. A fatal error is noise."""
    if _FATAL.search(output) and not _ASSERTION.search(output):
        return GateResult("red_for_right_reason", False,
                          "test errored instead of failing an assertion")
    return GateResult("red_for_right_reason", bool(_ASSERTION.search(output)),
                      "failure is an assertion failure")


class StubTestGenerator:
    """Offline stand-in. Replays what a fixture says happened.

    Replace with the Token Factory generator: feed it a sibling test file as
    a template, the source of the changed function, and the WP factory
    cheatsheet. Do not let it write a WP_UnitTestCase from nothing.
    """

    def __init__(self, scripted: dict) -> None:
        self.scripted = scripted

    def attempt(self, bug: BugReport, n: int) -> tuple[str, int, str]:
        """Returns (phpunit_output, exit_code, test_path)."""
        runs = self.scripted.get("attempts", [])
        if n < len(runs):
            r = runs[n]
            return r["output"], r["exit_code"], r.get("test_file", "")
        return "No tests executed.", 255, ""


def run(bug: BugReport, generator, repo: str | Path = ".") -> PrecheckResult:
    """`repo` is the checkout the generated test paths are relative to."""
    root = Path(repo)
    gates: list[GateResult] = []

    for attempt in range(MAX_ATTEMPTS):
        output, code, test_file = generator.attempt(bug, attempt)
        gates = [
            gate_syntax(root / test_file) if test_file else GateResult("syntax", False, "no test produced"),
            gate_runs(output, code),
            gate_is_red(output, code),
            gate_red_for_the_right_reason(output),
        ]
        if all(g.passed for g in gates):
            return PrecheckResult(
                decision=Decision.ALLOW,
                reproduced=True,
                attempts=attempt + 1,
                gates=gates,
                test_file=test_file,
                test_name=Path(test_file).stem if test_file else None,
                reason="bug reproduced by a generated test",
            )

    failed = [g.name for g in gates if not g.passed]
    return PrecheckResult(
        decision=Decision.ESCALATE,
        reproduced=False,
        attempts=MAX_ATTEMPTS,
        gates=gates,
        reason=f"could not reproduce in {MAX_ATTEMPTS} attempts; gates failed: {', '.join(failed)}",
    )
