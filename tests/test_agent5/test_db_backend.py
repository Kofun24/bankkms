"""
tests/test_agent5/test_db_backend.py

Tests specifically for the "db" storage backend (agent5_audit_logging/
db_storage.py) — separate from the existing file-backend test files,
which are untouched and still run with zero DB dependency.

Requires a real DATABASE_URL in .env, since these hit the actual
Postgres `audit_log` table. Run just these with:

    python -m pytest tests/test_agent5/test_db_backend.py -v

Cleanup pattern: the chain is GLOBAL (one continuous hash chain across
the whole table, not scoped per test/session), so tests can't assume an
empty table the way file-backend tests assume an empty file. Instead:
  1. Capture whatever the chain's current state is before the test.
  2. Append records, assert they correctly continue FROM that state
     (not from GENESIS_HASH).
  3. Delete exactly the rows this test added, by log_id, immediately
     after — see db_storage.db_delete_by_log_ids()'s docstring for why
     this is only safe for append-then-immediately-clean-up, not for
     deleting older rows out of a chain other things have since built on.
"""

import uuid

import pytest
from sqlalchemy import text

from agent5_audit_logging.db_storage import (
    GENESIS_HASH,
    db_append_atomic,
    db_delete_by_log_ids,
    db_read_all,
)
from agent5_audit_logging.logger import compute_hash
from database.config import SessionLocal
from shared.enums import LogStage
from shared.schemas import AuditLogRecord


def _test_session_id() -> str:
    return f"test_db5_{uuid.uuid4().hex[:8]}"


def _append_test_record(stage, agent, session_id, payload, summary) -> AuditLogRecord:
    def _build(prev_hash: str) -> AuditLogRecord:
        record = AuditLogRecord(
            log_id=str(uuid.uuid4()),
            session_id=session_id,
            stage=stage,
            agent=agent,
            payload_snapshot=payload,
            decision_summary=summary,
            immutable_hash="",
        )
        record.immutable_hash = compute_hash(record, prev_hash)
        return record

    return db_append_atomic(_build)


@pytest.fixture
def track_log_ids():
    """Collects log_ids appended during a test; deletes exactly those
    rows afterward (append-then-cleanup pattern -- see module docstring)."""
    ids: list[str] = []
    yield ids
    if ids:
        db_delete_by_log_ids(ids)


def _current_last_hash() -> str:
    """Reads whatever the chain's last hash currently is, without
    holding the advisory lock -- just for test assertions, not for
    driving an actual append (db_append_atomic does that safely itself)."""
    records = db_read_all()
    return records[-1].immutable_hash if records else GENESIS_HASH


def test_first_append_chains_from_whatever_the_current_last_hash_is(track_log_ids):
    """Unlike the file backend's per-test-isolated empty file, the DB
    chain is global -- a fresh append must chain from the table's TRUE
    current last hash, not assume GENESIS_HASH."""
    baseline = _current_last_hash()
    session_id = _test_session_id()

    record = _append_test_record(
        LogStage.CLASSIFICATION, "agent1_classification", session_id,
        {"intent": "procedure_lookup"}, "test record",
    )
    track_log_ids.append(record.log_id)

    assert record.immutable_hash == compute_hash(record, baseline)


def test_second_append_chains_from_first_append_within_same_test(track_log_ids):
    session_id = _test_session_id()

    r1 = _append_test_record(
        LogStage.CLASSIFICATION, "agent1_classification", session_id, {"n": 1}, "first",
    )
    r2 = _append_test_record(
        LogStage.RETRIEVAL, "agent2_retrieval", session_id, {"n": 2}, "second",
    )
    track_log_ids.extend([r1.log_id, r2.log_id])

    assert r2.immutable_hash == compute_hash(r2, r1.immutable_hash)


def test_db_read_all_returns_appended_record_with_correct_content(track_log_ids):
    session_id = _test_session_id()
    payload = {"nested": {"a": 1, "b": [1, 2, 3]}, "flag": True}

    record = _append_test_record(
        LogStage.VERIFICATION, "agent4_verification", session_id, payload, "approved",
    )
    track_log_ids.append(record.log_id)

    all_records = db_read_all()
    match = next(r for r in all_records if r.log_id == record.log_id)

    assert match.session_id == session_id
    assert match.stage == LogStage.VERIFICATION
    assert match.agent == "agent4_verification"
    assert match.payload_snapshot == payload
    assert match.decision_summary == "approved"
    assert match.immutable_hash == record.immutable_hash


def test_all_four_stages_round_trip_correctly(track_log_ids):
    session_id = _test_session_id()
    stages_and_agents = [
        (LogStage.CLASSIFICATION, "agent1_classification"),
        (LogStage.RETRIEVAL, "agent2_retrieval"),
        (LogStage.GENERATION, "agent3_response"),
        (LogStage.VERIFICATION, "agent4_verification"),
    ]

    appended = []
    for stage, agent in stages_and_agents:
        r = _append_test_record(stage, agent, session_id, {}, f"{stage.value} record")
        appended.append(r)
        track_log_ids.append(r.log_id)

    all_records = db_read_all()
    for expected in appended:
        match = next(r for r in all_records if r.log_id == expected.log_id)
        assert match.stage == expected.stage
        assert match.agent == expected.agent


def test_tampering_a_db_record_is_detected_by_verify_chain(track_log_ids, monkeypatch):
    """Directly UPDATEs a row's decision_summary (simulating someone
    editing the table by hand or a compromised process), then confirms
    verify_chain (via read_all_records, driven by the db backend) flags
    it. Forces AUDIT_LOG_BACKEND to 'db' for the duration of this test
    only, since verify_chain()/read_all_records() dispatch on that
    config value when no explicit log_path is given."""
    import agent5_audit_logging.logger as logger_module
    monkeypatch.setattr(logger_module, "AUDIT_LOG_BACKEND", "db")

    session_id = _test_session_id()
    record = _append_test_record(
        LogStage.GENERATION, "agent3_response", session_id, {}, "original",
    )
    track_log_ids.append(record.log_id)

    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE audit_log SET decision_summary = :s WHERE log_id = :id"),
            {"s": "TAMPERED", "id": record.log_id},
        )
        db.commit()
    finally:
        db.close()

    ok, broken = logger_module.verify_chain()

    assert ok is False
    assert any(b["log_id"] == record.log_id for b in broken)


def test_db_delete_by_log_ids_removes_exactly_those_rows():
    session_id = _test_session_id()
    r1 = _append_test_record(LogStage.CLASSIFICATION, "agent1_classification", session_id, {}, "a")
    r2 = _append_test_record(LogStage.RETRIEVAL, "agent2_retrieval", session_id, {}, "b")

    db_delete_by_log_ids([r1.log_id, r2.log_id])

    remaining = db_read_all()
    remaining_ids = {r.log_id for r in remaining}
    assert r1.log_id not in remaining_ids
    assert r2.log_id not in remaining_ids