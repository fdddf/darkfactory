"""Key one of two: deterministic checks on the diff.

Nothing here asks a model anything. Every finding is reproducible from the
patch and the policy file alone, which is what makes it auditable.

Where phpcs is available we fold in the WordPress security sniffs too, but
the rules below stand on their own so the line still runs without it.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from functools import lru_cache
import tempfile
from pathlib import Path

from ..policy import Policy
from ..schema import Decision, Finding, LayerResult, Patch, Severity
from .diffparse import ParsedDiff, normalize, parse

LAYER = "deterministic"


def _meta(policy: Policy, rule: str) -> dict:
    """Severity, CWE and display name for a rule the patterns do not carry."""
    for spec in policy.get("pattern_rules", []):
        if spec["rule"] == rule:
            return spec
    return {}


def _finding(spec: dict, *, rule: str, file: str, line: int, evidence: str,
             severity: str | None = None, why: str | None = None) -> Finding:
    return Finding(
        rule=rule,
        severity=Severity(severity or spec.get("severity", "medium")),
        file=file, line=line, evidence=evidence,
        rationale=why or spec.get("why", ""),
        layer=LAYER,
        cwe=spec.get("cwe", ""),
        name=spec.get("name", ""),
    )


def _matches(path: str, glob: str) -> bool:
    """Checked against the path as written and with src/ stripped."""
    prefix = glob.rstrip("*").rstrip("/") + "/"
    for candidate in {path, normalize(path)}:
        if fnmatch.fnmatch(candidate, glob) or candidate.startswith(prefix):
            return True
    return False


def _protected_paths(d: ParsedDiff, policy: Policy) -> list[Finding]:
    spec = _meta(policy, "protected_path")
    out = []
    for rule in policy["protected_paths"]:
        for f in d.files:
            if _matches(f.path, rule["glob"]):
                out.append(_finding(
                    spec, rule="protected_path", file=f.path, line=0,
                    evidence=f"patch touches {f.path}",
                    why=f"protected path ({rule['why']}); changes here never ship unattended",
                ))
    return out


def _test_files(d: ParsedDiff, policy: Policy) -> list[Finding]:
    """A fix that edits the tests has moved the goalposts, not fixed the bug."""
    out = []
    for glob in policy["test_paths"]:
        for f in d.files:
            if _matches(f.path, glob):
                out.append(_finding(
                    _meta(policy, "test_file_modified"), rule="test_file_modified",
                    file=f.path, line=0, evidence=f"patch modifies {f.path}",
                ))
    return out


def _dependencies(d: ParsedDiff, policy: Policy) -> list[Finding]:
    out = []
    for f in d.files:
        if Path(normalize(f.path)).name in policy["dependency_manifests"]:
            out.append(_finding(
                _meta(policy, "dependency_changed"), rule="dependency_changed",
                file=f.path, line=0, evidence=f"patch modifies {f.path}",
            ))
    return out


def _blast_radius(d: ParsedDiff, policy: Policy) -> list[Finding]:
    limits = policy["blast_radius"]
    out = []
    checks = [
        (len(d.files), limits["max_files_changed"], "files changed"),
        (d.insertions, limits["max_insertions"], "lines added"),
        (d.deletions, limits["max_deletions"], "lines removed"),
    ]
    for actual, allowed, label in checks:
        if actual > allowed:
            out.append(_finding(
                _meta(policy, "blast_radius"), rule="blast_radius",
                file="", line=0, evidence=f"{actual} {label}, limit is {allowed}",
            ))
    return out


def _removed_guards(d: ParsedDiff, policy: Policy) -> list[Finding]:
    """The one that catches a fix which passes every test and still ships a hole."""
    out = []
    for rule in policy["removed_guards"]:
        needle = rule["pattern"]
        for f in d.files:
            removed = [ln for ln in f.removed if _hit(ln.text, needle)]
            if not removed:
                continue
            # Only a finding if it is gone, not merely moved within the hunk.
            still_there = any(_hit(ln.text, needle) for ln in f.added)
            if still_there:
                continue
            for ln in removed:
                out.append(_finding(
                    rule, rule="removed_guard", file=f.path, line=ln.number,
                    evidence=ln.text.strip(),
                ))
    return out


def _added_sinks(d: ParsedDiff, policy: Policy) -> list[Finding]:
    out = []
    for rule in policy["added_sinks"]:
        needle = rule["pattern"]
        for f in d.files:
            for ln in f.added:
                if _hit(ln.text, needle):
                    out.append(_finding(
                        rule, rule="added_sink", file=f.path, line=ln.number,
                        evidence=ln.text.strip(),
                    ))
    return out


# Patterns that need more than a substring: the vulnerability is in how the
# request input reaches the sink, not in the function name alone.
REQUEST = r"\$_(?:GET|POST|REQUEST|COOKIE|FILES|SERVER)"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("interpolated_sql",
     re.compile(r"->(?:query|get_results|get_var|get_row|get_col)\s*\(\s*[\"'][^\"']*\$")),
    ("path_traversal",
     re.compile(rf"(?:fopen|file_get_contents|file_put_contents|unlink|readfile|copy|rename)"
                rf"\s*\([^)]*{REQUEST}")),
    ("file_inclusion",
     re.compile(rf"(?:include|include_once|require|require_once)\s*(?:\(|\s)[^;]*{REQUEST}")),
    ("unescaped_echo",
     re.compile(rf"(?:echo|print)\s+(?:(?!esc_|wp_kses|sanitize_|absint|intval)[^;])*{REQUEST}")),
]


def _patterns(d: ParsedDiff, policy: Policy) -> list[Finding]:
    out = []
    for rule, pattern in PATTERNS:
        spec = _meta(policy, rule)
        for f in d.files:
            for ln in f.added:
                if pattern.search(ln.text):
                    out.append(_finding(
                        spec, rule=rule, file=f.path, line=ln.number,
                        evidence=ln.text.strip(),
                    ))
    return out


def _secrets(d: ParsedDiff, policy: Policy) -> list[Finding]:
    pats = [re.compile(p) for p in policy["secret_patterns"]]
    out = []
    for f in d.files:
        for ln in f.added:
            for p in pats:
                if p.search(ln.text):
                    out.append(_finding(
                        _meta(policy, "secret_added"), rule="secret_added",
                        file=f.path, line=ln.number,
                        evidence=ln.text.strip()[:60] + "...",
                    ))
                    break
    return out


def _phpcs(patch: Patch) -> list[Finding]:
    """WordPress security sniffs, when phpcs is installed. Optional by design."""
    if not shutil.which("phpcs"):
        return []
    out: list[Finding] = []
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False) as fh:
            fh.write(patch.diff)
        proc = subprocess.run(
            ["phpcs", "--standard=WordPress", "--report=json", "--runtime-set", "testVersion", "7.4-"],
            input=patch.diff, capture_output=True, text=True, timeout=60,
        )
        import json as _json
        data = _json.loads(proc.stdout or "{}")
        for path, info in (data.get("files") or {}).items():
            for msg in info.get("messages", []):
                src = msg.get("source", "")
                if not src.startswith(("WordPress.Security", "WordPress.DB")):
                    continue
                out.append(Finding(
                    rule=f"phpcs:{src}",
                    severity=Severity.HIGH if msg.get("type") == "ERROR" else Severity.MEDIUM,
                    file=path, line=msg.get("line", 0),
                    evidence=msg.get("message", ""),
                    rationale="WordPress coding standards security sniff",
                    layer=LAYER, name="Coding Standards",
                ))
    except Exception:
        return out
    return out


# A bare substring test matches inside longer names: "rand(" fires on
# "mt_rand(", "system(" on "filesystem(". Function-shaped patterns get a
# boundary; everything else stays a substring.
_CALL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\($")


@lru_cache(maxsize=512)
def _needle(pattern: str) -> re.Pattern[str] | None:
    if _CALL.match(pattern):
        return re.compile(r"(?<![A-Za-z0-9_$>\-])" + re.escape(pattern))
    return None


def _hit(text: str, pattern: str) -> bool:
    rx = _needle(pattern)
    return bool(rx.search(text)) if rx else pattern in text


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """One line can satisfy two rules for the same reason; report it once."""
    seen: set[tuple] = set()
    out = []
    for f in findings:
        key = (f.rule, f.file, f.line, f.cwe, f.evidence)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


BLOCKING = {Severity.CRITICAL, Severity.HIGH}


def inspect(patch: Patch, policy: Policy) -> LayerResult:
    d: ParsedDiff = parse(patch.diff)

    findings: list[Finding] = []
    for check in (_protected_paths, _test_files, _dependencies, _blast_radius,
                  _removed_guards, _added_sinks, _secrets):
        findings += check(d, policy)
    findings += _patterns(d, policy)
    findings += _phpcs(patch)
    findings = _dedupe(findings)

    if any(f.severity in BLOCKING for f in findings):
        decision = Decision.REJECT
    elif findings:
        decision = Decision.ESCALATE
    else:
        decision = Decision.ALLOW

    return LayerResult(layer=LAYER, decision=decision, confidence=1.0, findings=findings)
