"""Policy loading. The policy is data, not code, so a judge can read it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Policy:
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path = "policy.json") -> "Policy":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def summary(self) -> str:
        return (
            f"{self.raw['name']}: "
            f"{len(self.raw['protected_paths'])} protected paths, "
            f"{len(self.raw['removed_guards'])} guard rules, "
            f"{len(self.raw['added_sinks'])} sink rules"
        )
