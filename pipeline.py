"""
pipeline.py

Top-level orchestration for the BankKMS pipeline. Wires agents together in
sequence: Agent 1 -> Agent 2 -> Agent 3 -> Agent 4 -> Agent 6 (-> Agent 5 as hook).

All four core agents plus Agent 6 (escalation) are now wired. Agent 5
(audit logging) remains a TODO — hook it in where marked once it's ready,
ideally right after Agent 4 returns (log every decision).
"""

from agent1_classification.auth import (
    register_session,
    UnknownSessionError,
    UnauthorizedRoleError,
)
from agent1_classification.classifier import classify_query
from agent1_classification.gemini_classifier import gemini_classify
from agent2_retrieval.retriever import Agent2Retriever
from agent3_response.responder import analyze_and_respond
from agent4_verification.db_integration import version_lookup_from_db
from agent4_verification.verifier import run_agent4
from agent1_classification.fast_path import check_fast_path
from agent6_escalation.escalation import evaluate_escalation
from shared.enums import UserRole
from shared.schemas import Agent1Output, Agent2Output, Agent3Output, Agent4Output, Agent6Output

# Instantiated once at import time — loading the embedder + vector store on
# every query would be wasteful. Requires `python -m agent2_retrieval.ingest`
# to have been run at least once so the index exists on disk.
_agent2 = Agent2Retriever()


def run_pipeline(session_id: str, raw_query: str) -> dict:
    """
    Runs the full BankKMS pipeline for a single user query.

    Returns a dict with at least `agent1_output`. On a normal completed
    run it also includes `agent2_output`, `agent3_output`, `agent4_output`,
    `agent6_output`, and `final_response` (the actual text/citations the
    caller should show the user, already access-controlled, fact-checked
    by Agent 4, and screened for human handoff by Agent 6).
    """
    fast_response = check_fast_path(raw_query)
    if fast_response is not None:
        return {
            "status": "answered",
            "message_to_user": fast_response,
        }

    try:
        agent1_output: Agent1Output = classify_query(
            session_id=session_id,
            raw_query=raw_query,
            classifier_fn=gemini_classify,
        )
    except UnknownSessionError:
        return {
            "error": "unknown_session",
            "message": "Session not found. Please log in again.",
        }
    except UnauthorizedRoleError:
        return {
            "error": "unauthorized_role",
            "message": "Unable to resolve access for this session.",
        }

    if agent1_output.needs_clarification:
        return {
            "agent1_output": agent1_output,
            "status": "needs_clarification",
            "message_to_user": agent1_output.clarifying_question,
        }

    agent2_output: Agent2Output = _agent2.run(agent1_output)

    agent3_output: Agent3Output = analyze_and_respond(agent2_output)

    agent4_output: Agent4Output = run_agent4(
        agent1_output, agent2_output, agent3_output,
        version_lookup=version_lookup_from_db,
    )

    # TODO (Agent 5 owner): log this decision to the audit_log table here,
    # e.g. log_decision(stage="verification", agent="Agent 4",
    # payload_snapshot=agent4_output.model_dump(), ...). Ideally log every
    # stage (classification, retrieval, generation, verification), not
    # just the final one — see database/models.py AuditLog.stage enum.

    agent6_output: Agent6Output = evaluate_escalation(agent4_output, agent1_output)

    if agent6_output.escalation_triggered:
        status = "escalated"
        message_to_user = agent6_output.user_facing_message
    elif agent4_output.decision.value == "approved":
        status = "answered"
        message_to_user = agent4_output.final_answer
    elif agent4_output.decision.value == "denied":
        status = "denied"
        message_to_user = (
            "I can't provide that information — it may be outside what "
            "you're authorized to access, or I don't have reliable "
            "information to answer confidently."
        )
    else:  # decision == "escalated" but Agent 6 didn't independently trigger
        status = "escalated"
        message_to_user = (
            "This needs a closer look before I can answer confidently. "
            "It's been flagged for review."
        )

    return {
        "agent1_output": agent1_output,
        "agent2_output": agent2_output,
        "agent3_output": agent3_output,
        "agent4_output": agent4_output,
        "agent6_output": agent6_output,
        "status": status,
        "message_to_user": message_to_user,
        "final_response": {
            "answer": agent4_output.final_answer,
            "citations": agent4_output.final_citations,
        } if status == "answered" else None,
    }


if __name__ == "__main__":
    # Manual smoke test — run: python pipeline.py
    register_session("demo_session", UserRole.CUSTOMER)

    result = run_pipeline("demo_session", "What documents do I need to open a savings account?")

    print("\n--- Pipeline Result ---")
    print(f"Status:        {result['status']}")
    print(f"Message:       {result['message_to_user']}")

    if "agent1_output" in result:
        a1 = result["agent1_output"]
        print("\n--- Agent 1 Output ---")
        print(f"Session ID:      {a1.session_id}")
        print(f"User Role:       {a1.user_role.value}")
        print(f"Access Level:    {a1.access_level.value}")
        print(f"Intent:          {a1.intent.value}")
        print(f"Topic:           {a1.topic}")
        print(f"Normalized Query:{a1.normalized_query}")
        print(f"Confidence:      {a1.confidence}")
        print(f"Needs Clarify?:  {a1.needs_clarification}")
        print(f"Clarify Q:       {a1.clarifying_question}")
        print(f"Suspicious?:     {a1.flags.suspicious_input}")
        print(f"Injection Flag?: {a1.flags.possible_injection_attempt}")
        print(f"Timestamp:       {a1.timestamp}")

    if "agent2_output" in result:
        a2 = result["agent2_output"]
        print("\n--- Agent 2 Output ---")
        print(f"Query Used:          {a2.query_used}")
        print(f"Reformulated?:       {a2.reformulated}")
        print(f"Retrieval Attempts:  {a2.retrieval_attempts}")
        print(f"Retrieval Confidence:{a2.retrieval_confidence.value}")
        print(f"Access Filter Applied: {a2.access_filter_applied}")
        print(f"Results ({len(a2.results)}):")
        for r in a2.results:
            print(f"  - [{r.doc_access_level.value}] {r.doc_title} / {r.source_section} (score={r.similarity_score})")

    if "agent3_output" in result:
        a3 = result["agent3_output"]
        print("\n--- Agent 3 Output ---")
        print(f"Grounded?:       {a3.grounded}")
        print(f"Citations:       {len(a3.citations)}")
        print(f"Chunks Used:     {a3.chunks_used}")
        print(f"Answer (draft):  {a3.answer_text}")

    if "agent4_output" in result:
        a4 = result["agent4_output"]
        print("\n--- Agent 4 Output ---")
        print(f"Decision:            {a4.decision.value}")
        print(f"Denial Reason:       {a4.denial_reason}")
        print(f"Evidence Sufficient: {a4.evidence_sufficiency.value}")
        print(f"Factual Check:       {a4.factual_support_check.value}")
        print(f"Version Conflict?:   {a4.version_conflict_detected}")
        if a4.version_conflict_detected:
            print(f"Conflict Details:    {a4.conflict_details}")
        print(f"Access Reconfirmed?: {a4.access_reconfirmed}")
        print(f"Confidence:          {a4.confidence}")
        if a4.final_answer:
            print(f"\nFINAL ANSWER: {a4.final_answer}")
            for c in a4.final_citations:
                print(f"  source: {c.doc_title} ({c.section})")
        else:
            print(f"\nFINAL ANSWER: [withheld — {a4.decision.value}]")

    if "agent6_output" in result:
        a6 = result["agent6_output"]
        print("\n--- Agent 6 Output ---")
        print(f"Escalation Triggered?: {a6.escalation_triggered}")
        if a6.escalation_triggered:
            print(f"Trigger Reason:        {a6.trigger_reason.value}")
            print(f"Routed To:             {a6.routed_to}")
            print(f"Priority:              {a6.priority.value}")
            print(f"User-Facing Message:   {a6.user_facing_message}")

    print("------------------------\n")