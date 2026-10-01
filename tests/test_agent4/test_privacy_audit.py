"""
tests/test_agent4/test_privacy_audit.py

Individual Assignment — Member 4
Privacy & Data Leakage Assessment

This file contains exactly 15 AUD test cases:

AUD-01  Authorized public access
AUD-02  Internal session accessing public document
AUD-03  Restricted session accessing internal document
AUD-04  Public session blocked from internal document
AUD-05  Public session blocked from restricted document
AUD-06  Internal session blocked from restricted document
AUD-07  Missing / forged citation blocked
AUD-08  Agent 3 / Agent 2 citation mismatch blocked
AUD-09  Insufficient evidence blocked
AUD-10  Low factual confidence handled safely
AUD-11  Conversation / session isolation
AUD-12  Audit-log session isolation
AUD-13  PII exposure in audit log
AUD-14  Version conflict detection
AUD-15  Malformed / non-existent chunk handled safely

Run only the 15 privacy tests:

    python -m pytest tests/test_agent4/test_privacy_audit.py -v -s

Run one AUD test:

    python -m pytest tests/test_agent4/test_privacy_audit.py -v -s -k AUD-05
"""

from __future__ import annotations

import uuid

import pytest

from agent4_verification.verifier import (
    check_access_reconfirm,
    check_evidence_sufficiency,
    check_factual_support,
    check_version_conflict,
    llm_factual_support_check,
    run_agent4,
)

from agent5_audit_logging.logger import (
    log_classification,
    log_generation,
    log_retrieval,
    log_verification,
    read_records_for_session,
)

from shared.enums import (
    AccessLevel,
    EvidenceSufficiency,
    FactualSupportCheck,
    Intent,
    RetrievalConfidence,
    UserRole,
)

from shared.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Citation,
    RetrievedChunk,
)


# ==========================================================================
# Helper functions
# ==========================================================================

def _unique_session_id() -> str:
    """
    Generate an isolated session ID for each privacy test.
    """
    return f"test_privacy_{uuid.uuid4().hex[:8]}"


def _build_pipeline_stage(
    session_id: str,
    topic_text: str,
    answer_text: str,
):
    """
    Build a realistic Agent 1 → Agent 2 → Agent 3 pipeline state.

    Each call creates a unique document and chunk so that two sessions
    cannot accidentally share identifiers.
    """

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
                doc_id=doc_id,
                doc_title="Test Doc",
                chunk_id=chunk_id,
                chunk_text=answer_text,
                similarity_score=0.9,
                doc_access_level=AccessLevel.PUBLIC,
                doc_version="v1",
                effective_date="2024-01-01",
                source_section="Section 1",
            )
        ],
        retrieval_confidence=RetrievalConfidence.HIGH,
    )

    agent3 = Agent3Output(
        session_id=session_id,
        answer_text=answer_text,
        grounded=True,
        citations=[
            Citation(
                doc_id=doc_id,
                doc_title="Test Doc",
                section="Section 1",
                chunk_id=chunk_id,
            )
        ],
        chunks_used=[chunk_id],
    )

    return agent1, agent2, agent3


@pytest.fixture
def track_log_ids():
    """
    Track only the audit-log records created by the current test.

    After the test finishes, those records are removed.

    Existing database records are never deleted.
    """

    from database.config import SessionLocal
    from database.models import AuditLog

    ids: list[str] = []

    yield ids

    if ids:

        db = SessionLocal()

        try:

            db.query(AuditLog).filter(
                AuditLog.log_id.in_(
                    [uuid.UUID(i) for i in ids]
                )
            ).delete(
                synchronize_session=False
            )

            db.commit()

        finally:
            db.close()


# ==========================================================================
# AUD-01
# ==========================================================================

def test_AUD01_authorized_public_access_is_allowed(
    make_chunk,
    make_citation,
    make_agent3_output,
):
    """
    AUD-01: Confirms that a public session can access a public document
    when the citation and retrieved chunk are valid.
    """

    chunk = make_chunk(
        doc_id="aud01_public_doc",
        chunk_id="aud01_chunk",
        doc_access_level=AccessLevel.PUBLIC,
    )

    citation = make_citation(
        doc_id="aud01_public_doc",
        chunk_id="aud01_chunk",
    )

    agent3 = make_agent3_output(
        citations=[citation],
        chunks_used=["aud01_chunk"],
    )

    lookup = {
        "aud01_chunk": chunk,
    }

    ok, violations = check_access_reconfirm(
        AccessLevel.PUBLIC,
        agent3,
        lookup,
    )

    assert ok is True
    assert violations == []


# ==========================================================================
# AUD-02
# ==========================================================================

def test_AUD02_internal_session_can_access_public_document(
    make_chunk,
    make_citation,
    make_agent3_output,
):
    """
    AUD-02: Confirms that an internal-authorized session can access a
    lower-tier public document without triggering an access violation.
    """

    chunk = make_chunk(
        doc_id="aud02_public_doc",
        chunk_id="aud02_chunk",
        doc_access_level=AccessLevel.PUBLIC,
    )

    citation = make_citation(
        doc_id="aud02_public_doc",
        chunk_id="aud02_chunk",
    )

    agent3 = make_agent3_output(
        citations=[citation],
        chunks_used=["aud02_chunk"],
    )

    lookup = {
        "aud02_chunk": chunk,
    }

    ok, violations = check_access_reconfirm(
        AccessLevel.INTERNAL,
        agent3,
        lookup,
    )

    assert ok is True
    assert violations == []


# ==========================================================================
# AUD-03
# ==========================================================================

def test_AUD03_restricted_session_can_access_internal_document(
    make_chunk,
    make_citation,
    make_agent3_output,
):
    """
    AUD-03: Confirms that a restricted-authorized session can access an
    internal document because the session has a higher authorization tier.
    """

    chunk = make_chunk(
        doc_id="aud03_internal_doc",
        chunk_id="aud03_chunk",
        doc_access_level=AccessLevel.INTERNAL,
    )

    citation = make_citation(
        doc_id="aud03_internal_doc",
        chunk_id="aud03_chunk",
    )

    agent3 = make_agent3_output(
        citations=[citation],
        chunks_used=["aud03_chunk"],
    )

    lookup = {
        "aud03_chunk": chunk,
    }

    ok, violations = check_access_reconfirm(
        AccessLevel.RESTRICTED,
        agent3,
        lookup,
    )

    assert ok is True
    assert violations == []


# ==========================================================================
# AUD-04
# ==========================================================================

def test_AUD04_public_session_is_blocked_from_internal_document(
    make_chunk,
    make_citation,
    make_agent3_output,
):
    """
    AUD-04: Attempts to expose an internal document to a public session.
    Agent 4 must detect the access violation and block the document.
    """

    chunk = make_chunk(
        doc_id="aud04_internal_doc",
        chunk_id="aud04_chunk",
        doc_access_level=AccessLevel.INTERNAL,
    )

    citation = make_citation(
        doc_id="aud04_internal_doc",
        chunk_id="aud04_chunk",
    )

    agent3 = make_agent3_output(
        citations=[citation],
        chunks_used=["aud04_chunk"],
    )

    lookup = {
        "aud04_chunk": chunk,
    }

    ok, violations = check_access_reconfirm(
        AccessLevel.PUBLIC,
        agent3,
        lookup,
    )

    assert ok is False
    assert violations == ["aud04_internal_doc"]


# ==========================================================================
# AUD-05
# ==========================================================================

def test_AUD05_public_session_is_blocked_from_restricted_document(
    make_chunk,
    make_citation,
    make_agent3_output,
):
    """
    AUD-05: Attempts to expose a restricted document to a public session.
    This is a direct restricted-document leakage test and must be blocked.
    """

    chunk = make_chunk(
        doc_id="aud05_restricted_doc",
        chunk_id="aud05_chunk",
        doc_access_level=AccessLevel.RESTRICTED,
    )

    citation = make_citation(
        doc_id="aud05_restricted_doc",
        chunk_id="aud05_chunk",
    )

    agent3 = make_agent3_output(
        citations=[citation],
        chunks_used=["aud05_chunk"],
    )

    lookup = {
        "aud05_chunk": chunk,
    }

    ok, violations = check_access_reconfirm(
        AccessLevel.PUBLIC,
        agent3,
        lookup,
    )

    assert ok is False
    assert violations == ["aud05_restricted_doc"]


# ==========================================================================
# AUD-06
# ==========================================================================

def test_AUD06_internal_session_is_blocked_from_restricted_document(
    make_chunk,
    make_citation,
    make_agent3_output,
):
    """
    AUD-06: Attempts to expose a restricted document to an internal
    session. Internal authorization must not be sufficient for restricted
    information.
    """

    chunk = make_chunk(
        doc_id="aud06_restricted_doc",
        chunk_id="aud06_chunk",
        doc_access_level=AccessLevel.RESTRICTED,
    )

    citation = make_citation(
        doc_id="aud06_restricted_doc",
        chunk_id="aud06_chunk",
    )

    agent3 = make_agent3_output(
        citations=[citation],
        chunks_used=["aud06_chunk"],
    )

    lookup = {
        "aud06_chunk": chunk,
    }

    ok, violations = check_access_reconfirm(
        AccessLevel.INTERNAL,
        agent3,
        lookup,
    )

    assert ok is False
    assert violations == ["aud06_restricted_doc"]


# ==========================================================================
# AUD-07
# ==========================================================================

def test_AUD07_missing_or_forged_citation_fails_closed(
    happy_path,
):
    """
    AUD-07: Simulates a forged or stale citation whose chunk ID cannot
    be resolved. Agent 4 must fail closed rather than allowing access.
    """

    empty_lookup = {}

    ok, violations = check_access_reconfirm(
        AccessLevel.RESTRICTED,
        happy_path["agent3"],
        empty_lookup,
    )

    assert ok is False
    assert violations == [
        happy_path["citation"].doc_id
    ]


# ==========================================================================
# AUD-08
# ==========================================================================

def test_AUD08_agent3_citation_not_returned_by_agent2_fails_factual_check(
    make_citation,
    make_agent3_output,
):
    """
    AUD-08: Simulates Agent 3 citing a chunk that Agent 2 never returned.
    This prevents a generated answer from bypassing the retrieval layer.
    """

    citation = make_citation(
        doc_id="aud08_phantom_doc",
        chunk_id="aud08_phantom_chunk",
    )

    agent3 = make_agent3_output(
        citations=[citation],
        chunks_used=["aud08_phantom_chunk"],
    )

    lookup = {}

    verdict, confidence = check_factual_support(
        agent3,
        lookup,
    )

    assert verdict == FactualSupportCheck.FAIL
    assert confidence == 0.0


# ==========================================================================
# AUD-09
# ==========================================================================

def test_AUD09_insufficient_evidence_is_not_accepted(
    make_agent3_output,
    make_citation,
):
    """
    AUD-09: Confirms that an answer without sufficient grounding,
    citations and used chunks is classified as insufficient evidence.
    """

    citation = make_citation()

    agent3 = make_agent3_output(
        grounded=False,
        citations=[citation],
        chunks_used=["aud09_chunk"],
    )

    result = check_evidence_sufficiency(agent3)

    assert result == EvidenceSufficiency.INSUFFICIENT


# ==========================================================================
# AUD-10
# ==========================================================================

def test_AUD10_low_factual_confidence_is_not_treated_as_verified():
    """
    AUD-10: Confirms that the offline factual-support fallback produces
    only 0.5 confidence when source text exists. This is below the
    Agent 4 approval threshold of 0.6 and therefore cannot by itself
    establish a confident factual verification.
    """

    verdict, confidence = llm_factual_support_check(
        "The minimum balance is LKR 1,000.",
        ["The minimum balance is LKR 1,000."],
    )

    assert verdict == "pass"
    assert confidence == 0.5
    assert confidence < 0.6


# ==========================================================================
# AUD-11
# ==========================================================================

def test_AUD11_conversation_content_is_isolated_between_sessions(
    monkeypatch,
):
    """
    AUD-11: Runs two unrelated conversations through Agent 4 and verifies
    that content from one session does not appear in the other session's
    final answer or citations.
    """

    import agent4_verification.verifier as verifier

    monkeypatch.setattr(
        verifier,
        "llm_factual_support_check",
        lambda answer, chunks: ("pass", 0.95),
    )

    session_a = _unique_session_id()
    session_b = _unique_session_id()

    agent1_a, agent2_a, agent3_a = _build_pipeline_stage(
        session_a,
        "savings account minimum balance",
        "The minimum balance for a savings account is LKR 1,000.",
    )

    agent1_b, agent2_b, agent3_b = _build_pipeline_stage(
        session_b,
        "fraud reporting procedure",
        "Report suspected fraud immediately through the approved hotline.",
    )

    result_a = run_agent4(
        agent1_a,
        agent2_a,
        agent3_a,
    )

    result_b = run_agent4(
        agent1_b,
        agent2_b,
        agent3_b,
    )

    assert result_a.session_id == session_a
    assert result_b.session_id == session_b

    assert "1,000" in result_a.final_answer
    assert "fraud" not in (
        result_a.final_answer or ""
    ).lower()

    assert "fraud" in (
        result_b.final_answer or ""
    ).lower()

    assert "1,000" not in (
        result_b.final_answer or ""
    )

    citations_a = {
        citation.doc_id
        for citation in result_a.final_citations
    }

    citations_b = {
        citation.doc_id
        for citation in result_b.final_citations
    }

    assert citations_a.isdisjoint(citations_b)


# ==========================================================================
# AUD-12
# ==========================================================================

def test_AUD12_audit_log_records_are_isolated_by_session(
    track_log_ids,
):
    """
    AUD-12: Creates audit records for two different sessions and verifies
    that read_records_for_session() returns only records belonging to the
    requested session.
    """

    session_a = _unique_session_id()
    session_b = _unique_session_id()

    agent1_a, agent2_a, agent3_a = _build_pipeline_stage(
        session_a,
        "savings account minimum balance",
        "The minimum balance is LKR 1,000.",
    )

    agent1_b, agent2_b, agent3_b = _build_pipeline_stage(
        session_b,
        "fraud reporting procedure",
        "Report suspected fraud immediately.",
    )

    result_a = run_agent4(
        agent1_a,
        agent2_a,
        agent3_a,
    )

    result_b = run_agent4(
        agent1_b,
        agent2_b,
        agent3_b,
    )

    records = []

    records.append(log_classification(agent1_a))
    records.append(log_retrieval(agent2_a))
    records.append(log_generation(agent3_a))
    records.append(log_verification(result_a))

    records.append(log_classification(agent1_b))
    records.append(log_retrieval(agent2_b))
    records.append(log_generation(agent3_b))
    records.append(log_verification(result_b))

    track_log_ids.extend(
        [record.log_id for record in records]
    )

    records_a = read_records_for_session(session_a)
    records_b = read_records_for_session(session_b)

    assert len(records_a) == 4
    assert len(records_b) == 4

    assert all(
        record.session_id == session_a
        for record in records_a
    )

    assert all(
        record.session_id == session_b
        for record in records_b
    )

    text_a = " ".join(
        str(record.payload_snapshot)
        for record in records_a
    )

    text_b = " ".join(
        str(record.payload_snapshot)
        for record in records_b
    )

    assert "fraud" not in text_a.lower()
    assert "1,000" in text_a

    assert "fraud" in text_b.lower()


# ==========================================================================
# AUD-13
# ==========================================================================

def test_AUD13_pii_like_query_is_stored_unredacted_in_audit_log(
    track_log_ids,
):
    """
    AUD-13 [PRIVACY FINDING]: Checks whether an account-number-shaped
    value entered by a user is stored verbatim in the audit log.

    The test intentionally uses fake data.

    A PASS means the test successfully confirmed the current behavior:
    the value is stored without redaction.

    Therefore this case is a security/privacy finding, not evidence
    that the privacy control is secure.
    """

    session_id = _unique_session_id()

    fake_account_number = "8801234567"

    query_with_pii = (
        f"What is the status of account {fake_account_number}?"
    )

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

    stored_records = read_records_for_session(
        session_id
    )

    assert len(stored_records) == 1

    stored_text = str(
        stored_records[0].payload_snapshot
    )

    # Current behavior:
    # the account-number-shaped value remains unredacted.
    assert fake_account_number in stored_text


# ==========================================================================
# AUD-14
# ==========================================================================

def test_AUD14_conflicting_document_versions_are_detected(
    make_chunk,
    make_citation,
    make_agent3_output,
):
    """
    AUD-14: Simulates an answer that cites two versions of the same
    policy document. Agent 4 must detect the version conflict.
    """

    chunk_v1 = make_chunk(
        doc_id="aud14_doc_v1",
        chunk_id="aud14_chunk_v1",
        doc_title="Minimum Balance Policy",
        doc_version="v1",
        effective_date="2024-01-01",
    )

    chunk_v2 = make_chunk(
        doc_id="aud14_doc_v2",
        chunk_id="aud14_chunk_v2",
        doc_title="Minimum Balance Policy",
        doc_version="v2",
        effective_date="2025-01-01",
    )

    citation_v1 = make_citation(
        doc_id="aud14_doc_v1",
        doc_title="Minimum Balance Policy",
        chunk_id="aud14_chunk_v1",
    )

    citation_v2 = make_citation(
        doc_id="aud14_doc_v2",
        doc_title="Minimum Balance Policy",
        chunk_id="aud14_chunk_v2",
    )

    agent3 = make_agent3_output(
        citations=[
            citation_v1,
            citation_v2,
        ],
        chunks_used=[
            "aud14_chunk_v1",
            "aud14_chunk_v2",
        ],
    )

    lookup = {
        "aud14_chunk_v1": chunk_v1,
        "aud14_chunk_v2": chunk_v2,
    }

    detected, details = check_version_conflict(
        agent3,
        lookup,
    )

    assert detected is True
    assert details is not None

    assert "Minimum Balance Policy" in details
    assert "v1" in details
    assert "v2" in details


# ==========================================================================
# AUD-15
# ==========================================================================

def test_AUD15_malformed_nonexistent_chunk_fails_closed(
    make_citation,
    make_agent3_output,
):
    """
    AUD-15: Provides a malformed/non-existent chunk reference and verifies
    that Agent 4 fails closed instead of silently accepting the citation.
    """

    citation = make_citation(
        doc_id="aud15_fake_doc",
        chunk_id="THIS_CHUNK_DOES_NOT_EXIST",
    )

    agent3 = make_agent3_output(
        grounded=True,
        citations=[citation],
        chunks_used=[
            "THIS_CHUNK_DOES_NOT_EXIST"
        ],
    )

    lookup = {}

    access_ok, violations = check_access_reconfirm(
        AccessLevel.PUBLIC,
        agent3,
        lookup,
    )

    assert access_ok is False
    assert violations == [
        "aud15_fake_doc"
    ]

    factual_verdict, factual_confidence = (
        check_factual_support(
            agent3,
            lookup,
        )
    )

    assert factual_verdict == FactualSupportCheck.FAIL
    assert factual_confidence == 0.0

