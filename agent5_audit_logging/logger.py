"""
agent5_audit_logging/logger.py

Agent 5 — Audit & Compliance Logging

Independently logs every query, classification, retrieval, access
decision, and final answer — timestamped and immutable (per the project
plan). This agent does not decide anything; it only observes and records
what Agents 1-4 already decided, so a compromised or buggy earlier agent
can't also hide its own tracks by skipping a log entry.

Storage backend is pluggable — see config.AUDIT_LOG_BACKEND:
  - "file" (default): append-only JSONL, one shared.schemas.AuditLogRecord
    per line. Zero DB dependency; what every existing test uses.
  - "db": the real Postgres `audit_log` table, via db_storage.py.

"Immutable" means hash-chained, not physically write-once: each record's
`immutable_hash` is a SHA-256 over that record's own content plus the
*previous* record's hash. Altering any record (or deleting one from the
middle) breaks the chain from that point forward, so verify_chain() can
detect and pinpoint tampering after the fact — same principle as a
blockchain, without needing one.

Every public function below (compute_hash, append_record,
read_all_records, verify_chain, and the four log_* wrappers) keeps the
exact same signature regardless of backend, so callers/tests never need
to know or care which one is active. `log_path`, when passed explicitly,
always forces the file backend at that path — this is what the existing
test suite relies on for per-test isolation, and it's untouched here.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4

from agent5_audit_logging.config import AUDIT_LOG_BACKEND, AUDIT_LOG_PATH
from shared.enums import LogStage
from shared.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Agent4Output,
    AuditLogRecord,
)

GENESIS_HASH = "0" * 64  # hash "before" the first record in any chain


# --------------------------------------------------------------------------
# Hashing — backend-agnostic, unchanged
# --------------------------------------------------------------------------

def _canonical_json(record: AuditLogRecord) -> str:
    """A deterministic JSON representation of a record's content, with
    immutable_hash excluded (you can't include a hash of yourself in the
    thing you're hashing). sort_keys + fixed separators make this
    reproducible regardless of field insertion order."""
    data = record.model_dump(mode="json")
    data.pop("immutable_hash", None)
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_hash(record: AuditLogRecord, prev_hash: str) -> str:
    """SHA-256 over (this record's content + the previous record's hash).
    Chaining in the previous hash is what makes this tamper-evident: to
    forge one record without detection, you'd have to also recompute
    every hash after it."""
    payload = _canonical_json(record) + prev_hash
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# File backend (original implementation, unchanged)
# --------------------------------------------------------------------------

def _read_lines(log_path: str) -> list[str]:
    if not os.path.exists(log_path):
        return []
    with open(log_path, "r", encoding="utf-8") as f:
        return [line for line in f.read().splitlines() if line.strip()]


def _get_last_hash(log_path: str) -> str:
    lines = _read_lines(log_path)
    if not lines:
        return GENESIS_HASH
    last = json.loads(lines[-1])
    return last["immutable_hash"]


def _append_line(record: AuditLogRecord, log_path: str) -> None:
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def _append_record_file(
    stage: LogStage, agent: str, session_id: str,
    payload_snapshot: dict, decision_summary: str, path: str,
) -> AuditLogRecord:
    prev_hash = _get_last_hash(path)
    record = AuditLogRecord(
        log_id=str(uuid4()),
        session_id=session_id,
        stage=stage,
        agent=agent,
        payload_snapshot=payload_snapshot,
        decision_summary=decision_summary,
        immutable_hash="",  # placeholder; _canonical_json excludes it anyway
    )
    record.immutable_hash = compute_hash(record, prev_hash)
    _append_line(record, path)
    return record


# --------------------------------------------------------------------------
# Core entry points — dispatch between file and DB backends
# --------------------------------------------------------------------------

def append_record(
    stage: LogStage,
    agent: str,
    session_id: str,
    payload_snapshot: dict,
    decision_summary: str,
    log_path: Optional[str] = None,
) -> AuditLogRecord:
    """Appends one audit record to the chain and returns it.

    `log_path`: if given, ALWAYS uses the file backend at that path,
    regardless of AUDIT_LOG_BACKEND — this is what tests rely on for
    isolation (a fresh tmp_path per test). If omitted, uses whichever
    backend config.AUDIT_LOG_BACKEND selects (file backend falls back to
    the shared AUDIT_LOG_PATH default, same as before this file changed).
    """
    if log_path is not None or AUDIT_LOG_BACKEND == "file":
        path = log_path or AUDIT_LOG_PATH
        return _append_record_file(stage, agent, session_id, payload_snapshot, decision_summary, path)

    # DB backend
    from agent5_audit_logging.db_storage import db_append_atomic

    def _build(prev_hash: str) -> AuditLogRecord:
        record = AuditLogRecord(
            log_id=str(uuid4()),
            session_id=session_id,
            stage=stage,
            agent=agent,
            payload_snapshot=payload_snapshot,
            decision_summary=decision_summary,
            immutable_hash="",
        )
        record.immutable_hash = compute_hash(record, prev_hash)
        return record

    return db_append_atomic(_build)


def read_all_records(log_path: Optional[str] = None) -> list[AuditLogRecord]:
    """Reads every record currently in the log, in append order.

    `log_path`: if given, always reads that file, regardless of backend
    config (test isolation, same as append_record). If omitted, reads
    from whichever backend is configured.
    """
    if log_path is not None or AUDIT_LOG_BACKEND == "file":
        path = log_path or AUDIT_LOG_PATH
        return [AuditLogRecord.model_validate_json(line) for line in _read_lines(path)]

    from agent5_audit_logging.db_storage import db_read_all
    return db_read_all()


def verify_chain(log_path: Optional[str] = None) -> tuple[bool, list[dict]]:
    """Recomputes each record's hash from its content + the *previous
    record's stored hash* and compares it to what's on disk/in the DB.

    Deliberately continues the chain using each record's *stored* hash
    (not the recomputed one) even after a mismatch — this isolates
    exactly which record(s) were altered, instead of every record after
    the first tampered one also showing as broken.

    Returns (is_intact, broken_records) where broken_records is a list of
    {"index", "log_id", "stage", "expected_hash", "actual_hash"} dicts —
    empty if the chain is fully intact. Backend-agnostic: driven entirely
    by read_all_records(), so it works identically for either backend.
    """
    records = read_all_records(log_path)
    prev_hash = GENESIS_HASH
    broken: list[dict] = []

    for i, rec in enumerate(records):
        expected = compute_hash(rec, prev_hash)
        if expected != rec.immutable_hash:
            broken.append(
                {
                    "index": i,
                    "log_id": rec.log_id,
                    "stage": rec.stage.value,
                    "expected_hash": expected,
                    "actual_hash": rec.immutable_hash,
                }
            )
        prev_hash = rec.immutable_hash

    return (len(broken) == 0, broken)


# --------------------------------------------------------------------------
# Per-agent convenience wrappers (unchanged — dispatch happens inside
# append_record, so these need no backend awareness at all)
# --------------------------------------------------------------------------

def log_classification(
    agent1_output: Agent1Output, log_path: Optional[str] = None
) -> AuditLogRecord:
    decision_summary = (
        f"intent={agent1_output.intent.value} "
        f"access_level={agent1_output.access_level.value} "
        f"needs_clarification={agent1_output.needs_clarification} "
        f"confidence={agent1_output.confidence}"
    )
    return append_record(
        stage=LogStage.CLASSIFICATION,
        agent="agent1_classification",
        session_id=agent1_output.session_id,
        payload_snapshot=agent1_output.model_dump(mode="json"),
        decision_summary=decision_summary,
        log_path=log_path,
    )


def log_retrieval(
    agent2_output: Agent2Output, log_path: Optional[str] = None
) -> AuditLogRecord:
    decision_summary = (
        f"results={len(agent2_output.results)} "
        f"confidence={agent2_output.retrieval_confidence.value} "
        f"reformulated={agent2_output.reformulated} "
        f"attempts={agent2_output.retrieval_attempts}"
    )
    return append_record(
        stage=LogStage.RETRIEVAL,
        agent="agent2_retrieval",
        session_id=agent2_output.session_id,
        payload_snapshot=agent2_output.model_dump(mode="json"),
        decision_summary=decision_summary,
        log_path=log_path,
    )


def log_generation(
    agent3_output: Agent3Output, log_path: Optional[str] = None
) -> AuditLogRecord:
    decision_summary = (
        f"grounded={agent3_output.grounded} "
        f"citations={len(agent3_output.citations)} "
        f"chunks_used={len(agent3_output.chunks_used)}"
    )
    return append_record(
        stage=LogStage.GENERATION,
        agent="agent3_response",
        session_id=agent3_output.session_id,
        payload_snapshot=agent3_output.model_dump(mode="json"),
        decision_summary=decision_summary,
        log_path=log_path,
    )


def log_verification(
    agent4_output: Agent4Output, log_path: Optional[str] = None
) -> AuditLogRecord:
    decision_summary = (
        f"decision={agent4_output.decision.value} "
        f"reason={agent4_output.denial_reason or 'n/a'} "
        f"confidence={agent4_output.confidence}"
    )
    return append_record(
        stage=LogStage.VERIFICATION,
        agent="agent4_verification",
        session_id=agent4_output.session_id,
        payload_snapshot=agent4_output.model_dump(mode="json"),
        decision_summary=decision_summary,
        log_path=log_path,
    )


# --------------------------------------------------------------------------
# Manual smoke test — run with: python -m agent5_audit_logging.logger
# Always uses the file backend (explicit log_path), regardless of your
# .env AUDIT_LOG_BACKEND setting, so this stays a safe local sanity check.
# For a DB-backend smoke test, see tests/test_agent5/test_db_backend.py.
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    demo_path = os.path.join(tempfile.gettempdir(), "bankkms_audit_demo.jsonl")
    if os.path.exists(demo_path):
        os.remove(demo_path)

    print(f"Writing demo audit chain to: {demo_path}\n")

    append_record(
        stage=LogStage.CLASSIFICATION,
        agent="agent1_classification",
        session_id="sess_demo",
        payload_snapshot={"intent": "procedure_lookup", "access_level": "public"},
        decision_summary="classified as procedure_lookup, access_level=public",
        log_path=demo_path,
    )
    append_record(
        stage=LogStage.RETRIEVAL,
        agent="agent2_retrieval",
        session_id="sess_demo",
        payload_snapshot={"results": 5, "retrieval_confidence": "medium"},
        decision_summary="retrieved 5 chunks at medium confidence",
        log_path=demo_path,
    )
    append_record(
        stage=LogStage.VERIFICATION,
        agent="agent4_verification",
        session_id="sess_demo",
        payload_snapshot={"decision": "approved", "confidence": 0.95},
        decision_summary="decision=approved confidence=0.95",
        log_path=demo_path,
    )

    ok, broken = verify_chain(demo_path)
    print(f"Chain intact: {ok}")
    print(f"Records: {len(read_all_records(demo_path))}\n")

    print("--- Simulating tampering with record #2 (retrieval) ---")
    lines = _read_lines(demo_path)
    tampered = json.loads(lines[1])
    tampered["decision_summary"] = "retrieved 999 chunks (TAMPERED)"
    lines[1] = json.dumps(tampered)
    with open(demo_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    ok2, broken2 = verify_chain(demo_path)
    print(f"Chain intact after tampering: {ok2}")
    if broken2:
        print(f"Tampering detected at: {broken2}")

    os.remove(demo_path)