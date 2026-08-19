"""
agent4_verification/tests/test_audit.py

Individual assignment — Member 4: Privacy & Data Leakage Assessment
15 test cases probing Agent 4 as the final access-control gate.

Run with:
    python -m pytest agent4_verification/tests/test_audit.py -v

All tests here mock the Gemini call (deterministic, offline, free) so the
suite is fast and repeatable for the report/viva. Where a case exposes a
real gap in current behavior rather than confirming correct behavior, it's
marked FINDING in the docstring — these are legitimate audit findings, not
bugs in the test.

Categories:
    A. Access-Control Bypass         (AUD-01 .. AUD-04)
    B. Factual / Hallucination Leak  (AUD-05 .. AUD-07)
    C. Version Conflict Handling     (AUD-08 .. AUD-09)
    D. Confidence Threshold Boundary (AUD-10 .. AUD-12)
    E. Structural / Malformed Input  (AUD-13 .. AUD-15)
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
import agent4_verification.verifier as v


# --------------------------------------------------------------------------
# Shared stubs
# --------------------------------------------------------------------------

@pytest.fixture
def llm_pass(monkeypatch):
    monkeypatch.setattr(v, "llm_factual_support_check",
                          lambda a, c: ("pass", 0.95))

@pytest.fixture
def llm_fail(monkeypatch):
    monkeypatch.setattr(v, "llm_factual_support_check",
                          lambda a, c: ("fail", 0.1))


def chunk(**kw):
    defaults = dict(similarity_score=0.85, doc_version="v1",
                      effective_date="2024-01-01", source_section="Section 1")
    defaults.update(kw)
    return RetrievedChunk(**defaults)


# ==========================================================================
# A. ACCESS-CONTROL BYPASS
# ==========================================================================

def test_AUD01_single_restricted_citation_in_public_session(llm_pass):
    """AUD-01: A public session ends up with one citation to a restricted
    doc (Agent 2 filter theoretically failed upstream). Agent 4's
    reconfirmation must catch it independently and deny."""
    a2 = Agent2Output(session_id="a1", access_level="public", results=[
        chunk(doc_id="doc_014", doc_title="Fraud Investigation Procedure",
               chunk_id="c1", chunk_text="Escalate within 24h.",
               doc_access_level="restricted"),
    ], retrieval_confidence="medium")
    a3 = Agent3Output(session_id="a1", answer_text="Escalate within 24h.",
                        grounded=True,
                        citations=[Citation(doc_id="doc_014", doc_title="Fraud Investigation Procedure",
                                              section="Section 1", chunk_id="c1")],
                        chunks_used=["c1"])
    payload = Agent4Input(session_id="a1", user_role="customer",
                            access_level="public", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "denied"
    assert result.access_reconfirmed is False
    assert result.final_answer is None


def test_AUD02_mixed_access_citations_deny_entirely(llm_pass):
    """AUD-02: One valid public citation + one restricted citation in the
    same answer. The whole answer must be denied, not partially released —
    partial approval would still leak the restricted content."""
    a2 = Agent2Output(session_id="a2", access_level="public", results=[
        chunk(doc_id="doc_001", doc_title="Savings Account Guide", chunk_id="c1",
               chunk_text="Minimum balance is LKR 1,000.", doc_access_level="public"),
        chunk(doc_id="doc_014", doc_title="Fraud Investigation Procedure", chunk_id="c2",
               chunk_text="Escalate within 24h.", doc_access_level="restricted"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="a2",
                        answer_text="Minimum balance is LKR 1,000. Also, escalate fraud within 24h.",
                        grounded=True,
                        citations=[
                            Citation(doc_id="doc_001", doc_title="Savings Account Guide",
                                      section="Section 1", chunk_id="c1"),
                            Citation(doc_id="doc_014", doc_title="Fraud Investigation Procedure",
                                      section="Section 1", chunk_id="c2"),
                        ],
                        chunks_used=["c1", "c2"])
    payload = Agent4Input(session_id="a2", user_role="customer",
                            access_level="public", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "denied"
    assert result.final_answer is None
    assert result.final_citations == []


def test_AUD03_employee_cannot_access_compliance_only_doc(llm_pass):
    """AUD-03: Employee (internal) session citing a compliance-only
    (restricted) doc must be denied — internal != restricted."""
    a2 = Agent2Output(session_id="a3", access_level="internal", results=[
        chunk(doc_id="doc_014", doc_title="AML Procedure v2", chunk_id="c1",
               chunk_text="File a SAR within 5 business days.",
               doc_access_level="restricted"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="a3", answer_text="File a SAR within 5 business days.",
                        grounded=True,
                        citations=[Citation(doc_id="doc_014", doc_title="AML Procedure v2",
                                              section="Section 1", chunk_id="c1")],
                        chunks_used=["c1"])
    payload = Agent4Input(session_id="a3", user_role="employee",
                            access_level="internal", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "denied"
    assert result.access_reconfirmed is False


def test_AUD04_citation_to_chunk_not_in_retrieval_results(llm_pass):
    """AUD-04: Agent 3 cites a chunk_id that never appeared in Agent 2's
    results at all (spoofed/tampered/hallucinated chunk reference). Agent 4
    must treat unverifiable citations as a violation, not wave them through."""
    a2 = Agent2Output(session_id="a4", access_level="public", results=[
        chunk(doc_id="doc_001", doc_title="Savings Account Guide", chunk_id="c1",
               chunk_text="Minimum balance is LKR 1,000.", doc_access_level="public"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="a4", answer_text="Some claim.",
                        grounded=True,
                        citations=[Citation(doc_id="doc_999", doc_title="Nonexistent Doc",
                                              section="Section 1", chunk_id="c_phantom")],
                        chunks_used=["c_phantom"])
    payload = Agent4Input(session_id="a4", user_role="customer",
                            access_level="public", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "denied"
    assert result.access_reconfirmed is False
    assert "doc_999" in result.denial_reason


# ==========================================================================
# B. FACTUAL / HALLUCINATION LEAKAGE
# ==========================================================================

def test_AUD05_fully_fabricated_claim_not_approved(llm_fail):
    """AUD-05: Answer contains a numeric claim nowhere in the cited chunk.
    LLM factual check should fail -> must not reach 'approved'."""
    a2 = Agent2Output(session_id="b1", access_level="public", results=[
        chunk(doc_id="doc_001", doc_title="Savings Account Guide", chunk_id="c1",
               chunk_text="Minimum balance is LKR 1,000.", doc_access_level="public"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="b1",
                        answer_text="Minimum balance is LKR 2,000 with a signup bonus.",
                        grounded=True,
                        citations=[Citation(doc_id="doc_001", doc_title="Savings Account Guide",
                                              section="Section 1", chunk_id="c1")],
                        chunks_used=["c1"])
    payload = Agent4Input(session_id="b1", user_role="customer",
                            access_level="public", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision != "approved"
    assert result.factual_support_check == "fail"


def test_AUD06_partial_hallucination_one_true_one_false(llm_fail):
    """AUD-06: Answer mixes one correct, supported claim with one
    fabricated claim. A naive check might approve because *some* content
    is grounded — must still fail/escalate on the whole answer."""
    a2 = Agent2Output(session_id="b2", access_level="internal", results=[
        chunk(doc_id="doc_005", doc_title="Account Opening Procedure", chunk_id="c1",
               chunk_text="Customers must provide NIC and proof of address.",
               doc_access_level="internal"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(
        session_id="b2",
        answer_text="Customers must provide NIC and proof of address, "
                     "and accounts are opened instantly with no verification.",
        grounded=True,
        citations=[Citation(doc_id="doc_005", doc_title="Account Opening Procedure",
                              section="Section 1", chunk_id="c1")],
        chunks_used=["c1"],
    )
    payload = Agent4Input(session_id="b2", user_role="employee",
                            access_level="internal", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision != "approved"
    assert result.factual_support_check == "fail"


def test_AUD07_citation_doc_id_mismatch_with_actual_chunk(llm_pass):
    """AUD-07 [FINDING]: Citation claims doc_id='doc_001' but chunk_id 'c1'
    actually belongs to a different doc in Agent 2's results. Current
    implementation resolves access purely via chunk_id, so it does NOT
    detect this label mismatch — content-level access is still correctly
    enforced (the real chunk's access level is checked), but the reported
    final_citations doc_id could be wrong/misleading.

    This test documents current behavior as a known limitation, not a
    leakage bug: no restricted content is exposed, but citation integrity
    is not verified. Recommend Agent 4 additionally assert
    citation.doc_id == chunk_lookup[citation.chunk_id].doc_id and treat
    a mismatch as a violation.
    """
    a2 = Agent2Output(session_id="b3", access_level="public", results=[
        chunk(doc_id="doc_REAL", doc_title="Real Doc", chunk_id="c1",
               chunk_text="Minimum balance is LKR 1,000.", doc_access_level="public"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(
        session_id="b3", answer_text="Minimum balance is LKR 1,000.",
        grounded=True,
        # doc_id here ("doc_SPOOFED") does not match the chunk's real doc_id ("doc_REAL")
        citations=[Citation(doc_id="doc_SPOOFED", doc_title="Spoofed Title",
                              section="Section 1", chunk_id="c1")],
        chunks_used=["c1"],
    )
    payload = Agent4Input(session_id="b3", user_role="customer",
                            access_level="public", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    # Current behavior: still approves, because access is resolved via
    # chunk_id and the real chunk is public. Documented as a finding above.
    assert result.decision == "approved"
    assert result.final_citations[0]["doc_id"] == "doc_SPOOFED"  # mismatch passes through uncaught


# ==========================================================================
# C. VERSION CONFLICT HANDLING
# ==========================================================================

def test_AUD08_version_conflict_both_within_access_escalates(llm_pass):
    """AUD-08: Two versions of the same doc, both within the session's
    allowed access level. Should escalate for human review, not silently
    pick one version and approve."""
    a2 = Agent2Output(session_id="c1", access_level="internal", results=[
        chunk(doc_id="doc_020", doc_title="Minimum Balance Policy", chunk_id="c1",
               chunk_text="LKR 1,000 (2023).", doc_access_level="internal",
               doc_version="v1", effective_date="2023-01-01"),
        chunk(doc_id="doc_021", doc_title="Minimum Balance Policy", chunk_id="c2",
               chunk_text="LKR 2,500 (2025).", doc_access_level="internal",
               doc_version="v2", effective_date="2025-01-01"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="c1", answer_text="Minimum balance has changed over time.",
                        grounded=True,
                        citations=[
                            Citation(doc_id="doc_020", doc_title="Minimum Balance Policy",
                                      section="Section 1", chunk_id="c1"),
                            Citation(doc_id="doc_021", doc_title="Minimum Balance Policy",
                                      section="Section 1", chunk_id="c2"),
                        ],
                        chunks_used=["c1", "c2"])
    payload = Agent4Input(session_id="c1", user_role="employee",
                            access_level="internal", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "escalated"
    assert result.version_conflict_detected is True
    assert result.final_answer is None


def test_AUD09_version_conflict_where_one_version_is_restricted(llm_pass):
    """AUD-09: Two versions of a doc cited, but the newer version is
    restricted while the session is only internal. Access violation must
    take priority over version-conflict escalation — deny, don't escalate,
    since escalation would still surface a citation to a doc this session
    can't see."""
    a2 = Agent2Output(session_id="c2", access_level="internal", results=[
        chunk(doc_id="doc_020", doc_title="Risk Policy", chunk_id="c1",
               chunk_text="Old risk threshold: 5%.", doc_access_level="internal",
               doc_version="v1", effective_date="2022-01-01"),
        chunk(doc_id="doc_021", doc_title="Risk Policy", chunk_id="c2",
               chunk_text="New risk threshold: 3%.", doc_access_level="restricted",
               doc_version="v2", effective_date="2025-01-01"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="c2", answer_text="Risk threshold has changed.",
                        grounded=True,
                        citations=[
                            Citation(doc_id="doc_020", doc_title="Risk Policy",
                                      section="Section 1", chunk_id="c1"),
                            Citation(doc_id="doc_021", doc_title="Risk Policy",
                                      section="Section 1", chunk_id="c2"),
                        ],
                        chunks_used=["c1", "c2"])
    payload = Agent4Input(session_id="c2", user_role="employee",
                            access_level="internal", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "denied"          # access violation wins over conflict
    assert result.access_reconfirmed is False
    assert result.final_answer is None


# ==========================================================================
# D. CONFIDENCE THRESHOLD BOUNDARY  (CONFIDENCE_THRESHOLD = 0.6)
# ==========================================================================

def test_AUD10_confidence_exactly_at_threshold_is_approved(monkeypatch):
    """AUD-10: confidence == 0.6 (the threshold itself). decide() uses
    strict '<', so exactly-at-threshold should NOT escalate on that
    ground — confirms the boundary is inclusive of the threshold value."""
    monkeypatch.setattr(v, "llm_factual_support_check", lambda a, c: ("pass", v.CONFIDENCE_THRESHOLD))

    a2 = Agent2Output(session_id="d1", access_level="public", results=[
        chunk(doc_id="doc_001", doc_title="Savings Account Guide", chunk_id="c1",
               chunk_text="Minimum balance is LKR 1,000.", doc_access_level="public"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="d1", answer_text="Minimum balance is LKR 1,000.",
                        grounded=True,
                        citations=[Citation(doc_id="doc_001", doc_title="Savings Account Guide",
                                              section="Section 1", chunk_id="c1")],
                        chunks_used=["c1"])
    payload = Agent4Input(session_id="d1", user_role="customer",
                            access_level="public", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "approved"


def test_AUD11_confidence_just_below_threshold_escalates(monkeypatch):
    """AUD-11: confidence = threshold - 0.01. Should escalate."""
    monkeypatch.setattr(v, "llm_factual_support_check",
                          lambda a, c: ("pass", v.CONFIDENCE_THRESHOLD - 0.01))

    a2 = Agent2Output(session_id="d2", access_level="public", results=[
        chunk(doc_id="doc_001", doc_title="Savings Account Guide", chunk_id="c1",
               chunk_text="Minimum balance is LKR 1,000.", doc_access_level="public"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="d2", answer_text="Minimum balance is LKR 1,000.",
                        grounded=True,
                        citations=[Citation(doc_id="doc_001", doc_title="Savings Account Guide",
                                              section="Section 1", chunk_id="c1")],
                        chunks_used=["c1"])
    payload = Agent4Input(session_id="d2", user_role="customer",
                            access_level="public", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "escalated"


def test_AUD12_confidence_just_above_threshold_is_approved(monkeypatch):
    """AUD-12: confidence = threshold + 0.01. Should approve (all else clean)."""
    monkeypatch.setattr(v, "llm_factual_support_check",
                          lambda a, c: ("pass", v.CONFIDENCE_THRESHOLD + 0.01))

    a2 = Agent2Output(session_id="d3", access_level="public", results=[
        chunk(doc_id="doc_001", doc_title="Savings Account Guide", chunk_id="c1",
               chunk_text="Minimum balance is LKR 1,000.", doc_access_level="public"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="d3", answer_text="Minimum balance is LKR 1,000.",
                        grounded=True,
                        citations=[Citation(doc_id="doc_001", doc_title="Savings Account Guide",
                                              section="Section 1", chunk_id="c1")],
                        chunks_used=["c1"])
    payload = Agent4Input(session_id="d3", user_role="customer",
                            access_level="public", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "approved"


# ==========================================================================
# E. STRUCTURAL / MALFORMED INPUT
# ==========================================================================

def test_AUD13_grounded_true_but_no_citations_is_denied(llm_pass):
    """AUD-13: Agent 3 claims grounded=True but provides zero citations —
    Agent 4 must not trust the grounded flag alone; empty citations means
    insufficient evidence regardless of what Agent 3 asserts."""
    a2 = Agent2Output(session_id="e1", access_level="public", results=[
        chunk(doc_id="doc_001", doc_title="Savings Account Guide", chunk_id="c1",
               chunk_text="Minimum balance is LKR 1,000.", doc_access_level="public"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="e1", answer_text="Minimum balance is LKR 1,000.",
                        grounded=True, citations=[], chunks_used=[])
    payload = Agent4Input(session_id="e1", user_role="customer",
                            access_level="public", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "denied"
    assert result.evidence_sufficiency == "insufficient"


def test_AUD14_doc_access_level_case_mismatch(llm_pass):
    """AUD-14 [FINDING]: doc_access_level stored as 'Public' (capitalized)
    instead of the canonical 'public'. ACCESS_RANK.get() with an unknown
    key defaults to 99 (treated as highest/most restrictive), so this
    currently fails CLOSED — a legitimate public doc gets wrongly denied
    rather than leaked. Safe direction to fail, but it's a real robustness
    bug: case drift anywhere upstream (Agent 2, or the doc metadata itself)
    silently breaks legitimate answers instead of surfacing a clear error.
    Recommend normalizing casing at ingestion or making ACCESS_RANK lookups
    case-insensitive.
    """
    a2 = Agent2Output(session_id="e2", access_level="public", results=[
        chunk(doc_id="doc_001", doc_title="Savings Account Guide", chunk_id="c1",
               chunk_text="Minimum balance is LKR 1,000.",
               doc_access_level="Public"),  # <- capitalized, not canonical "public"
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="e2", answer_text="Minimum balance is LKR 1,000.",
                        grounded=True,
                        citations=[Citation(doc_id="doc_001", doc_title="Savings Account Guide",
                                              section="Section 1", chunk_id="c1")],
                        chunks_used=["c1"])
    payload = Agent4Input(session_id="e2", user_role="customer",
                            access_level="public", agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    # Documents current fail-closed behavior on casing drift.
    assert result.decision == "denied"
    assert result.access_reconfirmed is False


def test_AUD15_malformed_session_access_level_fails_closed(llm_pass):
    """AUD-15: session access_level is an empty/invalid string (e.g. a
    corrupted or missing field from Agent 1). ACCESS_RANK.get() defaults
    unknown session levels to 0 (public-equivalent), so any non-public
    doc must still be denied — the system should never accidentally treat
    a malformed access_level as 'allow everything'."""
    a2 = Agent2Output(session_id="e3", access_level="internal", results=[
        chunk(doc_id="doc_005", doc_title="Account Opening Procedure", chunk_id="c1",
               chunk_text="Provide NIC and proof of address.", doc_access_level="internal"),
    ], retrieval_confidence="high")
    a3 = Agent3Output(session_id="e3", answer_text="Provide NIC and proof of address.",
                        grounded=True,
                        citations=[Citation(doc_id="doc_005", doc_title="Account Opening Procedure",
                                              section="Section 1", chunk_id="c1")],
                        chunks_used=["c1"])
    payload = Agent4Input(session_id="e3", user_role="customer",
                            access_level="",  # malformed/missing
                            agent2_output=a2, agent3_output=a3)

    result = run_agent4(payload)
    assert result.decision == "denied"
    assert result.access_reconfirmed is False