"""
pipeline.py

Top-level orchestration for the BankKMS pipeline. Wires agents together in
sequence: Agent 1 -> Agent 2 -> Agent 3 -> Agent 4 (-> Agent 5/6 as hooks).

Currently only Agent 1 is implemented. Agents 2-4 are stubbed as TODOs so
the pipeline runs end-to-end (returning early after classification) without
crashing, and can be extended agent-by-agent as teammates finish their parts.
"""

from agent1_classification.auth import (
    register_session,
    UnknownSessionError,
    UnauthorizedRoleError,
)
from agent1_classification.classifier import classify_query
from agent1_classification.gemini_classifier import gemini_classify
from shared.enums import UserRole
from shared.schemas import Agent1Output


def run_pipeline(session_id: str, raw_query: str) -> dict:
    """
    Runs the full BankKMS pipeline for a single user query.

    Returns a dict with at least `agent1_output`. Once Agents 2-4 land,
    this will also include `agent2_output`, `agent3_output`, `final_response`.
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

    # TODO (Agent 2 owner): call knowledge retrieval here
    # agent2_output = retrieve_knowledge(agent1_output)

    # TODO (Agent 3 owner): call response synthesis here
    # agent3_output = generate_response(agent2_output)

    # TODO (Agent 4 owner): call verification here
    # agent4_output = verify_response(agent3_output, agent1_output)

    return {
        "agent1_output": agent1_output,
        "status": "classified_awaiting_retrieval",
        "message_to_user": (
            "Query classified successfully. Retrieval pipeline not yet connected."
        ),
    }


if __name__ == "__main__":
    # Manual smoke test — run: python pipeline.py
    register_session("demo_session", UserRole.CUSTOMER)

    result = run_pipeline("demo_session", "What documents do I need to open a savings account?")
    print(result)