"""Find the tests that cannot serve as an oracle.

A test that passes and fails on the same tree is not evidence. Run the
selection several times, keep whatever disagreed with itself, and write
those names into the policy so the suppression is declared rather than
discovered at the worst moment.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def scan(runner, selectors: list[str], rounds: int = 3) -> tuple[list[str], dict]:
    """Returns (flaky test ids, per-test outcome counts)."""
    seen: dict[str, set[str]] = defaultdict(set)
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for _ in range(rounds):
        result = runner.run_detailed(selectors)
        if not result.ran:
            raise SystemExit(f"cannot scan: {result.reason}")
        for case in result.cases:
            if case.status == "skipped":
                continue
            seen[case.id].add(case.status)
            counts[case.id][case.status] += 1

    flaky = sorted(tid for tid, statuses in seen.items() if len(statuses) > 1)
    return flaky, {k: dict(v) for k, v in counts.items()}


def write_to_policy(flaky: list[str], policy_path: str | Path = "policy.json") -> int:
    path = Path(policy_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    existing = set(data.get("quarantined_tests", []))
    added = [t for t in flaky if t not in existing]
    data["quarantined_tests"] = sorted(existing | set(flaky))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(added)
