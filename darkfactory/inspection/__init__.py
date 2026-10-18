"""Diff inspection: the security half of the post-checks.

Two keys, both must turn. Neither layer can ship a change on its own and
neither can be overruled by the other - a disagreement goes to a human,
because that is cheaper than being wrong in either direction.
"""

from __future__ import annotations

from ..policy import Policy
from ..schema import (
    BugReport, Decision, InspectionResult, LayerResult, Patch, SemanticJudge,
)
from . import deterministic
from .semantic import NemotronJudge, StubJudge

__all__ = ["inspect", "combine", "NemotronJudge", "StubJudge"]


def combine(det: LayerResult, sem: LayerResult, policy: Policy) -> tuple[Decision, str]:
    """The two-key rule."""
    if det.decision is Decision.REJECT or sem.decision is Decision.REJECT:
        who = "deterministic" if det.decision is Decision.REJECT else "semantic"
        return Decision.REJECT, f"{who} layer rejected the change"

    if sem.error and policy.get("escalate_on_semantic_error", True):
        return Decision.ESCALATE, f"semantic layer could not run ({sem.error})"

    if det.decision is Decision.ALLOW and sem.decision is Decision.ALLOW:
        return Decision.ALLOW, "both layers cleared the change"

    return Decision.ESCALATE, (
        f"layers disagree (deterministic={det.decision}, semantic={sem.decision})"
    )


def inspect(
    bug: BugReport, patch: Patch, policy: Policy, judge: SemanticJudge
) -> InspectionResult:
    det = deterministic.inspect(patch, policy)
    sem = judge.review(bug, patch, policy)
    decision, reason = combine(det, sem, policy)
    return InspectionResult(decision=decision, deterministic=det, semantic=sem, reason=reason)
