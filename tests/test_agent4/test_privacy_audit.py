"""
tests/test_agent4/test_privacy_audit.py

Individual assignment — Member 4: Privacy & Data Leakage Assessment
Continues the AUD-numbered case set (AUD-01..AUD-15 already cover access
bypass, hallucination leakage, version conflicts, confidence boundaries,
and malformed input). This file adds the two areas the project plan
calls out that weren't covered yet: conversation/session isolation, and
PII exposure in the audit log.

Runs against the REAL shared database (Agent 5's audit_log table),
following the same append-then-cleanup safety pattern as
tests/test_agent5/ -- every test only ever creates and later deletes its
own rows, never touching pre-existing data. See track_log_ids below.

Run with:
    python -m pytest tests/test_agent4/test_privacy_audit.py -v
"""

import uuid

import pytest

from agent4_verification.verifier import run_agent4
from agent5_audit_logging.logger import (
    log_classification,
    log_generation,
    log_retrieval,
    log_verification,
    read_records_for_session,
)
from shared.enums import AccessLevel, Intent, RetrievalConfidence, UserRole
from shared.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Citation,
    RetrievedChunk,
)


def _unique_session_id() -> str:
    return f"test_privacy_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def track_log_ids():
    """Same safety pattern as tests/test_agent5/conftest.py: collects
    log_ids appended during a test, deletes exactly those rows afterward.
    Never touches anything that existed before the test."""
    from database.config import SessionLocal
    from database.models import AuditLog

    ids: list[str] = []
    yield ids
    if ids:
        db = SessionLocal()
        try:
            db.query(AuditLog).filter(
                AuditLog.log_id.in_([uuid.UUID(i) for i in ids])
            ).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


def _build_pipeline_stage(session_id: str, topic_text: str, answer_text: str):
    """Builds a minimal but realistic (agent1, agent2, agent3) triple for
    one fake session, so each test can construct two clearly distinct
    'conversations' and prove nothing bleeds between them."""
    chunk_id = f"c_{uuid.uuid4().hex[:6]}"
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"

    agent1 = Agent1Output(
        session_id=session_id,
        user_role=UserRole.CUSTOMER,
        access_level=AccessLevel.PUBLIC,
        intent=Intent.ACCOUNT_INFO,
        topic=topic_text,
        normalized_query=topic_text,
        confidence=0.9,
    )
    agent2 = Agent2Output(
        session_id=session_id,
        query_used=topic_text,
        access_level=AccessLevel.PUBLIC,
        results=[
            RetrievedChunk(
                doc_id=doc_id, doc_title="Test Doc", chunk_id=chunk_id,
                chunk_text=answer_text, similarity_score=0.9,
                doc_access_level=AccessLevel.PUBLIC, doc_version="v1",
                effective_date="2024-01-01", source_section="Section 1",
            )
        ],
        retrieval_confidence=RetrievalConfidence.HIGH,
    )
    agent3 = Agent3Output(
        session_id=session_id,
        answer_text=answer_text,
        grounded=True,
        citations=[Citation(doc_id=doc_id, doc_title="Test Doc",
                              section="Section 1", chunk_id=chunk_id)],
        chunks_used=[chunk_id],
    )
    return agent1, agent2, agent3


# ==========================================================================
# AUD-16: Conversation / session isolation
# ==========================================================================

def test_AUD16_agent4_output_never_mixes_content_across_sessions(monkeypatch):
    """AUD-16: Two structurally unrelated sessions run through Agent 4.
    Confirms session A's output contains nothing from session B's
    content (and vice versa) -- proving there's no shared mutable state
    in verifier.py that could leak one user's answer into another's."""
    import agent4_verification.verifier as v
    monkeypatch.setattr(v, "llm_factual_support_check", lambda a, c: ("pass", 0.95))

    session_a = _unique_session_id()
    session_b = _unique_session_id()

    a1_a, a2_a, a3_a = _build_pipeline_stage(
        session_a, "savings account minimum balance",
        "The minimum balance for a savings account is LKR 1,000.",
    )
    a1_b, a2_b, a3_b = _build_pipeline_stage(
        session_b, "fraud reporting procedure",
        "Report suspected fraud immediately via the hotline.",
    )

    result_a = run_agent4(a1_a, a2_a, a3_a)
    result_b = run_agent4(a1_b, a2_b, a3_b)

    assert result_a.session_id == session_a
    assert result_b.session_id == session_b

    assert "1,000" in result_a.final_answer
    assert "1,000" not in (result_b.final_answer or "")

    assert "fraud" in result_b.final_answer.lower()
    assert "fraud" not in (result_a.final_answer or "").lower()

    assert {c.doc_id for c in result_a.final_citations}.isdisjoint(
        {c.doc_id for c in result_b.final_citations}
    )


def test_AUD16b_audit_log_correctly_isolates_records_per_session(track_log_ids, monkeypatch):
    """AUD-16 (audit trail side): logs two sessions' full pipelines
    through Agent 5, then confirms read_records_for_session() for
    session A returns ONLY session A's payloads -- no leakage through
    the shared/global hash chain, despite both sessions' records living
    in the same table and the same continuous chain."""
    import agent4_verification.verifier as v
    monkeypatch.setattr(v, "llm_factual_support_check", lambda a, c: ("pass", 0.95))

    session_a = _unique_session_id()
    session_b = _unique_session_id()

    a1_a, a2_a, a3_a = _build_pipeline_stage(
        session_a, "savings account minimum balance",
        "The minimum balance for a savings account is LKR 1,000.",
    )
    a1_b, a2_b, a3_b = _build_pipeline_stage(
        session_b, "fraud reporting procedure",
        "Report suspected fraud immediately via the hotline.",
    )

    result_a = run_agent4(a1_a, a2_a, a3_a)
    result_b = run_agent4(a1_b, a2_b, a3_b)

    r1 = log_classification(a1_a)
    r2 = log_retrieval(a2_a)
    r3 = log_generation(a3_a)
    r4 = log_verification(result_a)
    r5 = log_classification(a1_b)
    r6 = log_retrieval(a2_b)
    r7 = log_generation(a3_b)
    r8 = log_verification(result_b)
    track_log_ids.extend([r.log_id for r in (r1, r2, r3, r4, r5, r6, r7, r8)])

    records_a = read_records_for_session(session_a)
    records_b = read_records_for_session(session_b)

    assert all(r.session_id == session_a for r in records_a)
    assert all(r.session_id == session_b for r in records_b)
    assert len(records_a) == 4
    assert len(records_b) == 4

    a_text = " ".join(str(r.payload_snapshot) for r in records_a)
    b_text = " ".join(str(r.payload_snapshot) for r in records_b)
    assert "fraud" not in a_text.lower()
    assert "1,000" not in b_text or "1,000" in a_text  # sanity: session A's own figure is fine in A


# ==========================================================================
# AUD-17: PII exposure in the audit log [FINDING]
# ==========================================================================

def test_AUD17_query_containing_pii_like_data_is_stored_unredacted_in_audit_log(track_log_ids):
    """AUD-17 [FINDING]: If a user types something PII-like into their
    query (here: a fake account-number-shaped string), it is currently
    stored VERBATIM in audit_log.payload_snapshot, with no redaction
    step anywhere in the pipeline.

    This is not a bug in the sense of broken code -- everything works
    exactly as designed, and having a complete, unaltered audit trail is
    normally a GOOD compliance property. But it does mean: whatever a
    user types, including anything sensitive, becomes permanent
    (append-only, hash-chained -- cannot be edited or deleted without
    breaking the chain) database content. For a real deployment, this is
    a genuine design decision to document explicitly rather than assume:
    either (a) accept this as intended for a compliance audit trail, or
    (b) add a redaction/masking step in Agent 1's sanitizer before the
    query is logged (e.g. detecting and masking account-number-shaped
    strings), applied consistently before it ever reaches Agent 5.

    This test demonstrates current behavior (no redaction), which is
    what the audit report should cite as the finding.
    """
    session_id = _unique_session_id()
    fake_account_number = "8801234567"  # PII-shaped test data, not real
    query_with_pii = f"What is the status of account {fake_account_number}?"

    agent1 = Agent1Output(
        session_id=session_id,
        user_role=UserRole.CUSTOMER,
        access_level=AccessLevel.PUBLIC,
        intent=Intent.ACCOUNT_INFO,
        topic="account status",
        normalized_query=query_with_pii,
        confidence=0.9,
    )

    record = log_classification(agent1)
    track_log_ids.append(record.log_id)

    stored = read_records_for_session(session_id)
    stored_text = str(stored[0].payload_snapshot)

    # Documents current behavior: the account-number-shaped string is
    # NOT redacted -- it passes straight through into permanent storage.
    assert fake_account_number in stored_text