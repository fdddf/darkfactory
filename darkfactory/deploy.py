"""Gated deploy: flag, canary, SLO, automatic rollback.

The worst case has to stay small and undo itself, so nothing ships to all
traffic and nothing waits on a person to notice.

TODO(team): back this with two WP containers behind a proxy. The decision
record it writes does not change when the plumbing becomes real.
"""

from __future__ import annotations

from .schema import Decision, DeployResult, Patch

CANARY_PCT = 10


class StubDeployer:
    def __init__(self, slo_breach: bool = False) -> None:
        self.slo_breach = slo_breach

    def deploy(self, bug_id: str, patch: Patch) -> DeployResult:
        flag = f"autofix_{bug_id.lower().replace('-', '_')}"
        if self.slo_breach:
            return DeployResult(
                decision=Decision.REJECT, deployed=False, flag=flag,
                canary_pct=CANARY_PCT, slo_breached=True, rolled_back=True,
                reason="error rate crossed the SLO during canary; rolled back automatically",
            )
        return DeployResult(
            decision=Decision.ALLOW, deployed=True, flag=flag,
            canary_pct=CANARY_PCT, slo_breached=False, rolled_back=False,
            reason=f"canary at {CANARY_PCT}% held within SLO, flag rolled forward",
        )
