"""
Agent 5 — hashing primitives.

`compute_hash` must be a deterministic function of (record content minus
immutable_hash, prev_hash) -- same inputs always produce the same hash,
and changing either input changes the output. This is the property the
whole tamper-detection scheme in verify_chain() relies on.
"""

from agent5_audit_logging.logger import GENESIS_HASH, compute_hash
from shared.enums import LogStage
from shared.schemas import AuditLogRecord


def _record(**overrides):
    defaults = dict(
        log_id="fixed-log-id",
        session_id="sess_test",
        stage=LogStage.CLASSIFICATION,
        agent="agent1_classification",
        payload_snapshot={"intent": "procedure_lookup"},
        decision_summary="classified",
        immutable_hash="",
    )
    defaults.update(overrides)
    return AuditLogRecord(**defaults)


def test_genesis_hash_is_64_hex_chars_of_zero():
    assert GENESIS_HASH == "0" * 64
    assert len(GENESIS_HASH) == 64


def test_compute_hash_is_deterministic():
    record = _record()
    h1 = compute_hash(record, GENESIS_HASH)
    h2 = compute_hash(record, GENESIS_HASH)
    assert h1 == h2


def test_compute_hash_is_a_valid_sha256_hex_digest():
    record = _record()
    h = compute_hash(record, GENESIS_HASH)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_compute_hash_ignores_the_immutable_hash_field_itself():
    """The hash is computed over the record's content minus
    immutable_hash -- so changing ONLY that field on a record (with
    everything else, including its timestamp, held fixed) must not
    change the computed hash.

    Mutates a single record in place rather than building two separate
    records -- two separate _record() calls would each get their own
    default_factory timestamp a few microseconds apart, which would
    change the hash for a reason unrelated to immutable_hash and mask
    what this test is actually checking."""
    record = _record(immutable_hash="")
    hash_before = compute_hash(record, GENESIS_HASH)

    record.immutable_hash = "some-stale-placeholder-value"
    hash_after = compute_hash(record, GENESIS_HASH)

    assert hash_before == hash_after


def test_compute_hash_changes_when_payload_changes():
    record_a = _record(payload_snapshot={"intent": "procedure_lookup"})
    record_b = _record(payload_snapshot={"intent": "policy_check"})
    assert compute_hash(record_a, GENESIS_HASH) != compute_hash(record_b, GENESIS_HASH)


def test_compute_hash_changes_when_decision_summary_changes():
    record_a = _record(decision_summary="classified as A")
    record_b = _record(decision_summary="classified as B")
    assert compute_hash(record_a, GENESIS_HASH) != compute_hash(record_b, GENESIS_HASH)


def test_compute_hash_changes_when_prev_hash_changes():
    record = _record()
    h_genesis = compute_hash(record, GENESIS_HASH)
    h_other = compute_hash(record, "1" * 64)
    assert h_genesis != h_other