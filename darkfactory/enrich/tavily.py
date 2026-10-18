"""Brief the human the line escalates to.

The whole design puts a person at the end of every path that is not a clear
pass. That person arrives cold, holding a rule name and a line number, and
has to decide whether a machine-written patch is dangerous. "removed_guard:
current_user_can at misc.php:315" is a ticket, not a briefing.

So when the line stops, we research what it stopped on: what the
vulnerability class is, how WordPress has been bitten by it before, what the
published advisories say. Tavily does the retrieval, every claim keeps its
source, and the brief goes into the audit trail with the rejection - so the
record says not just that we refused a patch but what we knew when we did.

This runs only on reject and escalate. A clean run does no searching, which
keeps it cheap and keeps the demo honest.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

ENDPOINT = "https://api.tavily.com/search"

# WordPress security reporting lives in a handful of places. Preferring them
# keeps the brief out of SEO blogspam without hard-filtering useful results.
PREFERRED = [
    "wordpress.org",
    "make.wordpress.org",
    "core.trac.wordpress.org",
    "wpscan.com",
    "patchstack.com",
    "cve.mitre.org",
    "nvd.nist.gov",
    "owasp.org",
]

# What to ask about, per rule the inspector can raise.
QUERIES = {
    "removed_guard": "{evidence} WordPress {detail} vulnerability advisory",
    "added_sink": "WordPress {detail} {evidence} exploit advisory",
    "interpolated_sql": "WordPress $wpdb SQL injection prepare advisory",
    "protected_path": "WordPress {file} security hardening history",
    "dependency_changed": "{file} known vulnerabilities advisory",
    "secret_added": "credential committed to source control remediation",
}


@dataclass(slots=True)
class Source:
    title: str
    url: str
    snippet: str
    score: float = 0.0


@dataclass(slots=True)
class Brief:
    """Researched context for one finding."""

    rule: str
    query: str
    answer: str = ""
    sources: list[Source] = field(default_factory=list)
    error: str | None = None


class NullEnricher:
    """Default. Does no network calls, so the line runs offline."""

    name = "none"

    def brief(self, findings) -> list[Brief]:
        return []


class TavilyEnricher:
    """Tavily search, scoped to the finding and to security sources."""

    name = "tavily"

    def __init__(
        self,
        api_key: str | None = None,
        max_results: int = 4,
        timeout: int = 20,
        max_findings: int = 3,
    ) -> None:
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self.max_results = max_results
        self.timeout = timeout
        # Brief the few findings that drove the decision, not all of them.
        self.max_findings = max_findings

    def _search(self, query: str) -> tuple[str, list[Source], str | None]:
        if not self.api_key:
            return "", [], "TAVILY_API_KEY is not set"

        payload = json.dumps({
            "query": query,
            "search_depth": "advanced",
            "max_results": self.max_results,
            "include_answer": True,
            "include_domains": PREFERRED,
            "include_domains_mode": "prefer",
        }).encode()

        req = urllib.request.Request(
            ENDPOINT,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return "", [], f"HTTP {exc.code}: {exc.read()[:200].decode(errors='replace')}"
        except Exception as exc:
            return "", [], f"{type(exc).__name__}: {exc}"

        sources = [
            Source(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=(r.get("content") or "")[:400],
                score=float(r.get("score") or 0),
            )
            for r in data.get("results", [])
        ]
        return (data.get("answer") or ""), sources, None

    @staticmethod
    def _query_for(finding) -> str:
        template = QUERIES.get(finding.rule, "WordPress {detail} security")
        return template.format(
            evidence=(finding.evidence or "")[:80],
            detail=(finding.rationale or "")[:80],
            file=finding.file or "WordPress core",
        ).strip()

    def brief(self, findings) -> list[Brief]:
        """Research the findings that mattered, worst first."""
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        ranked = sorted(findings, key=lambda f: order.get(str(f.severity), 9))

        out: list[Brief] = []
        seen: set[str] = set()
        for finding in ranked:
            if len(out) >= self.max_findings:
                break
            query = self._query_for(finding)
            if query in seen:
                continue
            seen.add(query)
            answer, sources, error = self._search(query)
            out.append(Brief(rule=finding.rule, query=query, answer=answer,
                             sources=sources, error=error))
        return out
