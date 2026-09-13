"""
Agent 5 — append_record / read_all_records.

Covers the basic storage contract: appending writes a well-formed,
correctly-chained record; reading returns records in append order;
log_ids are unique; reading a log that doesn't exist yet returns an
empty list rather than raising.
"""

from shared.enums import LogStage

from agent5_audit_logging.logger import (
    GENESIS_HASH,
    append_record,
    compute_hash,
    read_all_records,
)


def test_first_record_chains_from_genesis_hash(log_path):
    record = append_record(
        stage=LogStage.CLASSIFICATION,
        agent="agent1_classification",
        session_id="sess_test",
        payload_snapshot={"intent": "procedure_lookup"},
        decision_summary="classified",
        log_path=log_path,
    )
    assert record.immutable_hash == compute_hash(record, GENESIS_HASH)


def test_second_record_chains_from_first_records_hash(log_path):
    first = append_record(
        stage=LogStage.CLASSIFICATION, agent="agent1_classification",
        session_id="sess_test", payload_snapshot={}, decision_summary="first",
        log_path=log_path,
    )
    second = append_record(
        stage=LogStage.RETRIEVAL, agent="agent2_retrieval",
        session_id="sess_test", payload_snapshot={}, decision_summary="second",
        log_path=log_path,
    )
    assert second.immutable_hash == compute_hash(second, first.immutable_hash)


def test_read_all_records_returns_records_in_append_order(log_path):
    append_record(
        stage=LogStage.CLASSIFICATION, agent="agent1_classification",
        session_id="sess_test", payload_snapshot={}, decision_summary="first",
        log_path=log_path,
    )
    append_record(
        stage=LogStage.RETRIEVAL, agent="agent2_retrieval",
        session_id="sess_test", payload_snapshot={}, decision_summary="second",
        log_path=log_path,
    )
    append_record(
        stage=LogStage.GENERATION, agent="agent3_response",
        session_id="sess_test", payload_snapshot={}, decision_summary="third",
        log_path=log_path,
    )

    records = read_all_records(log_path)

    assert [r.decision_summary for r in records] == ["first", "second", "third"]
    assert [r.stage for r in records] == [
        LogStage.CLASSIFICATION, LogStage.RETRIEVAL, LogStage.GENERATION,
    ]


def test_log_ids_are_unique_across_appends(log_path):
    for i in range(5):
        append_record(
            stage=LogStage.CLASSIFICATION, agent="agent1_classification",
            session_id="sess_test", payload_snapshot={}, decision_summary=f"record {i}",
            log_path=log_path,
        )
    records = read_all_records(log_path)
    log_ids = {r.log_id for r in records}
    assert len(log_ids) == 5


def test_read_all_records_on_nonexistent_file_returns_empty_list(log_path):
    """log_path is a fresh tmp_path that nothing has written to yet."""
    assert read_all_records(log_path) == []


def test_payload_snapshot_round_trips_through_storage(log_path):
    payload = {"nested": {"a": 1, "b": [1, 2, 3]}, "flag": True, "note": None}
    append_record(
        stage=LogStage.VERIFICATION, agent="agent4_verification",
        session_id="sess_test", payload_snapshot=payload, decision_summary="approved",
        log_path=log_path,
    )
    records = read_all_records(log_path)
    assert records[0].payload_snapshot == payload