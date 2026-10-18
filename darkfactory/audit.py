"""Append-only, hash-chained, signed audit log.

The human is out of the loop while the line runs and on the loop afterwards.
That only works if the record cannot be quietly edited after the fact, so
every entry commits to the one before it and the whole chain is signed.

Tamper with one byte of the log and `verify` reports the exact entry where
the chain breaks. That check is the demo.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .schema import Stage, canonical_json, to_jsonable

GENESIS = "0" * 64


@dataclass(slots=True)
class AuditEntry:
    seq: int
    ts: float
    bug_id: str
    stage: Stage
    decision: str
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = GENESIS
    entry_hash: str = ""
    signature: str = ""

    def body(self) -> dict[str, Any]:
        """Exactly the fields the hash commits to."""
        return {
            "seq": self.seq,
            "ts": self.ts,
            "bug_id": self.bug_id,
            "stage": str(self.stage),
            "decision": self.decision,
            "summary": self.summary,
            "payload": to_jsonable(self.payload),
            "prev_hash": self.prev_hash,
        }

    def compute_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.body()).encode()).hexdigest()


def _sign(digest: str, key: bytes) -> str:
    return hmac.new(key, digest.encode(), hashlib.sha256).hexdigest()


def _load_key() -> bytes:
    # HMAC keeps this dependency-free. Swap for Ed25519 if there is time;
    # the chain itself does not change.
    return os.environ.get("AUDIT_SIGNING_KEY", "dev-insecure-key").encode()


class AuditLog:
    """JSONL on disk. Append-only by construction: we never rewrite a line."""

    def __init__(self, path: str | Path = "audit/trail.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._key = _load_key()

    # -- writing ----------------------------------------------------------

    def _tail(self) -> tuple[int, str]:
        seq, prev = 0, GENESIS
        for entry in self.read():
            seq, prev = entry.seq + 1, entry.entry_hash
        return seq, prev

    def append(
        self,
        bug_id: str,
        stage: Stage,
        decision: str,
        summary: str,
        payload: Any = None,
    ) -> AuditEntry:
        seq, prev = self._tail()
        entry = AuditEntry(
            seq=seq,
            ts=time.time(),
            bug_id=bug_id,
            stage=stage,
            decision=str(decision),
            summary=summary,
            payload=to_jsonable(payload) if payload is not None else {},
            prev_hash=prev,
        )
        entry.entry_hash = entry.compute_hash()
        entry.signature = _sign(entry.entry_hash, self._key)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(canonical_json(entry) + "\n")
        return entry

    # -- reading ----------------------------------------------------------

    def read(self) -> Iterator[AuditEntry]:
        import json

        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                yield AuditEntry(
                    seq=raw["seq"],
                    ts=raw["ts"],
                    bug_id=raw["bug_id"],
                    stage=Stage(raw["stage"]),
                    decision=raw["decision"],
                    summary=raw["summary"],
                    payload=raw.get("payload", {}),
                    prev_hash=raw["prev_hash"],
                    entry_hash=raw.get("entry_hash", ""),
                    signature=raw.get("signature", ""),
                )

    def for_bug(self, bug_id: str) -> list[AuditEntry]:
        return [e for e in self.read() if e.bug_id == bug_id]

    # -- integrity --------------------------------------------------------

    def verify(self) -> tuple[bool, list[str]]:
        """Walk the chain. Returns (ok, problems)."""
        problems: list[str] = []
        prev = GENESIS
        expected_seq = 0

        for entry in self.read():
            where = f"entry #{entry.seq} ({entry.stage}, bug {entry.bug_id})"

            if entry.seq != expected_seq:
                problems.append(f"{where}: sequence jumped, expected {expected_seq}")
            if entry.prev_hash != prev:
                problems.append(f"{where}: prev_hash does not match the entry before it")

            recomputed = entry.compute_hash()
            if recomputed != entry.entry_hash:
                problems.append(f"{where}: contents were edited after the fact")
            elif _sign(recomputed, self._key) != entry.signature:
                problems.append(f"{where}: signature does not verify")

            prev = entry.entry_hash
            expected_seq = entry.seq + 1

        return (not problems), problems
