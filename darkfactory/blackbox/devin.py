"""Devin as the black box.

Sessions run in parallel, one per qualified bug, and each hands back a diff
that goes through the same gates as any other. Orchestrate several with
Devin Dynamic Workflows: https://docs.devin.ai/work-with-devin/dynamic-workflows

TODO(team): fill in once DEVIN_API_KEY is issued. Key must be a cog_
service-user key - apk_ keys are not accepted.
"""

from __future__ import annotations

import os

from ..schema import BugReport, Patch


class DevinFixer:
    name = "devin"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("DEVIN_API_KEY", "")

    def fix(self, bug: BugReport, failing_test: str, repo: str) -> Patch:
        raise NotImplementedError(
            "Devin fixer not wired up yet - run with --fixer fixture"
        )
