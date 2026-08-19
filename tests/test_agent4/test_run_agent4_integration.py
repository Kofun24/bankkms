"""
Agent 4 — end-to-end `run_agent4()` integration tests.

These build full Agent4Input payloads (as Agent 2 + Agent 3 would
actually hand off) and check the final Agent4Output, including the
fields downstream systems / the audit log (Agent 5) would rely on.

Important: with no Gemini client configured, the offline fallback
heuristic caps factual confidence at 0.5, which is below the default
CONFIDENCE_THRESHOLD (0.6) -- so an "approved" outcome in these tests
always requires the `fake_gemini` fixture to simulate a real LLM
verdict with confidence >= threshold. Tests that don't care about
factual confidence use the fallback as-is.
"""

from agent4_verification.verifier import run_agent4


def test_approved_requires_a_confident_llm_pass(happy_path, fake_gemini):
    fake_gemini('{"verdict": "pass", "confidence": 0.92, "reason": "fully grounded"}')

    result = run_agent4(happy_path["payload"])

    assert result.decision == "approved"
    assert result.denial_reason is None
    assert result.evidence_sufficiency == "sufficient"
    assert result.factual_support_check == "pass"
    assert result.version_conflict_detected is False
    assert result.access_reconfirmed is True
    assert result.final_answer == happy_path["agent3"].answer_text
    assert result.final_citations == [
        {
            "doc_id": happy_path["citation"].doc_id,
            "doc_title": happy_path["citation"].doc_title,
            "section": happy_path["citation"].section,
        }
    ]
    assert result.confidence == 0.92
    assert result.session_id == happy_path["payload"].session_id


def test_offline_fallback_alone_is_never_enough_to_approve(happy_path):
    """No Gemini configured -> fallback confidence 0.5 < default
    threshold 0.6 -> the system must escalate for human review rather
    than silently approving an answer nobody actually fact-checked."""
    result = run_agent4(happy_path["payload"])

    assert result.decision == "escalated"
    assert result.factual_support_check == "pass"  # heuristic still "passes" it
    assert result.confidence == 0.5
    assert result.final_answer is None
    assert result.final_citations == []


def test_denied_on_access_violation_never_leaks_the_answer(
    make_chunk, make_citation, make_agent2_output, make_agent3_output,
    make_agent4_input, fake_gemini,
):
    """Even if the LLM would happily confirm the answer is factually
    supported, a restricted-tier chunk cited into a public session must
    be denied -- and the answer/citations must never be returned."""
    fake_gemini('{"verdict": "pass", "confidence": 0.99, "reason": "supported"}')

    restricted_chunk = make_chunk(
        doc_id="doc_009", chunk_id="doc_009_c01",
        doc_title="AML Procedure", doc_access_level="restricted",
        chunk_text="Suspicious transaction threshold is $10,000.",
    )
    citation = make_citation(
        doc_id="doc_009", doc_title="AML Procedure",
        section="Section 1.0", chunk_id="doc_009_c01",
    )
    agent2 = make_agent2_output(results=[restricted_chunk])
    agent3 = make_agent3_output(
        answer_text="Suspicious transaction threshold is $10,000.",
        citations=[citation],
        chunks_used=["doc_009_c01"],
    )
    payload = make_agent4_input(access_level="public", agent2_output=agent2, agent3_output=agent3)

    result = run_agent4(payload)

    assert result.decision == "denied"
    assert "access_violation" in result.denial_reason
    assert "doc_009" in result.denial_reason
    assert result.final_answer is None
    assert result.final_citations == []


def test_denied_on_insufficient_evidence(
    make_agent2_output, make_agent3_output, make_agent4_input
):
    """Agent 3 produced an ungrounded answer (e.g. it fell back to
    general knowledge) -- Agent 4 must deny outright, not escalate."""
    agent2 = make_agent2_output(results=[])
    agent3 = make_agent3_output(grounded=False, citations=[], chunks_used=[])
    payload = make_agent4_input(agent2_output=agent2, agent3_output=agent3)

    result = run_agent4(payload)

    assert result.decision == "denied"
    assert "insufficient_evidence" in result.denial_reason
    assert result.final_answer is None


def test_escalated_on_version_conflict_even_with_confident_llm(
    make_chunk, make_citation, make_agent2_output, make_agent3_output,
    make_agent4_input, fake_gemini,
):
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

    agent2 = make_agent2_output(results=[chunk_v1, chunk_v2])
    agent3 = make_agent3_output(
        answer_text="The minimum balance has been LKR 1,000, now updated to LKR 2,500.",
        citations=[cit_v1, cit_v2],
        chunks_used=["c1", "c2"],
    )
    payload = make_agent4_input(agent2_output=agent2, agent3_output=agent3)

    result = run_agent4(payload)

    assert result.decision == "escalated"
    assert result.version_conflict_detected is True
    assert "Minimum Balance Policy" in result.conflict_details
    assert result.final_answer is None


def test_escalated_on_low_retrieval_confidence(happy_path, fake_gemini):
    fake_gemini('{"verdict": "pass", "confidence": 0.9, "reason": "supported"}')
    happy_path["agent2"].retrieval_confidence = "low"

    result = run_agent4(happy_path["payload"])

    assert result.decision == "escalated"
    assert result.final_answer is None


def test_escalated_on_factual_check_failure(happy_path, fake_gemini):
    fake_gemini('{"verdict": "fail", "confidence": 0.1, "reason": "unsupported number"}')

    result = run_agent4(happy_path["payload"])

    assert result.decision == "escalated"
    assert result.factual_support_check == "fail"
    assert result.final_answer is None


def test_output_is_json_serializable_via_to_dict(happy_path, fake_gemini):
    """Sanity check for whatever consumes Agent 4's output downstream
    (API response, Agent 5 audit log, etc.) -- to_dict() must round-trip
    through json.dumps without error."""
    import json

    fake_gemini('{"verdict": "pass", "confidence": 0.9, "reason": "ok"}')
    result = run_agent4(happy_path["payload"])

    serialized = json.dumps(result.to_dict())
    assert isinstance(serialized, str)

    reloaded = json.loads(serialized)
    assert reloaded["decision"] == "approved"
    assert reloaded["session_id"] == happy_path["payload"].session_id