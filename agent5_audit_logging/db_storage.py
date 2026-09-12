"""
agent5_audit_logging/db_storage.py

Postgres-backed storage for Agent 5's hash-chained audit log — the
`audit_log` table (database/models.py). This is the production backend;
logger.py dispatches to either this or the original JSONL file backend
depending on config.AUDIT_LOG_BACKEND / whether an explicit log_path
override was passed to a given call.

Chain scope: GLOBAL across the whole audit_log table — one continuous
hash chain, same principle as the single-JSONL-file design it replaces,
just backed by row insertion (id) order instead of file line order.

Concurrency: two processes appending at the same instant could both read
"last hash = X" before either commits, and both insert a record chained
from X — silently breaking the tamper-evidence guarantee this whole
agent exists to provide. Fixed here with a Postgres advisory lock
(pg_advisory_xact_lock), held for the entire read-last-hash + insert
transaction, so appends serialize globally across every process talking
to this database. This also correctly handles the empty-table case (the
very first insert), which a row-level lock alone would miss since
there's no row yet to lock.
"""

import uuid as uuid_lib
from typing import Callable

from sqlalchemy import text

from database.config import SessionLocal
from database.models import AuditLog
from database.models import AuditStage as DBAuditStage
from shared.enums import LogStage
from shared.schemas import AuditLogRecord

GENESIS_HASH = "0" * 64

# Arbitrary fixed lock key — every append takes this same advisory lock,
# so appends serialize globally regardless of session_id. Hashed DB-side
# via hashtext() rather than relying on Python's hash() for strings,
# which is randomized per-process and unsafe for this purpose.
_CHAIN_LOCK_KEY = "bankkms_audit_log_chain"


_STAGE_TO_DB = {
    LogStage.CLASSIFICATION: DBAuditStage.CLASSIFICATION,
    LogStage.RETRIEVAL: DBAuditStage.RETRIEVAL,
    LogStage.GENERATION: DBAuditStage.GENERATION,
    LogStage.VERIFICATION: DBAuditStage.VERIFICATION,
}
_STAGE_FROM_DB = {v: k for k, v in _STAGE_TO_DB.items()}
# NOTE: database.models.AuditStage also defines ESCALATION, but
# shared.enums.LogStage does not — there's currently no LogStage value
# for a future Agent 6 hook to log under. Raising clearly below rather
# than silently coercing to some other stage; add LogStage.ESCALATION
# to shared/enums.py when Agent 6 is built, then extend the maps above.


def _to_db_stage(stage: LogStage) -> DBAuditStage:
    try:
        return _STAGE_TO_DB[stage]
    except KeyError:
        raise ValueError(
            f"No DB AuditStage mapping for LogStage={stage!r}. If this is "
            "meant to represent an escalation event, LogStage.ESCALATION "
            "doesn't exist yet in shared/enums.py — add it there first."
        )


def _from_db_stage(stage: DBAuditStage) -> LogStage:
    try:
        return _STAGE_FROM_DB[stage]
    except KeyError:
        raise ValueError(
            f"DB AuditStage={stage!r} has no corresponding shared.enums.LogStage "
            "(e.g. ESCALATION) — a record with this stage can't round-trip "
            "through Agent 5 until that enum value exists on the shared side."
        )


def db_append_atomic(build_record: Callable[[str], AuditLogRecord]) -> AuditLogRecord:
    """
    Atomically: acquire the global chain lock -> read the TRUE last hash
    -> ask the caller to build the record (computing immutable_hash
    against that exact prev_hash) -> insert -> commit (releases the
    lock).

    `build_record` is (prev_hash: str) -> AuditLogRecord, with
    immutable_hash already computed against that prev_hash. Taking a
    callback rather than a finished record is what actually closes the
    race: the hash is computed AFTER the lock is held and the real
    prev_hash is known, not before.
    """
    db = SessionLocal()
    try:
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": _CHAIN_LOCK_KEY},
        )

        last = (
            db.query(AuditLog.immutable_hash)
            .order_by(AuditLog.id.desc())
            .first()
        )
        prev_hash = last[0] if last else GENESIS_HASH

        record = build_record(prev_hash)

        row = AuditLog(
            log_id=uuid_lib.UUID(record.log_id),
            session_id=record.session_id,
            stage=_to_db_stage(record.stage),
            agent=record.agent,
            payload_snapshot=record.payload_snapshot,
            decision_summary=record.decision_summary,
            timestamp=record.timestamp,
            immutable_hash=record.immutable_hash,
            prev_hash=prev_hash,
        )
        db.add(row)
        db.commit()
        return record
    finally:
        db.close()


def db_read_all() -> list[AuditLogRecord]:
    """Reads every record in the global chain, in insertion (id) order."""
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
        return [
            AuditLogRecord(
                log_id=str(row.log_id),
                session_id=row.session_id,
                stage=_from_db_stage(row.stage),
                agent=row.agent,
                payload_snapshot=row.payload_snapshot,
                decision_summary=row.decision_summary,
                timestamp=row.timestamp,
                immutable_hash=row.immutable_hash,
            )
            for row in rows
        ]
    finally:
        db.close()


def db_delete_by_log_ids(log_ids: list[str]) -> None:
    """TEST-CLEANUP HELPER ONLY. Deletes specific rows by log_id.

    Safe only when the deleted rows are the most-recently-appended ones
    in the chain at the time of deletion (append-only cleanup). Deleting
    from the middle of a chain that other rows were appended after would
    make those later rows fail verify_chain() — they'd still declare a
    prev_hash pointing at a hash that, from the surviving rows'
    perspective, no longer precedes them in iteration order. See
    tests/test_agent5/test_db_backend.py for the safe usage pattern
    (track log_ids as you append, delete them right after asserting).
    """
    db = SessionLocal()
    try:
        db.query(AuditLog).filter(
            AuditLog.log_id.in_([uuid_lib.UUID(lid) for lid in log_ids])
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()