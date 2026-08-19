"""
agent4_verification/tests/test_verifier.py

Unit tests for Agent 4. These run WITHOUT calling Gemini — the LLM call is
monkeypatched so tests are fast, free, and deterministic. This is what you
run constantly while developing, and what your teammates/examiner can run
without needing your API key.

Run with:
    pytest agent4_verification/tests/ -v

For a live test that actually calls Gemini, see test_live_gemini_smoke
at the bottom (skipped automatically if GEMINI_API_KEY isn't set).
"""

import pytest

from agent4_verification.verifier import (
    Agent2Output,
    Agent3Output,
    Agent4Input,
    Citation,
    RetrievedChunk,
    run_agent4,
)
import agent4_verification.verifier as verifier_module


# --------------------------------------------------------------------------
# Fixture: force the LLM factual-support check to a known value, so these
# tests aren't dependent on network access or Gemini's actual judgment.
# --------------------------------------------------------------------------

@pytest.fixture
def stub_llm_pass(monkeypatch):
    """Pretend the LLM always says the answer is well-supported."""
    monkeypatch.setattr(
        verifier_module, "llm_factual_support_check",
        lambda answer_text, chunk_texts: ("pass", 0.95),
    )


@pytest.fixture
def stub_llm_fail(monkeypatch):
    """Pretend the LLM always says the answer is NOT supported."""
    monkeypatch.setattr(
        verifier_module, "llm_factual_support_check",
        lambda answer_text, chunk_texts: ("fail", 0.1),
    )


@pytest.fixture
def stub_llm_low_confidence(monkeypatch):
    """Pretend the LLM passes it, but with confidence below the threshold."""
    monkeypatch.setattr(
        verifier_module, "llm_factual_support_check",
        lambda answer_text, chunk_texts: ("pass", 0.4),  # < CONFIDENCE_THRESHOLD (0.6)
    )


# --------------------------------------------------------------------------
# Scenario builders
# --------------------------------------------------------------------------

def make_clean_payload():
    a2 = Agent2Output(
        session_id="s1",
        access_level="public",
        results=[
            RetrievedChunk(
                doc_id="doc_001", doc_title="Savings Account Guide",
                chunk_id="c1", chunk_text="Minimum balance is LKR 1,000.",
                similarity_score=0.9, doc_access_level="public",
                doc_version="v1", effective_date="2024-06-01",
                source_section="Section 2.1",
            )
        ],
        retrieval_confidence="high",
    )
    a3 = Agent3Output(
        session_id="s1",
        answer_text="Minimum balance is LKR 1,000.",
        grounded=True,
        citations=[Citation(doc_id="doc_001", doc_title="Savings Account Guide",
                              section="Section 2.1", chunk_id="c1")],
        chunks_used=["c1"],
    )
    return Agent4Input(session_id="s1", user_role="customer",
                         access_level="public", agent2_output=a2, agent3_output=a3)


def make_access_violation_payload():
    a2 = Agent2Output(
        session_id="s2",
        access_level="public",
        results=[
            RetrievedChunk(
                doc_id="doc_014", doc_title="Fraud Investigation Procedure",
                chunk_id="c2", chunk_text="Escalate confirmed fraud within 24h.",
                similarity_score=0.8, doc_access_level="restricted",  # leak
                doc_version="v1", effective_date="2025-02-01",
                source_section="Section 1.3",
            )
        ],
        retrieval_confidence="medium",
    )
    a3 = Agent3Output(
        session_id="s2",
        answer_text="Escalate confirmed fraud within 24h.",
        grounded=True,
        citations=[Citation(doc_id="doc_014", doc_title="Fraud Investigation Procedure",
                              section="Section 1.3", chunk_id="c2")],
        chunks_used=["c2"],
    )
    return Agent4Input(session_id="s2", user_role="customer",
                         access_level="public", agent2_output=a2, agent3_output=a3)


def make_no_evidence_payload():
    a2 = Agent2Output(session_id="s3", access_level="public", results=[],
                        retrieval_confidence="low")
    a3 = Agent3Output(session_id="s3",
                        answer_text="I don't have information on this.",
                        grounded=False, citations=[], chunks_used=[])
    return Agent4Input(session_id="s3", user_role="customer",
                         access_level="public", agent2_output=a2, agent3_output=a3)


def make_uncited_chunk_payload():
    a2 = Agent2Output(
        session_id="s4", access_level="internal",
        results=[
            RetrievedChunk(
                doc_id="doc_005", doc_title="Account Opening Procedure",
                chunk_id="c5", chunk_text="Provide NIC and proof of address.",
                similarity_score=0.85, doc_access_level="internal",
                doc_version="v1", effective_date="2024-01-01",
                source_section="Section 1",
            )
        ],
        retrieval_confidence="high",
    )
    a3 = Agent3Output(
        session_id="s4", answer_text="Provide NIC and proof of address.",
        grounded=True, citations=[], chunks_used=["c5"],  # used but not cited
    )
    return Agent4Input(session_id="s4", user_role="employee",
                         access_level="internal", agent2_output=a2, agent3_output=a3)


def make_version_conflict_payload():
    a2 = Agent2Output(
        session_id="s5", access_level="internal",
        results=[
            RetrievedChunk(doc_id="doc_020", doc_title="Minimum Balance Policy",
                             chunk_id="c6", chunk_text="LKR 1,000 (2023).",
                             similarity_score=0.8, doc_access_level="internal",
                             doc_version="v1", effective_date="2023-01-01",
                             source_section="Section 1"),
            RetrievedChunk(doc_id="doc_021", doc_title="Minimum Balance Policy",
                             chunk_id="c7", chunk_text="LKR 2,500 (2025).",
                             similarity_score=0.85, doc_access_level="internal",
                             doc_version="v2", effective_date="2025-01-01",
                             source_section="Section 1"),
        ],
        retrieval_confidence="high",
    )
    a3 = Agent3Output(
        session_id="s5", answer_text="Minimum balance has changed over time.",
        grounded=True,
        citations=[
            Citation(doc_id="doc_020", doc_title="Minimum Balance Policy",
                      section="Section 1", chunk_id="c6"),
            Citation(doc_id="doc_021", doc_title="Minimum Balance Policy",
                      section="Section 1", chunk_id="c7"),
        ],
        chunks_used=["c6", "c7"],
    )
    return Agent4Input(session_id="s5", user_role="employee",
                         access_level="internal", agent2_output=a2, agent3_output=a3)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_clean_case_is_approved(stub_llm_pass):
    result = run_agent4(make_clean_payload())
    assert result.decision == "approved"
    assert result.final_answer is not None
    assert result.access_reconfirmed is True


def test_access_violation_is_denied_and_leaks_nothing(stub_llm_pass):
    """Core privacy test — must never approve a citation to a doc above
    the session's access level, even if the LLM would've said it's fine."""
    result = run_agent4(make_access_violation_payload())
    assert result.decision == "denied"
    assert result.access_reconfirmed is False
    assert result.final_answer is None
    assert result.final_citations == []
    assert "doc_014" in result.denial_reason


def test_no_evidence_denies_not_escalates(stub_llm_pass):
    result = run_agent4(make_no_evidence_payload())
    assert result.decision == "denied"
    assert result.evidence_sufficiency == "insufficient"
    assert result.final_answer is None


def test_uncited_used_chunk_never_approved():
    """No stub needed — factual check fails before the LLM is even called
    (used-but-uncited is caught by the cheap heuristic check first)."""
    result = run_agent4(make_uncited_chunk_payload())
    assert result.decision != "approved"
    assert result.factual_support_check == "fail"
    assert result.final_answer is None


def test_version_conflict_escalates_not_approves(stub_llm_pass):
    result = run_agent4(make_version_conflict_payload())
    assert result.decision == "escalated"
    assert result.version_conflict_detected is True
    assert "Minimum Balance Policy" in result.conflict_details
    assert result.final_answer is None


def test_llm_fail_escalates(stub_llm_fail):
    result = run_agent4(make_clean_payload())
    assert result.decision == "escalated"
    assert result.factual_support_check == "fail"
    assert result.final_answer is None


def test_low_confidence_below_threshold_escalates(stub_llm_low_confidence):
    """Even a 'pass' verdict should escalate if confidence < CONFIDENCE_THRESHOLD."""
    result = run_agent4(make_clean_payload())
    assert result.decision == "escalated"
    assert result.confidence < verifier_module.CONFIDENCE_THRESHOLD


def test_approved_always_has_final_answer(stub_llm_pass):
    result = run_agent4(make_clean_payload())
    if result.decision == "approved":
        assert result.final_answer and result.final_answer.strip()
        assert result.final_citations


def test_denied_always_has_a_reason(stub_llm_pass):
    for payload in (make_access_violation_payload(), make_no_evidence_payload()):
        result = run_agent4(payload)
        if result.decision == "denied":
            assert result.denial_reason


# --------------------------------------------------------------------------
# Live smoke test — actually calls Gemini. Skipped unless GEMINI_API_KEY
# is set in your .env. Run explicitly with:
#   pytest agent4_verification/tests/test_verifier.py -v -k live_gemini
# --------------------------------------------------------------------------

@pytest.mark.skipif(
    not verifier_module.GEMINI_API_KEY,
    reason="GEMINI_API_KEY not set — skipping live Gemini call",
)
def test_live_gemini_smoke():
    result = run_agent4(make_clean_payload())
    # Don't assert a specific decision here (depends on live model output) —
    # just prove the round trip to Gemini and back didn't error, and that
    # we got a real confidence score back, not the no-key fallback value.
    assert result.factual_support_check in ("pass", "fail")
    assert 0.0 <= result.confidence <= 1.0