"""An open model on Nebius Token Factory as the black box.

Runs inside a Nebius Sandbox so the agent gets scoped file access and an
outbound allowlist rather than the host environment. Containment is the
part that matters here; how well it patches is not our problem.

TODO(team): wire to contree once Sandboxes access is approved.
"""

from __future__ import annotations

import os

from ..schema import BugReport, Patch


class TokenFactoryFixer:
    name = "tokenfactory"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("MODEL_FIXER", "")

    def fix(self, bug: BugReport, failing_test: str, repo: str) -> Patch:
        raise NotImplementedError(
            "Token Factory fixer not wired up yet - run with --fixer fixture"
        )
