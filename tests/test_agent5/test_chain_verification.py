"""
Agent 5 — verify_chain tamper detection.

This is the core "immutability" guarantee: verify_chain() must report a
clean chain as intact, and must detect + pinpoint any record altered on
disk after the fact. It must isolate the tampered record rather than
flagging every record after it, and it must also catch a deleted record
(which breaks the chain differently -- the next record's prev_hash no
longer matches anything).
"""

import json

from agent5_audit_logging.logger import _read_lines, append_record, verify_chain
from shared.enums import LogStage


def _append_three(log_path):
    r1 = append_record(
        stage=LogStage.CLASSIFICATION, agent="agent1_classification",
        session_id="sess_test", payload_snapshot={"n": 1}, decision_summary="first",
        log_path=log_path,
    )
    r2 = append_record(
        stage=LogStage.RETRIEVAL, agent="agent2_retrieval",
        session_id="sess_test", payload_snapshot={"n": 2}, decision_summary="second",
        log_path=log_path,
    )
    r3 = append_record(
        stage=LogStage.GENERATION, agent="agent3_response",
        session_id="sess_test", payload_snapshot={"n": 3}, decision_summary="third",
        log_path=log_path,
    )
    return r1, r2, r3


def test_empty_log_verifies_as_intact(log_path):
    """log_path points at a file that doesn't exist yet -- an empty
    chain is trivially intact."""
    ok, broken = verify_chain(log_path)
    assert ok is True
    assert broken == []


def test_single_record_chain_verifies_as_intact(log_path):
    append_record(
        stage=LogStage.CLASSIFICATION, agent="agent1_classification",
        session_id="sess_test", payload_snapshot={}, decision_summary="only record",
        log_path=log_path,
    )
    ok, broken = verify_chain(log_path)
    assert ok is True
    assert broken == []


def test_clean_multi_record_chain_verifies_as_intact(log_path):
    _append_three(log_path)
    ok, broken = verify_chain(log_path)
    assert ok is True
    assert broken == []


def test_tampering_with_middle_record_is_detected(log_path):
    _append_three(log_path)

    lines = _read_lines(log_path)
    tampered = json.loads(lines[1])
    tampered["decision_summary"] = "TAMPERED"
    lines[1] = json.dumps(tampered)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    ok, broken = verify_chain(log_path)

    assert ok is False
    assert len(broken) == 1
    assert broken[0]["index"] == 1
    assert broken[0]["stage"] == "retrieval"


def test_tampering_isolates_to_the_altered_record_only(log_path):
    """Records before and after the tampered one, which were never
    touched, must NOT show up in broken -- verify_chain continues the
    chain using each record's stored hash, not the recomputed one, so a
    single alteration doesn't cascade into false positives downstream."""
    _append_three(log_path)

    lines = _read_lines(log_path)
    tampered = json.loads(lines[1])
    tampered["decision_summary"] = "TAMPERED"
    lines[1] = json.dumps(tampered)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    ok, broken = verify_chain(log_path)

    broken_indices = {b["index"] for b in broken}
    assert 0 not in broken_indices
    assert 2 not in broken_indices
    assert broken_indices == {1}


def test_tampering_with_first_record_is_detected(log_path):
    _append_three(log_path)

    lines = _read_lines(log_path)
    tampered = json.loads(lines[0])
    tampered["payload_snapshot"] = {"n": 999}
    lines[0] = json.dumps(tampered)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    ok, broken = verify_chain(log_path)

    assert ok is False
    assert broken[0]["index"] == 0


def test_deleting_a_record_breaks_the_chain(log_path):
    """Removing a record from the middle means the next record's
    prev_hash (baked into its own immutable_hash) no longer matches
    anything real -- this must also be caught, not silently accepted as
    a shorter-but-valid chain."""
    _append_three(log_path)

    lines = _read_lines(log_path)
    del lines[1]  # remove the middle record entirely
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    ok, broken = verify_chain(log_path)

    assert ok is False
    assert len(broken) >= 1


def test_broken_record_report_includes_expected_and_actual_hash(log_path):
    _append_three(log_path)

    lines = _read_lines(log_path)
    tampered = json.loads(lines[2])
    tampered["decision_summary"] = "TAMPERED"
    lines[2] = json.dumps(tampered)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    ok, broken = verify_chain(log_path)

    assert ok is False
    entry = broken[0]
    assert "expected_hash" in entry
    assert "actual_hash" in entry
    assert entry["expected_hash"] != entry["actual_hash"]