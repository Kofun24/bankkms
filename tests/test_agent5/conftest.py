"""
tests/test_agent5/conftest.py

Shared fixtures for Agent 5 (Audit & Compliance Logging) tests.

Every test gets an isolated log file via `log_path` (a fresh path under
pytest's tmp_path), so tests never touch the real AUDIT_LOG_PATH from
config.py and never interfere with each other's chains.
"""

from __future__ import annotations

import pytest

from shared.enums import (
    AccessLevel,
    EvidenceSufficiency,
    FactualSupportCheck,
    Intent,
    RetrievalConfidence,
    UserRole,
    VerificationDecision,
)
from shared.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Agent4Output,
    Citation,
    RetrievedChunk,
)


@pytest.fixture
def log_path(tmp_path):
    """A fresh, isolated audit log path for a single test. The file does
    not exist yet -- the first append starts a new chain."""
    return str(tmp_path / "audit_log.jsonl")


@pytest.fixture
def make_chunk():
    def _make(
        doc_id="doc_001",
        doc_title="Savings Account Guide",
        chunk_id="doc_001_c04",
        chunk_text="A National Identity Card and proof of address are required.",
        similarity_score=0.69,
        doc_access_level=AccessLevel.PUBLIC,
        doc_version="v1",
        effective_date="2024-01-01",
        source_section="How to Open an Account",
    ) -> RetrievedChunk:
        return RetrievedChunk(
            doc_id=doc_id,
            doc_title=doc_title,
            chunk_id=chunk_id,
            chunk_text=chunk_text,
            similarity_score=similarity_score,
            doc_access_level=doc_access_level,
            doc_version=doc_version,
            effective_date=effective_date,
            source_section=source_section,
        )

    return _make


@pytest.fixture
def make_citation():
    def _make(
        doc_id="doc_001",
        doc_title="Savings Account Guide",
        section="How to Open an Account",
        chunk_id="doc_001_c04",
    ) -> Citation:
        return Citation(
            doc_id=doc_id, doc_title=doc_title, section=section, chunk_id=chunk_id
        )

    return _make


@pytest.fixture
def make_agent1_output():
    def _make(
        session_id="sess_test",
        user_role=UserRole.CUSTOMER,
        access_level=AccessLevel.PUBLIC,
        intent=Intent.PROCEDURE_LOOKUP,
        topic="documents needed for savings account",
        normalized_query="What documents do I need to open a savings account?",
        confidence=0.95,
        needs_clarification=False,
    ) -> Agent1Output:
        return Agent1Output(
            session_id=session_id,
            user_role=user_role,
            access_level=access_level,
            intent=intent,
            topic=topic,
            normalized_query=normalized_query,
            confidence=confidence,
            needs_clarification=needs_clarification,
        )

    return _make


@pytest.fixture
def make_agent2_output(make_chunk):
    def _make(
        session_id="sess_test",
        query_used="What documents do I need to open a savings account?",
        access_level=AccessLevel.PUBLIC,
        results=None,
        retrieval_confidence=RetrievalConfidence.MEDIUM,
        reformulated=False,
        retrieval_attempts=1,
    ) -> Agent2Output:
        return Agent2Output(
            session_id=session_id,
            query_used=query_used,
            access_level=access_level,
            results=results if results is not None else [make_chunk()],
            retrieval_confidence=retrieval_confidence,
            reformulated=reformulated,
            retrieval_attempts=retrieval_attempts,
        )

    return _make


@pytest.fixture
def make_agent3_output(make_citation):
    def _make(
        session_id="sess_test",
        answer_text="You need a National Identity Card and proof of address.",
        grounded=True,
        citations=None,
        chunks_used=None,
    ) -> Agent3Output:
        return Agent3Output(
            session_id=session_id,
            answer_text=answer_text,
            grounded=grounded,
            citations=citations if citations is not None else [make_citation()],
            chunks_used=chunks_used if chunks_used is not None else ["doc_001_c04"],
        )

    return _make


@pytest.fixture
def make_agent4_output():
    def _make(
        session_id="sess_test",
        decision=VerificationDecision.APPROVED,
        denial_reason=None,
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
        factual_support_check=FactualSupportCheck.PASS,
        version_conflict_detected=False,
        access_reconfirmed=True,
        confidence=0.95,
    ) -> Agent4Output:
        return Agent4Output(
            session_id=session_id,
            decision=decision,
            denial_reason=denial_reason,
            evidence_sufficiency=evidence_sufficiency,
            factual_support_check=factual_support_check,
            version_conflict_detected=version_conflict_detected,
            access_reconfirmed=access_reconfirmed,
            confidence=confidence,
        )

    return _make