"""
agent5_audit_logging/logger.py

Agent 5 — Audit & Compliance Logging

Independently logs every query, classification, retrieval, access
decision, and final answer — timestamped and immutable. This agent does
not decide anything; it only observes and records what Agents 1-4 already
decided, so a compromised or buggy earlier agent can't also hide its own
tracks by skipping a log entry.

Storage: the `audit_log` table in the shared Postgres database (see
database/models.py::AuditLog). One continuous, GLOBAL hash chain across
the whole system — not per-session — which matches how a real compliance
audit trail should work: a single ledger, not one that resets per user.

<<<<<<< Updated upstream
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
=======
"Immutable" here means hash-chained, not physically write-once: each
record's `immutable_hash` is a SHA-256 over that record's own content
plus the *previous* record's hash (now an explicit `prev_hash` column,
rather than implied by file-line order as in the earlier JSONL
prototype). Altering any record — or deleting one from the middle —
breaks the chain from that point forward, so verify_chain() can detect
and pinpoint tampering after the fact.

Testing note: verify_chain()'s tests deliberately corrupt records to
prove tampering is caught. Running that against the REAL shared
production audit_log table would actually corrupt real audit history for
the whole team — the opposite of what an immutable log is for. To avoid
this, the DB session is injectable: production code uses the real
SessionLocal by default; tests pass an isolated in-memory SQLite session
factory instead (see tests/test_agent5/conftest.py). Same table schema,
zero risk to shared data.

Concurrency note: this assumes reasonably low write concurrency (fine for
this project's scope). Postgres's own row insert ordering (the `id`
autoincrement sequence) gives a reliable global order even with multiple
writers, which is actually a step up from the JSONL version's
single-writer assumption — but there's still a narrow race between
"read the last hash" and "insert using it" if two processes log
simultaneously. Not addressed here; a production version would wrap the
read-last-hash + insert in a single transaction with a row lock.
>>>>>>> Stashed changes
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable, Optional
from uuid import uuid4

<<<<<<< Updated upstream
from agent5_audit_logging.config import AUDIT_LOG_BACKEND, AUDIT_LOG_PATH
=======
from sqlalchemy.orm import Session as DBSession

from database.config import SessionLocal
from database.models import AuditLog as DBAuditLog
from database.models import AuditStage as DBAuditStage
>>>>>>> Stashed changes
from shared.enums import LogStage
from shared.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Agent4Output,
    AuditLogRecord,
)

GENESIS_HASH = "0" * 64  # hash "before" the first record in any chain

# A session_factory is any zero-arg callable returning a SQLAlchemy Session
# (SessionLocal itself satisfies this). Injectable so tests can point at an
# isolated engine instead of the real shared database.
SessionFactory = Callable[[], DBSession]


# --------------------------------------------------------------------------
# Stage conversion — shared.enums.LogStage <-> database.models.AuditStage
# --------------------------------------------------------------------------
# Two distinct Enum classes for the same concept, same pattern Agent 2's
# vector_store.py already established for AccessLevel: convert explicitly
# at the DB boundary rather than relying on them comparing equal implicitly.

def _to_db_stage(stage: LogStage) -> DBAuditStage:
    return DBAuditStage(stage.value)


def _to_shared_stage(db_stage: DBAuditStage) -> LogStage:
    return LogStage(db_stage.value)


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
<<<<<<< Updated upstream
# File backend (original implementation, unchanged)
=======
# Storage — DB-backed
>>>>>>> Stashed changes
# --------------------------------------------------------------------------

def _db_row_to_record(row: DBAuditLog) -> AuditLogRecord:
    return AuditLogRecord(
        log_id=str(row.log_id),
        session_id=row.session_id,
        stage=_to_shared_stage(row.stage),
        agent=row.agent,
        payload_snapshot=row.payload_snapshot,
        decision_summary=row.decision_summary,
        timestamp=row.timestamp,
        immutable_hash=row.immutable_hash,
    )


def _get_last_hash(db: DBSession) -> str:
    last = db.query(DBAuditLog).order_by(DBAuditLog.id.desc()).first()
    return last.immutable_hash if last else GENESIS_HASH


def read_all_records(session_factory: SessionFactory = SessionLocal) -> list[AuditLogRecord]:
    """Reads every record currently in the chain, in append (id) order."""
    db = session_factory()
    try:
        rows = db.query(DBAuditLog).order_by(DBAuditLog.id.asc()).all()
        return [_db_row_to_record(r) for r in rows]
    finally:
        db.close()


<<<<<<< Updated upstream
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
=======
def read_records_for_session(
    session_id: str, session_factory: SessionFactory = SessionLocal
) -> list[AuditLogRecord]:
    """Convenience filter for "show me this session's audit trail" — NOT
    used for hash-chain verification, since verify_chain() needs the
    globally-ordered full chain to correctly recompute prev_hash links."""
    db = session_factory()
    try:
        rows = (
            db.query(DBAuditLog)
            .filter(DBAuditLog.session_id == session_id)
            .order_by(DBAuditLog.id.asc())
            .all()
        )
        return [_db_row_to_record(r) for r in rows]
    finally:
        db.close()
>>>>>>> Stashed changes


def verify_chain(
    session_factory: SessionFactory = SessionLocal,
) -> tuple[bool, list[dict]]:
    """Recomputes each record's hash from its content + the *previous
<<<<<<< Updated upstream
    record's stored hash* and compares it to what's on disk/in the DB.
=======
    record's stored hash* and compares it to what's on disk (now: the
    `immutable_hash` column). Also checks the stored `prev_hash` column
    itself against the previous row's actual immutable_hash — this is a
    real DB-only upgrade over the JSONL version: it catches a row whose
    prev_hash pointer doesn't match its true predecessor (e.g. rows
    reordered or a forged row spliced in), not just content tampering.
>>>>>>> Stashed changes

    Deliberately continues the chain using each record's *stored* hash
    (not the recomputed one) even after a mismatch — this isolates
    exactly which record(s) were altered, instead of every record after
    the first tampered one also showing as broken.

    Returns (is_intact, broken_records) where broken_records is a list of
<<<<<<< Updated upstream
    {"index", "log_id", "stage", "expected_hash", "actual_hash"} dicts —
    empty if the chain is fully intact. Backend-agnostic: driven entirely
    by read_all_records(), so it works identically for either backend.
=======
    {"index", "log_id", "stage", "expected_hash", "actual_hash",
    "prev_hash_mismatch"} dicts — empty if the chain is fully intact.
>>>>>>> Stashed changes
    """
    db = session_factory()
    try:
        rows = db.query(DBAuditLog).order_by(DBAuditLog.id.asc()).all()
    finally:
        db.close()

    prev_hash = GENESIS_HASH
    broken: list[dict] = []

    for i, row in enumerate(rows):
        record = _db_row_to_record(row)
        expected = compute_hash(record, prev_hash)

        content_ok = expected == row.immutable_hash
        pointer_ok = row.prev_hash == prev_hash

        if not content_ok or not pointer_ok:
            broken.append(
                {
                    "index": i,
                    "log_id": str(row.log_id),
                    "stage": row.stage.value,
                    "expected_hash": expected,
                    "actual_hash": row.immutable_hash,
                    "prev_hash_mismatch": not pointer_ok,
                }
            )

        prev_hash = row.immutable_hash

    return (len(broken) == 0, broken)


# --------------------------------------------------------------------------
# Per-agent convenience wrappers (unchanged — dispatch happens inside
# append_record, so these need no backend awareness at all)
# --------------------------------------------------------------------------

<<<<<<< Updated upstream
=======
def append_record(
    stage: LogStage,
    agent: str,
    session_id: str,
    payload_snapshot: dict,
    decision_summary: str,
    session_factory: SessionFactory = SessionLocal,
) -> AuditLogRecord:
    """Appends one audit record to the chain and returns it.

    `session_factory` is only for tests / isolated runs — production code
    should rely on the default (the real SessionLocal) so every stage
    writes to the same shared chain.
    """
    db = session_factory()
    try:
        prev_hash = _get_last_hash(db)

        record = AuditLogRecord(
            log_id=str(uuid4()),
            session_id=session_id,
            stage=stage,
            agent=agent,
            payload_snapshot=payload_snapshot,
            decision_summary=decision_summary,
            timestamp=datetime.now(timezone.utc),
            immutable_hash="",  # placeholder; _canonical_json excludes it anyway
        )
        record.immutable_hash = compute_hash(record, prev_hash)

        db_row = DBAuditLog(
            log_id=record.log_id,
            session_id=record.session_id,
            stage=_to_db_stage(stage),
            agent=agent,
            payload_snapshot=payload_snapshot,
            decision_summary=decision_summary,
            timestamp=record.timestamp,
            immutable_hash=record.immutable_hash,
            prev_hash=prev_hash,
        )
        db.add(db_row)
        db.commit()

        return record
    finally:
        db.close()


# --------------------------------------------------------------------------
# Per-agent convenience wrappers
# --------------------------------------------------------------------------
# pipeline.py calls these directly after each agent runs — one line per
# stage instead of hand-building payload_snapshot/decision_summary at
# every call site.

>>>>>>> Stashed changes
def log_classification(
    agent1_output: Agent1Output, session_factory: SessionFactory = SessionLocal
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
        session_factory=session_factory,
    )


def log_retrieval(
    agent2_output: Agent2Output, session_factory: SessionFactory = SessionLocal
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
        session_factory=session_factory,
    )


def log_generation(
    agent3_output: Agent3Output, session_factory: SessionFactory = SessionLocal
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
        session_factory=session_factory,
    )


def log_verification(
    agent4_output: Agent4Output, session_factory: SessionFactory = SessionLocal
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
        session_factory=session_factory,
    )


# --------------------------------------------------------------------------
# Manual smoke test — run with: python -m agent5_audit_logging.logger
<<<<<<< Updated upstream
# Always uses the file backend (explicit log_path), regardless of your
# .env AUDIT_LOG_BACKEND setting, so this stays a safe local sanity check.
# For a DB-backend smoke test, see tests/test_agent5/test_db_backend.py.
=======
#
# WARNING: this writes real rows to the shared production audit_log
# table (no session_factory override here — deliberately, to prove the
# real DB wiring works end to end). It does NOT tamper with or delete
# anything; it only appends 3 demo rows and verifies the chain.
>>>>>>> Stashed changes
# --------------------------------------------------------------------------

if __name__ == "__main__":
    print("Writing 3 demo records to the REAL audit_log table...\n")

    r1 = append_record(
        stage=LogStage.CLASSIFICATION,
        agent="agent1_classification",
        session_id="sess_demo_logger_smoketest",
        payload_snapshot={"intent": "procedure_lookup", "access_level": "public"},
        decision_summary="classified as procedure_lookup, access_level=public",
    )
    r2 = append_record(
        stage=LogStage.RETRIEVAL,
        agent="agent2_retrieval",
        session_id="sess_demo_logger_smoketest",
        payload_snapshot={"results": 5, "retrieval_confidence": "medium"},
        decision_summary="retrieved 5 chunks at medium confidence",
    )
    r3 = append_record(
        stage=LogStage.VERIFICATION,
        agent="agent4_verification",
        session_id="sess_demo_logger_smoketest",
        payload_snapshot={"decision": "approved", "confidence": 0.95},
        decision_summary="decision=approved confidence=0.95",
    )

<<<<<<< Updated upstream
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
=======
    ok, broken = verify_chain()
    print(f"Chain intact (whole table): {ok}")
    print(f"Total records in table: {len(read_all_records())}")
    print(f"This session's records: {len(read_records_for_session('sess_demo_logger_smoketest'))}")
    if not ok:
        print(f"Broken entries: {broken}")
>>>>>>> Stashed changes
