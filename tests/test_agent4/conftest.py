"""
tests/test_agent4/conftest.py

Shared fixtures for Agent 4 (Verification & Governance) tests.

Builds real shared.schemas / shared.enums objects (the same contracts
Agents 1-3 actually produce), not local stand-ins -- so these tests catch
real integration breakage, not just Agent 4's internal logic in isolation.

Key thing these fixtures solve: `llm_factual_support_check` calls out to
Gemini. We never want real tests hitting a real API, so every test gets
`no_gemini` (client forced to None -> fallback heuristic) unless it
explicitly asks for `fake_gemini` to control the verdict/confidence
returned.
"""

from __future__ import annotations

import pytest

import agent4_verification.verifier as verifier
from shared.enums import AccessLevel, Intent, RetrievalConfidence, UserRole
from shared.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Citation,
    RetrievedChunk,
)


# --------------------------------------------------------------------------
# Gemini client control
# --------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeModels:
    def __init__(self, text: str):
        self._text = text

    def generate_content(self, model, contents):
        return _FakeResponse(self._text)


class _FakeGeminiClient:
    """Stands in for genai.Client(...). `.models.generate_content(...)`
    always returns the JSON string it was built with."""

    def __init__(self, response_text: str):
        self.models = _FakeModels(response_text)


class _RaisingClient:
    """Simulates a Gemini call that raises (network error, bad response,
    etc.) so we can assert Agent 4 fails closed."""

    class _Models:
        def generate_content(self, model, contents):
            raise RuntimeError("simulated Gemini failure")

    def __init__(self):
        self.models = self._Models()


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    """By default, every test runs with no Gemini client configured, so
    llm_factual_support_check falls back to the offline heuristic. This
    keeps the suite fast, deterministic, and network-free."""
    monkeypatch.setattr(verifier, "_gemini_client", None)
    monkeypatch.setattr(verifier, "GEMINI_API_KEY", None)
    yield


@pytest.fixture
def fake_gemini(monkeypatch):
    """Use in a test to control exactly what Gemini 'returns'.

    Usage:
        fake_gemini('{"verdict": "pass", "confidence": 0.9, "reason": "ok"}')
    """

    def _install(response_text: str):
        monkeypatch.setattr(
            verifier, "_gemini_client", _FakeGeminiClient(response_text)
        )
        return response_text

    return _install


@pytest.fixture
def failing_gemini(monkeypatch):
    """Install a Gemini client whose call raises, to test the
    fail-closed exception path."""
    monkeypatch.setattr(verifier, "_gemini_client", _RaisingClient())


# --------------------------------------------------------------------------
# Domain object factories (real shared.schemas / shared.enums types)
# --------------------------------------------------------------------------

@pytest.fixture
def make_chunk():
    def _make(
        doc_id="doc_001",
        doc_title="Savings Account Guide",
        chunk_id="doc_001_c03",
        chunk_text="The minimum balance for a standard savings account is LKR 1,000.",
        similarity_score=0.91,
        doc_access_level=AccessLevel.PUBLIC,
        doc_version="v1",
        effective_date="2024-06-01",
        source_section="Section 2.1",
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
        section="Section 2.1",
        chunk_id="doc_001_c03",
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
        intent=Intent.ACCOUNT_INFO,
        topic="savings_account",
        normalized_query="What is the minimum balance for a savings account?",
        confidence=0.9,
    ) -> Agent1Output:
        return Agent1Output(
            session_id=session_id,
            user_role=user_role,
            access_level=access_level,
            intent=intent,
            topic=topic,
            normalized_query=normalized_query,
            confidence=confidence,
        )

    return _make


@pytest.fixture
def make_agent2_output():
    def _make(
        session_id="sess_test",
        query_used="minimum balance savings account",
        access_level=AccessLevel.PUBLIC,
        results=None,
        retrieval_confidence=RetrievalConfidence.HIGH,
    ) -> Agent2Output:
        return Agent2Output(
            session_id=session_id,
            query_used=query_used,
            access_level=access_level,
            results=results or [],
            retrieval_confidence=retrieval_confidence,
        )

    return _make


@pytest.fixture
def make_agent3_output():
    def _make(
        session_id="sess_test",
        answer_text="The minimum balance for a standard savings account is LKR 1,000.",
        grounded=True,
        citations=None,
        chunks_used=None,
    ) -> Agent3Output:
        return Agent3Output(
            session_id=session_id,
            answer_text=answer_text,
            grounded=grounded,
            citations=citations or [],
            chunks_used=chunks_used or [],
        )

    return _make


@pytest.fixture
def happy_path(
    make_chunk, make_citation, make_agent1_output, make_agent2_output, make_agent3_output
):
    """A minimal, fully-consistent public-tier scenario: one chunk, one
    citation, chunk used, no conflicts. Individual tests mutate copies of
    this rather than rebuilding it from scratch."""
    chunk = make_chunk()
    citation = make_citation()
    agent1 = make_agent1_output()
    agent2 = make_agent2_output(results=[chunk])
    agent3 = make_agent3_output(citations=[citation], chunks_used=[chunk.chunk_id])
    return {
        "chunk": chunk,
        "citation": citation,
        "agent1": agent1,
        "agent2": agent2,
        "agent3": agent3,
    }