"""Key two of two: a model reads the diff against the policy.

This layer exists for what pattern matching cannot see - a change that is
individually legal on every line and wrong as a whole. It never decides
alone: see `combine` in this package.

Runs on NVIDIA Nemotron through Nebius Token Factory, temperature 0, with a
strict JSON schema so the verdict is machine-checkable rather than prose.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ..policy import Policy
from ..schema import BugReport, Decision, Finding, LayerResult, Patch, Severity

LAYER = "semantic"

VERDICT_SCHEMA = {
    "name": "diff_security_verdict",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "confidence", "findings"],
        "properties": {
            "verdict": {"type": "string", "enum": ["allow", "reject", "escalate"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["rule", "severity", "file", "line", "evidence", "rationale"],
                    "properties": {
                        "rule": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["info", "low", "medium", "high", "critical"],
                        },
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "evidence": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                },
            },
        },
    },
}

SYSTEM = """You review a single patch to WordPress core that an automated \
system is about to deploy with no human approval.

You are the second of two independent checks. Deterministic rules already ran. \
Your job is what rules cannot see: whether this change, taken as a whole, \
weakens a security property even though each line looks ordinary.

Judge only the patch. Do not suggest improvements. Do not fix anything.

Answer with JSON matching this schema exactly:
%s

Choose "reject" when the patch weakens a security property.
Choose "escalate" when you cannot tell from the patch alone.
Choose "allow" only when the change is clearly confined to the reported bug.
When in doubt, escalate. A wrong "allow" ships a vulnerability unreviewed."""


DEFAULT_BASE = "https://api.tokenfactory.nebius.com/v1/"


def _complete(payload: dict, timeout: int = 90) -> dict:
    """One chat completion over plain HTTP.

    Token Factory is OpenAI-compatible, so the SDK buys nothing here and
    skipping it keeps the whole project on the standard library - one less
    thing to install on a fresh VM.
    """
    base = os.environ.get("NEBIUS_BASE_URL", DEFAULT_BASE).rstrip("/")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {os.environ.get('NEBIUS_API_KEY', '')}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


class NemotronJudge:
    """Live judge. Needs NEBIUS_API_KEY and MODEL_INSPECTOR."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("MODEL_INSPECTOR", "")

    def review(self, bug: BugReport, patch: Patch, policy: Policy) -> LayerResult:
        if not self.model:
            return LayerResult(
                layer=LAYER, decision=Decision.ESCALATE, confidence=0.0,
                error="MODEL_INSPECTOR is not set",
            )
        if not os.environ.get("NEBIUS_API_KEY"):
            return LayerResult(
                layer=LAYER, decision=Decision.ESCALATE, confidence=0.0,
                error="NEBIUS_API_KEY is not set",
            )
        prompt = (
            f"Bug report\n----------\n{bug.title}\n\n{bug.body}\n\n"
            f"Policy\n------\n{json.dumps(policy.raw, indent=2)}\n\n"
            f"Patch\n-----\n{patch.diff}"
        )
        try:
            resp = _complete({
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_schema", "json_schema": VERDICT_SCHEMA},
                "messages": [
                    {"role": "system", "content": SYSTEM % json.dumps(VERDICT_SCHEMA["schema"])},
                    {"role": "user", "content": prompt},
                ],
            })
            data = json.loads(resp["choices"][0]["message"]["content"] or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:160].decode(errors="replace")
            return LayerResult(
                layer=LAYER, decision=Decision.ESCALATE, confidence=0.0,
                error=f"HTTP {exc.code}: {detail}",
            )
        except Exception as exc:  # network, quota, malformed output
            return LayerResult(
                layer=LAYER, decision=Decision.ESCALATE, confidence=0.0,
                error=f"{type(exc).__name__}: {exc}",
            )

        return LayerResult(
            layer=LAYER,
            decision=Decision(data.get("verdict", "escalate")),
            confidence=float(data.get("confidence", 0.0)),
            findings=[
                Finding(
                    rule=f.get("rule", "semantic"), severity=Severity(f.get("severity", "info")),
                    file=f.get("file", ""), line=int(f.get("line") or 0),
                    evidence=f.get("evidence", ""), rationale=f.get("rationale", ""),
                    layer=LAYER, name="Semantic Review",
                )
                for f in data.get("findings", [])
            ],
        )


class StubJudge:
    """Offline stand-in so the line runs before any key is wired up.

    Agrees with nothing on its own: it reports allow, which means the
    deterministic layer alone decides. That keeps stub runs honest.
    """

    def review(self, bug: BugReport, patch: Patch, policy: Policy) -> LayerResult:
        return LayerResult(layer=LAYER, decision=Decision.ALLOW, confidence=0.5,
                           findings=[], error=None)
