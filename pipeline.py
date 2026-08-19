"""
pipeline.py

Top-level orchestration for the BankKMS pipeline. Wires agents together in
sequence: Agent 1 -> Agent 2 -> Agent 3 -> Agent 4 (-> Agent 5/6 as hooks).

Currently Agents 1-3 are implemented. Agent 4 is stubbed as a TODO so
the pipeline runs end-to-end (returning early after synthesis) without
crashing, and can be extended as its owner finishes their part.
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
from shared.enums import UserRole
from shared.schemas import Agent1Output, Agent2Output, Agent3Output

# Instantiated once at import time — loading the embedder + vector store on
# every query would be wasteful. Requires `python -m agent2_retrieval.ingest`
# to have been run at least once so the index exists on disk.
_agent2 = Agent2Retriever()

def run_pipeline(session_id: str, raw_query: str) -> dict:
    """
    Runs the full BankKMS pipeline for a single user query.

    Returns a dict with at least `agent1_output`. Once Agent 4 lands,
    this will also include `agent4_output`/`final_response`.
    """
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

    # TODO (Agent 4 owner): call verification here
    # agent4_output = verify_response(agent3_output, agent1_output)

    return {
        "agent1_output": agent1_output,
        "agent2_output": agent2_output,
        "agent3_output": agent3_output,
        "status": "generated_awaiting_verification",
        "message_to_user": agent3_output.answer_text,
    }


if __name__ == "__main__":
    import json

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
        print(f"Grounded?:           {a3.grounded}")
        print(f"Answer:              {a3.answer_text}")
        print(f"Chunks Used:         {a3.chunks_used}")
        print(f"Chunks Discarded:    {a3.chunks_discarded}")
        print(f"Synthesis Notes:     {a3.synthesis_notes}")
        print("Citations:")
        for c in a3.citations:
            print(f"  - [{c.doc_id}] {c.doc_title} / {c.section} (chunk={c.chunk_id})")
    print("------------------------\n")