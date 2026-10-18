"""Interface contracts for the dark factory pipeline.

These types are the ONLY thing the four parallel workstreams share.
Do not change them without telling the whole team.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class Decision(StrEnum):
    ALLOW = "allow"
    REJECT = "reject"
    ESCALATE = "escalate"


class Stage(StrEnum):
    INTAKE = "intake"
    PRECHECK = "precheck"
    BLACKBOX = "blackbox"
    ORACLE = "oracle"
    INSPECTION = "inspection"
    BRIEF = "brief"
    DEPLOY = "deploy"
    OUTCOME = "outcome"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


@dataclass(slots=True)
class BugReport:
    """One bug entering the line.

    `source` carries provenance: for seeded bugs this is the reverted
    WordPress commit plus its Trac ticket, which is what lets us claim the
    bug set is real rather than synthetic.
    """

    id: str
    title: str
    body: str
    source: str = ""
    hint_paths: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Stage results
# --------------------------------------------------------------------------


@dataclass(slots=True)
class GateResult:
    """One of the four pre-check gates."""

    name: str
    passed: bool
    detail: str = ""


@dataclass(slots=True)
class PrecheckResult:
    """Did we manage to generate a test that reproduces the bug?

    This is the gate that defines "trivial". If it does not clearly pass,
    the black box never starts.
    """

    decision: Decision
    reproduced: bool
    attempts: int
    gates: list[GateResult] = field(default_factory=list)
    test_file: str | None = None
    test_name: str | None = None
    reason: str = ""


@dataclass(slots=True)
class Patch:
    """What the black box hands back. We never look inside the box itself."""

    diff: str
    produced_by: str
    files_changed: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    sandbox_run_id: str | None = None


@dataclass(slots=True)
class OracleResult:
    """Behavioural evidence: the bug is gone and nothing else broke."""

    decision: Decision
    repro_red_to_green: bool
    regression_green: bool
    test_files_untouched: bool
    tests_selected: list[str] = field(default_factory=list)
    selection_strategy: str = ""
    quarantined: list[str] = field(default_factory=list)
    reason: str = ""
    # Populated by the real runner; the audit needs the numbers, not a verdict.
    tests_run: int = 0
    failures: list[str] = field(default_factory=list)
    quarantine_suppressed: list[str] = field(default_factory=list)
    runner: str = ""
    runner_summary: str = ""


@dataclass(slots=True)
class Finding:
    rule: str
    severity: Severity
    file: str
    line: int
    evidence: str
    rationale: str
    layer: str  # "deterministic" | "semantic"
    # The weakness class, so a finding can be looked up against published
    # advisories rather than only read as our own rule name.
    cwe: str = ""
    name: str = ""


@dataclass(slots=True)
class LayerResult:
    """One key of the two-key rule."""

    layer: str
    decision: Decision
    confidence: float = 1.0
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class InspectionResult:
    """Security verdict on the diff itself.

    Two independent layers must both clear a change. Disagreement is not
    resolved by picking a winner: it escalates.
    """

    decision: Decision
    deterministic: LayerResult
    semantic: LayerResult
    reason: str = ""

    @property
    def findings(self) -> list[Finding]:
        return self.deterministic.findings + self.semantic.findings


@dataclass(slots=True)
class DeployResult:
    decision: Decision
    deployed: bool = False
    flag: str = ""
    canary_pct: int = 0
    slo_breached: bool = False
    rolled_back: bool = False
    reason: str = ""


@dataclass(slots=True)
class RunOutcome:
    """What happened to one bug, end to end."""

    bug_id: str
    decision: Decision
    stopped_at: Stage
    reason: str
    escalated_to_human: bool


# --------------------------------------------------------------------------
# Seams. Swap any implementation without touching the pipeline.
# --------------------------------------------------------------------------


class Fixer(Protocol):
    """The black box. Explicitly NOT our deliverable.

    Drop in Devin, a Token Factory model, or a shell script. None of the
    confidence is meant to come from this.
    """

    name: str

    def fix(self, bug: BugReport, failing_test: str, repo: str) -> Patch: ...


class SemanticJudge(Protocol):
    def review(self, bug: BugReport, patch: Patch, policy: Any) -> LayerResult: ...


class TestRunner(Protocol):
    def run(self, repo: str, selectors: list[str]) -> tuple[bool, str]: ...


# --------------------------------------------------------------------------
# Serialisation. Audit entries must be byte-stable, so one canonical form.
# --------------------------------------------------------------------------


def to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, StrEnum):
        return str(obj)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


def canonical_json(obj: Any) -> str:
    """Stable encoding. Any drift here silently breaks the hash chain."""
    return json.dumps(
        to_jsonable(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
