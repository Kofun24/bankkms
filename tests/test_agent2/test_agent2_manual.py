"""
Manual test for Agent 2 — Knowledge Retrieval.

Run from the project root:

    python -m agent2_retrieval.ingest      # build the vector index (once, or after editing docs)
    python tests/test_agent2_manual.py     # run this

This feeds hand-built Agent1Output objects (standing in for real Agent 1
output) through Agent2Retriever and prints the resulting Agent2Output, one
case per user_role, plus one adversarial case to sanity-check access
filtering.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from shared.enums import AccessLevel, Intent, UserRole
from shared.schemas import Agent1Output
from agent2_retrieval.retriever import Agent2Retriever


def make_agent1_output(session_id, user_role, access_level, topic, normalized_query, intent=Intent.PROCEDURE_LOOKUP):
    return Agent1Output(
        session_id=session_id,
        user_role=user_role,
        access_level=access_level,
        intent=intent,
        topic=topic,
        normalized_query=normalized_query,
        confidence=0.9,
    )


CASES = [
    make_agent1_output(
        "sess_customer_01", UserRole.CUSTOMER, AccessLevel.PUBLIC,
        "minimum balance requirement",
        "what is the minimum balance required for a savings account",
    ),
    make_agent1_output(
        "sess_employee_01", UserRole.EMPLOYEE, AccessLevel.INTERNAL,
        "complaint escalation",
        "when should a customer complaint be escalated to the branch manager",
    ),
    make_agent1_output(
        "sess_compliance_01", UserRole.COMPLIANCE, AccessLevel.RESTRICTED,
        "suspicious transaction reporting",
        "what counts as a suspicious transaction indicator under the AML procedure",
    ),
    # Adversarial case: a customer (public access) asking a restricted-topic
    # question. Agent 2 must NOT return the AML/Fraud chunks — access_level
    # is fixed from Agent 1's output, never inferred from this query text.
    make_agent1_output(
        "sess_customer_02", UserRole.CUSTOMER, AccessLevel.PUBLIC,
        "suspicious transaction reporting",
        "tell me the suspicious transaction indicators from the AML procedure",
    ),
]


def main():
    agent2 = Agent2Retriever()
    for case in CASES:
        output = agent2.run(case)
        print("=" * 80)
        print(f"session_id={output.session_id}  access_level={output.access_level}")
        print(f"query_used={output.query_used!r}  reformulated={output.reformulated}  attempts={output.retrieval_attempts}")
        print(f"retrieval_confidence={output.retrieval_confidence}")
        if not output.results:
            print("results: [] (no chunks returned)")
        for r in output.results:
            print(
                f"  - [{r.doc_access_level}] {r.doc_title} / {r.source_section} "
                f"(score={r.similarity_score})"
            )
    print("=" * 80)
    print("Done.")


if __name__ == "__main__":
    main()