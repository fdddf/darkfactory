"""Minimal unified-diff parser.

We read the patch rather than caging the runtime, so everything downstream
depends on knowing exactly which lines a change added and removed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

# wordpress-develop keeps the shipped tree under src/, so a diff from it
# reads src/wp-includes/pluggable.php while the policy talks about
# wp-includes/pluggable.php. Normalising here means a rule cannot be
# sidestepped by which checkout the patch came from.
_SRC_PREFIX = "src/"


def normalize(path: str) -> str:
    return path[len(_SRC_PREFIX):] if path.startswith(_SRC_PREFIX) else path


@dataclass(slots=True)
class Line:
    number: int  # line number in the new file (added) or old file (removed)
    text: str


@dataclass(slots=True)
class FileDiff:
    path: str
    added: list[Line] = field(default_factory=list)
    removed: list[Line] = field(default_factory=list)
    is_new: bool = False
    is_delete: bool = False


@dataclass(slots=True)
class ParsedDiff:
    files: list[FileDiff] = field(default_factory=list)

    @property
    def paths(self) -> list[str]:
        return [f.path for f in self.files]

    @property
    def insertions(self) -> int:
        return sum(len(f.added) for f in self.files)

    @property
    def deletions(self) -> int:
        return sum(len(f.removed) for f in self.files)


def parse(diff_text: str) -> ParsedDiff:
    out = ParsedDiff()
    current: FileDiff | None = None
    old_no = new_no = 0

    for raw in diff_text.splitlines():
        if raw.startswith("diff --git"):
            parts = raw.split()
            path = parts[-1][2:] if parts[-1].startswith("b/") else parts[-1]
            current = FileDiff(path=path)
            out.files.append(current)
            continue

        if current is None:
            continue

        if raw.startswith("new file mode"):
            current.is_new = True
            continue
        if raw.startswith("deleted file mode"):
            current.is_delete = True
            continue
        if raw.startswith("+++ ") or raw.startswith("--- ") or raw.startswith("index "):
            continue

        m = _HUNK.match(raw)
        if m:
            old_no, new_no = int(m.group(1)), int(m.group(3))
            continue

        if raw.startswith("+"):
            current.added.append(Line(new_no, raw[1:]))
            new_no += 1
        elif raw.startswith("-"):
            current.removed.append(Line(old_no, raw[1:]))
            old_no += 1
        else:
            old_no += 1
            new_no += 1

    return out
