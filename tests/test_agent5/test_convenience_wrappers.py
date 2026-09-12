"""
Agent 5 — per-agent convenience wrappers.

log_classification / log_retrieval / log_generation / log_verification
build an AuditLogRecord from a real Agent1-4 Output object. These tests
confirm each wrapper tags the correct LogStage/agent name, snapshots the
real payload, and writes a decision_summary that reflects what actually
happened -- and that all four chain together correctly when called in
pipeline order for one session.
"""

from agent5_audit_logging.logger import (
    log_classification,
    log_generation,
    log_retrieval,
    log_verification,
    verify_chain,
)
from shared.enums import (
    AccessLevel,
    EvidenceSufficiency,
    FactualSupportCheck,
    Intent,
    RetrievalConfidence,
    VerificationDecision,
)


def test_log_classification_tags_correct_stage_and_agent(log_path, make_agent1_output):
    a1 = make_agent1_output()
    record = log_classification(a1, log_path=log_path)
    assert record.stage.value == "classification"
    assert record.agent == "agent1_classification"
    assert record.session_id == a1.session_id


def test_log_classification_summary_reflects_output(log_path, make_agent1_output):
    a1 = make_agent1_output(intent=Intent.POLICY_CHECK, access_level=AccessLevel.INTERNAL)
    record = log_classification(a1, log_path=log_path)
    assert "intent=policy_check" in record.decision_summary
    assert "access_level=internal" in record.decision_summary


def test_log_classification_payload_snapshot_matches_agent1_output(log_path, make_agent1_output):
    a1 = make_agent1_output()
    record = log_classification(a1, log_path=log_path)
    assert record.payload_snapshot["session_id"] == a1.session_id
    assert record.payload_snapshot["intent"] == a1.intent.value


def test_log_retrieval_tags_correct_stage_and_agent(log_path, make_agent2_output):
    a2 = make_agent2_output()
    record = log_retrieval(a2, log_path=log_path)
    assert record.stage.value == "retrieval"
    assert record.agent == "agent2_retrieval"


def test_log_retrieval_summary_reflects_result_count_and_confidence(
    log_path, make_agent2_output, make_chunk
):
    a2 = make_agent2_output(
        results=[make_chunk(), make_chunk(chunk_id="doc_001_c05")],
        retrieval_confidence=RetrievalConfidence.LOW,
    )
    record = log_retrieval(a2, log_path=log_path)
    assert "results=2" in record.decision_summary
    assert "confidence=low" in record.decision_summary


def test_log_generation_tags_correct_stage_and_agent(log_path, make_agent3_output):
    a3 = make_agent3_output()
    record = log_generation(a3, log_path=log_path)
    assert record.stage.value == "generation"
    assert record.agent == "agent3_response"


def test_log_generation_summary_reflects_grounding_and_citation_count(
    log_path, make_agent3_output
):
    a3 = make_agent3_output(grounded=False, citations=[], chunks_used=[])
    record = log_generation(a3, log_path=log_path)
    assert "grounded=False" in record.decision_summary
    assert "citations=0" in record.decision_summary


def test_log_verification_tags_correct_stage_and_agent(log_path, make_agent4_output):
    a4 = make_agent4_output()
    record = log_verification(a4, log_path=log_path)
    assert record.stage.value == "verification"
    assert record.agent == "agent4_verification"


def test_log_verification_summary_reflects_decision_and_reason(
    log_path, make_agent4_output
):
    a4 = make_agent4_output(
        decision=VerificationDecision.DENIED,
        denial_reason="access_violation: cited document(s) exceed session access_level",
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
        factual_support_check=FactualSupportCheck.PASS,
        confidence=0.0,
    )
    record = log_verification(a4, log_path=log_path)
    assert "decision=denied" in record.decision_summary
    assert "access_violation" in record.decision_summary


def test_log_verification_summary_shows_na_when_no_denial_reason(
    log_path, make_agent4_output
):
    a4 = make_agent4_output(decision=VerificationDecision.APPROVED, denial_reason=None)
    record = log_verification(a4, log_path=log_path)
    assert "reason=n/a" in record.decision_summary


def test_all_four_stages_chain_together_for_one_session(
    log_path, make_agent1_output, make_agent2_output, make_agent3_output, make_agent4_output
):
    """Simulates what pipeline.py will do: call all four wrappers in
    order for the same session, then confirm the resulting chain is
    fully intact end to end."""
    a1 = make_agent1_output()
    a2 = make_agent2_output()
    a3 = make_agent3_output()
    a4 = make_agent4_output()

    log_classification(a1, log_path=log_path)
    log_retrieval(a2, log_path=log_path)
    log_generation(a3, log_path=log_path)
    log_verification(a4, log_path=log_path)

    ok, broken = verify_chain(log_path)
    assert ok is True
    assert broken == []