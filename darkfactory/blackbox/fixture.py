"""Replays a recorded diff. Lets the whole line run with no model and no repo."""

from __future__ import annotations

from pathlib import Path

from ..schema import BugReport, Patch
from ..inspection.diffparse import parse


class FixtureFixer:
    name = "fixture"

    def __init__(self, diff_path: str | Path = "") -> None:
        self.diff_path = Path(diff_path)

    def fix(self, bug: BugReport, failing_test: str, repo: str) -> Patch:
        text = self.diff_path.read_text(encoding="utf-8")
        d = parse(text)
        return Patch(
            diff=text,
            produced_by=f"fixture:{self.diff_path.name}",
            files_changed=d.paths,
            insertions=d.insertions,
            deletions=d.deletions,
        )
