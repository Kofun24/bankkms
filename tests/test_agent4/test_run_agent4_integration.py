"""
Agent 4 — end-to-end `run_agent4()` integration tests.

These build full Agent1Output / Agent2Output / Agent3Output payloads (as
Agents 1-3 actually hand off) and check the final Agent4Output, including
the fields downstream systems / the audit log (Agent 5) would rely on.

Important: with no Gemini client configured, the offline fallback
heuristic caps factual confidence at 0.5, which is below the default
CONFIDENCE_THRESHOLD (0.6) -- so an "approved" outcome in these tests
always requires the `fake_gemini` fixture to simulate a real LLM
verdict with confidence >= threshold. Tests that don't care about
factual confidence use the fallback as-is.

These do NOT exercise the real database-backed version_lookup (that
needs a live DB) -- run_live_query.py at the project root is the real
end-to-end proof against actual data.
"""

import json

from agent4_verification.verifier import run_agent4
from shared.enums import AccessLevel, RetrievalConfidence, VerificationDecision


def test_approved_requires_a_confident_llm_pass(happy_path, fake_gemini):
    fake_gemini('{"verdict": "pass", "confidence": 0.92, "reason": "fully grounded"}')

    result = run_agent4(happy_path["agent1"], happy_path["agent2"], happy_path["agent3"])

    assert result.decision == VerificationDecision.APPROVED
    assert result.denial_reason is None
    assert result.evidence_sufficiency.value == "sufficient"
    assert result.factual_support_check.value == "pass"
    assert result.version_conflict_detected is False
    assert result.access_reconfirmed is True
    assert result.final_answer == happy_path["agent3"].answer_text
    assert len(result.final_citations) == 1
    assert result.final_citations[0].doc_id == happy_path["citation"].doc_id
    assert result.final_citations[0].doc_title == happy_path["citation"].doc_title
    assert result.final_citations[0].section == happy_path["citation"].section
    assert result.confidence == 0.92
    assert result.session_id == happy_path["agent3"].session_id


def test_offline_fallback_alone_is_never_enough_to_approve(happy_path):
    """No Gemini configured -> fallback confidence 0.5 < default
    threshold 0.6 -> the system must escalate for human review rather
    than silently approving an answer nobody actually fact-checked."""
    result = run_agent4(happy_path["agent1"], happy_path["agent2"], happy_path["agent3"])

    assert result.decision == VerificationDecision.ESCALATED
    assert result.factual_support_check.value == "pass"  # heuristic still "passes" it
    assert result.confidence == 0.5
    assert result.final_answer is None
    assert result.final_citations == []


def test_denied_on_access_violation_never_leaks_the_answer(
    make_chunk, make_citation, make_agent1_output, make_agent2_output,
    make_agent3_output, fake_gemini,
):
    """Even if the LLM would happily confirm the answer is factually
    supported, a restricted-tier chunk cited into a public session must
    be denied -- and the answer/citations must never be returned."""
    fake_gemini('{"verdict": "pass", "confidence": 0.99, "reason": "supported"}')

    restricted_chunk = make_chunk(
        doc_id="doc_009", chunk_id="doc_009_c01",
        doc_title="AML Procedure", doc_access_level=AccessLevel.RESTRICTED,
        chunk_text="Suspicious transaction threshold is $10,000.",
    )
    citation = make_citation(
        doc_id="doc_009", doc_title="AML Procedure",
        section="Section 1.0", chunk_id="doc_009_c01",
    )
    agent1 = make_agent1_output(access_level=AccessLevel.PUBLIC)
    agent2 = make_agent2_output(access_level=AccessLevel.PUBLIC, results=[restricted_chunk])
    agent3 = make_agent3_output(
        answer_text="Suspicious transaction threshold is $10,000.",
        citations=[citation],
        chunks_used=["doc_009_c01"],
    )

    result = run_agent4(agent1, agent2, agent3)

    assert result.decision == VerificationDecision.DENIED
    assert "access_violation" in result.denial_reason
    assert "doc_009" in result.denial_reason
    assert result.final_answer is None
    assert result.final_citations == []


def test_denied_on_insufficient_evidence(
    make_agent1_output, make_agent2_output, make_agent3_output
):
    """Agent 3 produced an ungrounded answer (e.g. it fell back to
    general knowledge) -- Agent 4 must deny outright, not escalate."""
    agent1 = make_agent1_output()
    agent2 = make_agent2_output(results=[])
    agent3 = make_agent3_output(grounded=False, citations=[], chunks_used=[])

    result = run_agent4(agent1, agent2, agent3)

    assert result.decision == VerificationDecision.DENIED
    assert "insufficient_evidence" in result.denial_reason
    assert result.final_answer is None


def test_approved_despite_version_conflict_when_everything_else_checks_out(
    make_chunk, make_citation, make_agent1_output, make_agent2_output,
    make_agent3_output, fake_gemini,
):
    """Version conflict is informational, not a blocker. Agent 2 only
    ever retrieves the current version of a document, so a conflict just
    means the document has prior history -- the answer itself, built
    from the citations Agent 2/3 actually returned, is still correct and
    should be released to the user. The conflict is still visible via
    version_conflict_detected/conflict_details (e.g. for pipeline.py to
    attach a transparency note, or for the audit log), it just doesn't
    withhold the answer the way an access violation or a failed factual
    check does."""
    fake_gemini('{"verdict": "pass", "confidence": 0.97, "reason": "supported"}')

    chunk_v1 = make_chunk(
        doc_id="doc_010", chunk_id="c1", doc_title="Minimum Balance Policy",
        doc_version="v1", effective_date="2024-01-01",
        chunk_text="Minimum balance is LKR 1,000.",
    )
    chunk_v2 = make_chunk(
        doc_id="doc_010b", chunk_id="c2", doc_title="Minimum Balance Policy",
        doc_version="v2", effective_date="2025-06-01",
        chunk_text="Minimum balance is LKR 2,500.",
    )
    cit_v1 = make_citation(doc_id="doc_010", doc_title="Minimum Balance Policy", chunk_id="c1")
    cit_v2 = make_citation(doc_id="doc_010b", doc_title="Minimum Balance Policy", chunk_id="c2")

    agent1 = make_agent1_output()
    agent2 = make_agent2_output(results=[chunk_v1, chunk_v2])
    agent3 = make_agent3_output(
        answer_text="The minimum balance has been LKR 1,000, now updated to LKR 2,500.",
        citations=[cit_v1, cit_v2],
        chunks_used=["c1", "c2"],
    )

    result = run_agent4(agent1, agent2, agent3)

    assert result.decision == VerificationDecision.APPROVED
    assert result.version_conflict_detected is True
    assert "Minimum Balance Policy" in result.conflict_details
    assert result.final_answer is not None
    assert result.denial_reason is None


def test_escalated_on_low_retrieval_confidence(happy_path, fake_gemini, make_agent2_output):
    fake_gemini('{"verdict": "pass", "confidence": 0.9, "reason": "supported"}')
    low_confidence_agent2 = make_agent2_output(
        results=happy_path["agent2"].results,
        retrieval_confidence=RetrievalConfidence.LOW,
    )

    result = run_agent4(happy_path["agent1"], low_confidence_agent2, happy_path["agent3"])

    assert result.decision == VerificationDecision.ESCALATED
    assert result.final_answer is None


def test_escalated_on_factual_check_failure(happy_path, fake_gemini):
    fake_gemini('{"verdict": "fail", "confidence": 0.1, "reason": "unsupported number"}')

    result = run_agent4(happy_path["agent1"], happy_path["agent2"], happy_path["agent3"])

    assert result.decision == VerificationDecision.ESCALATED
    assert result.factual_support_check.value == "fail"
    assert result.final_answer is None


def test_output_is_json_serializable(happy_path, fake_gemini):
    """Sanity check for whatever consumes Agent 4's output downstream
    (API response, Agent 5 audit log, etc.) -- Pydantic's
    model_dump_json() must round-trip through json.loads without error."""
    fake_gemini('{"verdict": "pass", "confidence": 0.9, "reason": "ok"}')
    result = run_agent4(happy_path["agent1"], happy_path["agent2"], happy_path["agent3"])

    serialized = result.model_dump_json()
    assert isinstance(serialized, str)

    reloaded = json.loads(serialized)
    assert reloaded["decision"] == "approved"
    assert reloaded["session_id"] == happy_path["agent3"].session_id