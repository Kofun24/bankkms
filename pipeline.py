"""
pipeline.py

Top-level orchestration for the BankKMS pipeline. Wires agents together in
sequence: Agent 1 -> Agent 2 -> Agent 3 -> Agent 4 -> Agent 5 (audit log)
-> Agent 6 (escalation).

All six agents are now wired:

  - Agent 1: classification
  - Agent 2: retrieval
  - Agent 3: response generation
  - Agent 4: verification
  - Agent 5: audit logging (every stage logged independently — see note
    below)
  - Agent 6: escalation handoff to human review
"""

from agent1_classification.auth import (
    register_session,
    UnknownSessionError,
    UnauthorizedRoleError,
)
from agent1_classification.classifier import classify_query
from agent1_classification.gemini_classifier import gemini_classify
from agent1_classification.fast_path import check_fast_path
from agent2_retrieval.retriever import Agent2Retriever
from agent3_response.responder import analyze_and_respond
from agent4_verification.db_integration import version_lookup_from_db
from agent4_verification.verifier import run_agent4
from agent5_audit_logging.logger import (
    log_classification,
    log_generation,
    log_retrieval,
    log_verification,
)
from agent6_escalation.escalation import evaluate_escalation
from shared.enums import UserRole
from shared.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Agent4Output,
    Agent6Output,
)


# Instantiated once at import time — loading the embedder + vector store on
# every query would be wasteful. Requires `python -m agent2_retrieval.ingest`
# to have been run at least once so the index exists on disk.
_agent2 = Agent2Retriever()


# Maps the machine-readable reason prefixes verifier.py's decide() produces
# (e.g. "access_violation: ...", "low_retrieval_confidence: ...") to an
# actual user-facing sentence. Matched by prefix so the doc_ids / conflict
# details verifier.py appends after the colon don't break the lookup.
# A reason that doesn't match anything here (shouldn't normally happen,
# but keeps this forward-compatible if decide() ever adds a new branch)
# falls back to a safe generic message rather than crashing.
_REASON_MESSAGES: dict[str, str] = {
    "access_violation": (
        "I can't share that information — it's outside what your account "
        "is authorized to access."
    ),
    
    "insufficient_evidence": (
        "I don't have reliable information in the knowledge base to "
        "answer that confidently."
    ),

    "factual_check_failed": (
        "I found some related information, but couldn't fully confirm its "
        "accuracy, so this has been flagged for review before I can answer "
        "confidently."
    ),

    "version_conflict": (
        "There appear to be multiple versions of this policy on record. "
        "This needs a quick review so you get the current, correct answer."
    ),

    "low_retrieval_confidence": (
        "I couldn't find a strong match for your question in the knowledge "
        "base, so this has been flagged for review."
    ),

    "low_confidence": (
        "I'm not confident enough in this answer yet, so it's been flagged "
        "for a closer look before I respond."
    ),
}


_DENIED_FALLBACK = (
    "I can't provide that information — it may be outside what you're "
    "authorized to access, or I don't have reliable information to answer "
    "confidently."
)

_ESCALATED_FALLBACK = (
    "This needs a closer look before I can answer confidently. It's been "
    "flagged for review."
)


def _message_for_reason(reason: str | None, denied: bool) -> str:
    """Turns verifier.py's internal reason string into the sentence the
    user actually sees. Matches by prefix (reason strings look like
    'access_violation: cited document(s) exceed...') so appended details
    (doc_ids, conflict specifics) don't break the lookup."""
    if reason:
        prefix = reason.split(":", 1)[0].strip()
        if prefix in _REASON_MESSAGES:
            return _REASON_MESSAGES[prefix]

    return _DENIED_FALLBACK if denied else _ESCALATED_FALLBACK


def resolve_pipeline_status(
    agent4_output: Agent4Output,
    agent6_output: Agent6Output,
) -> tuple[str, str]:
    """Resolves final user-facing status and message.

    Status resolution priority:
    1. Legitimate denials (access violation, insufficient evidence):
       Return status="denied" unless a session/security escalation trigger
       (REPEATED_DENIAL or SUSPICIOUS_PATTERN) takes precedence.
    2. Agent 6 escalation (low confidence, version conflict, etc.):
       Return status="escalated" with Agent 6's reassuring message.
    3. Approved answer:
       Return status="answered" with final answer text (and version note if flagged).
    4. Otherwise (e.g. Agent 4 pre-escalated but Agent 6 didn't independently trigger):
       Return status="escalated".
    """
    if agent4_output.decision.value == "denied":
        # A legitimate denial (e.g. insufficient_evidence, access_violation)
        # must return status="denied" rather than being masked as a generic
        # escalation. Only true session/security triggers (e.g. repeated
        # denials or prompt-injection attempts) take precedence.
        if agent6_output.escalation_triggered and agent6_output.trigger_reason in (
            EscalationReason.REPEATED_DENIAL,
            EscalationReason.SUSPICIOUS_PATTERN,
        ):
            return "escalated", agent6_output.user_facing_message
        return "denied", _message_for_reason(agent4_output.denial_reason, denied=True)

    if agent6_output.escalation_triggered:
        return "escalated", agent6_output.user_facing_message

    if agent4_output.decision.value == "approved":
        msg = agent4_output.final_answer or ""
        if agent4_output.version_conflict_detected:
            # Not a blocker — Agent 2 already retrieved only the current
            # version, so the answer itself is correct. This is purely a
            # transparency note: the document has prior versions on
            # record, worth surfacing since policy figures do change.
            msg += (
                "\n\n(Note: this policy has been updated before — the "
                "figures above reflect the current version.)"
            )
        return "answered", msg

    # decision == "escalated" but Agent 6 didn't independently trigger
    return "escalated", _message_for_reason(agent4_output.denial_reason, denied=False)


def run_pipeline(session_id: str, raw_query: str) -> dict:
    """
    Runs the full BankKMS pipeline for a single user query.

    Returns a dict with at least `agent1_output`. On a normal completed
    run it also includes `agent2_output`, `agent3_output`, `agent4_output`,
    `agent5_records`, `agent6_output`, and `final_response` (the actual
    text/citations the caller should show the user, already
    access-controlled and fact-checked by Agent 4, and screened for human
    handoff by Agent 6).
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
        agent1_output,
        agent2_output,
        agent3_output,
        version_lookup=version_lookup_from_db,
    )

    # Every stage gets logged independently, not just the final decision —
    # so a compromised/buggy earlier agent can't also hide its own tracks
    # by the pipeline skipping a log entry on its behalf.
    audit_records = [
        log_classification(agent1_output),
        log_retrieval(agent2_output),
        log_generation(agent3_output),
        log_verification(agent4_output),
    ]

    agent6_output: Agent6Output = evaluate_escalation(
        agent4_output,
        agent1_output,
    )

    status, message_to_user = resolve_pipeline_status(agent4_output, agent6_output)
    # A definitive denial from Agent 4 takes precedence over
    # Agent 6's generic escalation result.
    if agent4_output.decision.value == "denied":
        status = "denied"
        message_to_user = _message_for_reason(
            agent4_output.denial_reason,
            denied=True,
        )

    elif agent6_output.escalation_triggered:
        status = "escalated"
        message_to_user = agent6_output.user_facing_message

    elif agent4_output.decision.value == "approved":
        status = "answered"
        message_to_user = agent4_output.final_answer

        # Not a blocker — Agent 2 already retrieved only the current
        # version, so the answer itself is correct. This is purely a
        # transparency note: the document has prior versions on
        # record, worth surfacing since policy figures do change.
        if agent4_output.version_conflict_detected:
            message_to_user += (
                "\n\n(Note: this policy has been updated before — the "
                "figures above reflect the current version.)"
            )

    else:
        # decision == "escalated" but Agent 6 didn't independently trigger
        status = "escalated"
        message_to_user = _message_for_reason(
            agent4_output.denial_reason,
            denied=False,
        )

    return {
        "agent1_output": agent1_output,
        "agent2_output": agent2_output,
        "agent3_output": agent3_output,
        "agent4_output": agent4_output,
        "agent5_records": audit_records,
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

    result = run_pipeline(
        "demo_session",
        "What documents do I need to open a savings account?",
    )

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
        print(f"Query Used:           {a2.query_used}")
        print(f"Reformulated?:        {a2.reformulated}")
        print(f"Retrieval Attempts:   {a2.retrieval_attempts}")
        print(f"Retrieval Confidence: {a2.retrieval_confidence.value}")
        print(f"Access Filter Applied: {a2.access_filter_applied}")
        print(f"Results ({len(a2.results)}):")

        for r in a2.results:
            print(
                f"  - [{r.doc_access_level.value}] "
                f"{r.doc_title} / {r.source_section} "
                f"(score={r.similarity_score})"
            )

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
        print(f"Decision:             {a4.decision.value}")
        print(f"Denial Reason:        {a4.denial_reason}")
        print(f"Evidence Sufficient:  {a4.evidence_sufficiency.value}")
        print(f"Factual Check:        {a4.factual_support_check.value}")
        print(f"Version Conflict?:    {a4.version_conflict_detected}")

        if a4.version_conflict_detected:
            print(f"Conflict Details:     {a4.conflict_details}")

        print(f"Access Reconfirmed?:  {a4.access_reconfirmed}")
        print(f"Confidence:           {a4.confidence}")

        if a4.final_answer:
            print(f"\nFINAL ANSWER: {a4.final_answer}")

            for c in a4.final_citations:
                print(f"  source: {c.doc_title} ({c.section})")

        else:
            print(
                f"\nFINAL ANSWER: "
                f"[withheld — {a4.decision.value}]"
            )

    if "agent5_records" in result:
        print("\n--- Agent 5 Output (audit log) ---")

        for rec in result["agent5_records"]:
            print(f"[{rec.stage.value}] log_id={rec.log_id}")
            print(f"    agent:      {rec.agent}")
            print(f"    summary:    {rec.decision_summary}")
            print(f"    hash:       {rec.immutable_hash}")
            print(f"    timestamp:  {rec.timestamp}")

    if "agent6_output" in result:
        a6 = result["agent6_output"]

        print("\n--- Agent 6 Output ---")
        print(
            f"Escalation Triggered?: "
            f"{a6.escalation_triggered}"
        )

        if a6.escalation_triggered:
            print(f"Trigger Reason:        {a6.trigger_reason.value}")
            print(f"Routed To:             {a6.routed_to}")
            print(f"Priority:              {a6.priority.value}")
            print(
                f"User-Facing Message:   "
                f"{a6.user_facing_message}"
            )

    print("------------------------\n")