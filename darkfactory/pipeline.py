"""The line.

Every stage writes its decision to the audit trail before the next one
starts, so a run that dies halfway still leaves a readable record of how
far it got and why it stopped.

One rule governs the whole thing: anything that is not a clear pass hands
the bug to a person. The line never guesses.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import oracle, precheck
from .audit import AuditLog
from .deploy import StubDeployer
from .enrich import NullEnricher
from .inspection import inspect
from .policy import Policy
from .schema import BugReport, Decision, RunOutcome, Stage


@dataclass(slots=True)
class Line:
    policy: Policy
    audit: AuditLog
    generator: object      # test generator for pre-check
    fixer: object          # the black box
    runner: object         # test runner for the oracle
    judge: object          # semantic half of diff inspection
    deployer: object = None
    enricher: object = None
    repo: str = "."
    observer: object = None

    def __post_init__(self) -> None:
        if self.deployer is None:
            self.deployer = StubDeployer()
        if self.enricher is None:
            self.enricher = NullEnricher()

    def _emit(self, kind: str, **data) -> None:
        if self.observer is not None:
            self.observer(kind, data)

    def _stop(self, bug: BugReport, stage: Stage, decision: Decision, reason: str) -> RunOutcome:
        """Nothing ships. A reject and an escalate both end up with a person;
        we keep them distinct because they mean different things to the team."""
        self.audit.append(bug.id, Stage.OUTCOME, decision,
                          f"handed to a human at {stage}", {"reason": reason})
        self._emit("outcome", bug_id=bug.id, decision=str(decision), reason=reason,
                   stopped_at=str(stage))
        return RunOutcome(bug.id, decision, stage, reason, True)

    def run(self, bug: BugReport) -> RunOutcome:
        self._emit("intake", bug_id=bug.id, title=bug.title, source=bug.source,
                   body=bug.body)
        self.audit.append(bug.id, Stage.INTAKE, "accepted", bug.title,
                          {"source": bug.source})

        # 1. Pre-check. The box does not start unless this clears.
        self._emit("stage_start", bug_id=bug.id, stage="precheck")
        pre = precheck.run(bug, self.generator, self.repo)
        self.audit.append(bug.id, Stage.PRECHECK, pre.decision, pre.reason, pre)
        self._emit("stage_done", bug_id=bug.id, stage="precheck",
                   decision=str(pre.decision), reason=pre.reason, detail=pre)
        if pre.decision is not Decision.ALLOW:
            return self._stop(bug, Stage.PRECHECK, pre.decision, pre.reason)

        # 2. The black box. Not our deliverable.
        self._emit("stage_start", bug_id=bug.id, stage="blackbox")
        patch = self.fixer.fix(bug, pre.test_file or "", ".")
        self.audit.append(
            bug.id, Stage.BLACKBOX, "produced",
            f"{patch.produced_by} returned a diff",
            {"files_changed": patch.files_changed,
             "insertions": patch.insertions, "deletions": patch.deletions,
             "sandbox_run_id": patch.sandbox_run_id},
        )
        self._emit("stage_done", bug_id=bug.id, stage="blackbox", decision="produced",
                   reason=f"{patch.produced_by} returned a diff", detail=patch)

        # 3a. Oracle: did the behaviour actually change, and only that.
        self._emit("stage_start", bug_id=bug.id, stage="oracle")
        orc = oracle.run(patch, self.policy, self.runner,
                         repo=self.repo, repro_test=pre.test_file)
        self.audit.append(bug.id, Stage.ORACLE, orc.decision, orc.reason, orc)
        self._emit("stage_done", bug_id=bug.id, stage="oracle",
                   decision=str(orc.decision), reason=orc.reason, detail=orc)
        if orc.decision is not Decision.ALLOW:
            return self._stop(bug, Stage.ORACLE, orc.decision, orc.reason)

        # 3b. Diff inspection: is the change itself safe to ship.
        self._emit("stage_start", bug_id=bug.id, stage="inspection")
        insp = inspect(bug, patch, self.policy, self.judge)
        self.audit.append(bug.id, Stage.INSPECTION, insp.decision, insp.reason, insp)
        self._emit("stage_done", bug_id=bug.id, stage="inspection",
                   decision=str(insp.decision), reason=insp.reason, detail=insp)
        if insp.decision is not Decision.ALLOW:
            # The person who picks this up should not have to start from a
            # rule name. Research what we stopped on and file it with the
            # rejection, sources and all.
            self._emit("stage_start", bug_id=bug.id, stage="brief")
            briefs = self.enricher.brief(insp.findings)
            self._emit("stage_done", bug_id=bug.id, stage="brief", decision="researched",
                       reason=f"{len(briefs)} finding(s) briefed", detail=briefs)
            if briefs:
                cited = sum(len(b.sources) for b in briefs)
                self.audit.append(
                    bug.id, Stage.BRIEF, "researched",
                    f"{len(briefs)} finding(s) briefed from {cited} source(s)",
                    briefs,
                )
            return self._stop(bug, Stage.INSPECTION, insp.decision, insp.reason)

        # 4. Gated deploy.
        self._emit("stage_start", bug_id=bug.id, stage="deploy")
        dep = self.deployer.deploy(bug.id, patch)
        self.audit.append(bug.id, Stage.DEPLOY, dep.decision, dep.reason, dep)
        self._emit("stage_done", bug_id=bug.id, stage="deploy",
                   decision=str(dep.decision), reason=dep.reason, detail=dep)
        if dep.decision is not Decision.ALLOW:
            return self._stop(bug, Stage.DEPLOY, dep.decision, dep.reason)

        self.audit.append(bug.id, Stage.OUTCOME, Decision.ALLOW,
                          "shipped with no human in the loop", {"flag": dep.flag})
        self._emit("outcome", bug_id=bug.id, decision="allow",
                   reason="shipped with no human in the loop")
        return RunOutcome(bug.id, Decision.ALLOW, Stage.OUTCOME,
                          "shipped unattended", False)
