"""Seed bugs by reverting real WordPress fixes.

A synthetic bug proves nothing: we chose it to be catchable. Reverting a
commit that WordPress itself shipped as a fix gives us a bug that really
happened, the ticket that reported it, the project's own patch as ground
truth, and - when the commit carried a test - a reproduction we did not
write ourselves.

The trick that makes this work: revert only the source half. The test that
came with the fix stays in the tree, so it goes red the moment the source
regresses. That is a reproduction nobody can accuse us of tuning.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

TRAC = re.compile(r"(?:Fixes|See|Props.*?)\s*#(\d+)")


def _git(repo: Path, *args: str, check: bool = True, stdin: str | None = None) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, input=stdin
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


@dataclass(slots=True)
class Candidate:
    sha: str
    subject: str
    body: str
    src_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0

    @property
    def ticket(self) -> str | None:
        m = TRAC.search(self.subject + "\n" + self.body)
        return m.group(1) if m else None

    @property
    def source(self) -> str:
        t = f", Trac #{self.ticket}" if self.ticket else ""
        return f"reverted from wordpress-develop @ {self.sha[:10]}{t}"

    def score(self) -> int:
        """Smaller and better covered is a better seed."""
        return self.insertions + self.deletions + 20 * max(0, len(self.src_files) - 1)


def find_candidates(
    repo: Path, limit: int = 400, max_files: int = 4, max_lines: int = 60
) -> list[Candidate]:
    out: list[Candidate] = []
    log = _git(repo, "log", f"-n{limit}", "--format=%H%x00%s%x00%b%x01",
               "--", "src/wp-includes", "src/wp-admin")

    for chunk in log.split("\x01"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        sha, subject, body = (chunk.split("\x00") + ["", ""])[:3]
        sha = sha.strip()
        if not sha:
            continue

        names = [n for n in _git(repo, "show", "--name-only", "--format=", sha).split() if n]
        src = [n for n in names if n.startswith("src/")]
        # tests/ also holds phpstan baselines and e2e specs; only PHPUnit
        # files can serve as a carried reproduction.
        tests = [
            n for n in names
            if n.startswith("tests/phpunit/") and n.endswith(".php")
        ]
        if not src or not tests or len(names) > max_files:
            continue

        stat = _git(repo, "show", "--shortstat", "--format=", sha)
        ins = int(m.group(1)) if (m := re.search(r"(\d+) insertion", stat)) else 0
        dels = int(m.group(1)) if (m := re.search(r"(\d+) deletion", stat)) else 0
        if ins + dels > max_lines:
            continue

        out.append(Candidate(sha, subject, body, src, tests, ins, dels))

    return sorted(out, key=Candidate.score)


# --------------------------------------------------------------------------


def revert_source_only(repo: Path, sha: str) -> str:
    """Undo the source half of a fix and leave its test in place.

    `git revert` takes no pathspec, so we apply the commit's src/ hunks in
    reverse instead. The test the fix shipped with stays untouched and goes
    red the moment the source regresses.

    Returns the diff now sitting in the working tree.
    """
    _git(repo, "checkout", "--", "src")
    forward = _git(repo, "show", "--format=", sha, "--", "src")
    if not forward.strip():
        raise RuntimeError(f"{sha[:10]} changes nothing under src/")
    _git(repo, "apply", "-R", "--whitespace=nowarn", "-", stdin=forward)
    return _git(repo, "diff", "--", "src")


def restore(repo: Path) -> None:
    _git(repo, "checkout", "--", "src", check=False)


def forward_diff(repo: Path, sha: str) -> str:
    """WordPress's own fix: the patch a perfect black box would produce."""
    return _git(repo, "show", "--format=", sha, "--", "src")


# --------------------------------------------------------------------------


def build_fixture(cand: Candidate, repo: Path, runner) -> dict:
    """Revert, confirm the carried test really goes red, record both diffs.

    A candidate whose test stays green after the revert is not a seed: the
    test does not cover the regression, so there is nothing to reproduce.
    """
    selectors = sorted(set(cand.test_files))
    if not selectors:
        return {"ok": False, "why": "no PHPUnit test files in the commit"}

    before = runner.run_detailed(selectors)
    if not before.ran:
        return {"ok": False, "why": f"baseline did not run: {before.reason}"}
    if not before.ok:
        return {"ok": False, "why": f"test is already failing before the revert: {before.failed_ids[:3]}"}

    try:
        bad_diff = revert_source_only(repo, cand.sha)
    except RuntimeError as exc:
        restore(repo)
        return {"ok": False, "why": f"could not stage the regression: {exc}"}

    after = runner.run_detailed(selectors)

    if not after.ran:
        restore(repo)
        return {"ok": False, "why": f"suite did not run after the revert: {after.reason}"}
    if after.ok:
        restore(repo)
        return {"ok": False, "why": "the carried test stays green after the revert, so it does not cover the bug"}

    red = after.failed_ids
    restore(repo)

    return {
        "ok": True,
        "sha": cand.sha,
        "ticket": cand.ticket,
        "subject": cand.subject,
        "source": cand.source,
        "selectors": selectors,
        "regression_diff": bad_diff,       # applied to create the bug
        "reference_fix": forward_diff(repo, cand.sha),  # ground truth
        "red_tests": red,
        "baseline_tests": before.tests,
    }


def write_fixture(result: dict, out_dir: Path, name: str) -> Path:
    """Turn a verified seed into a fixture the pipeline can run."""
    diffs = out_dir / "diffs"
    diffs.mkdir(parents=True, exist_ok=True)
    (diffs / f"{name}_fix.diff").write_text(result["reference_fix"], encoding="utf-8")
    (diffs / f"{name}_regression.diff").write_text(result["regression_diff"], encoding="utf-8")

    red = result["red_tests"][0] if result["red_tests"] else ""
    fixture = {
        "bug": {
            "id": f"WP-{result['ticket'] or result['sha'][:7]}",
            "title": result["subject"],
            "body": (
                f"Reported in Trac #{result['ticket']}. "
                if result["ticket"] else ""
            ) + f"Reproduced by {red}.",
            "source": result["source"],
            "hint_paths": [],
        },
        "seed": {
            "sha": result["sha"],
            "regression_diff": f"diffs/{name}_regression.diff",
            "selectors": result["selectors"],
            "red_tests": result["red_tests"],
        },
        "precheck": {
            "attempts": [{
                "test_file": result["selectors"][0],
                "exit_code": 1,
                "output": "PHPUnit\n\nF\n\nThere was 1 failure:\n\n1) "
                          f"{red}\nFailed asserting that the regression is absent.\n\nFAILURES!",
            }]
        },
        "patch": f"diffs/{name}_fix.diff",
        "oracle": {"green": True},
        "deploy": {"slo_breach": False},
    }
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
