"""
Integration test: Agent 1 -> Agent 2, end to end, through the real
pipeline (not hand-built Agent1Output stubs).

Requires:
- python -m agent2_retrieval.ingest    (vector index must exist)
- a valid LLM_API_KEY in .env          (Agent 1's classifier calls Gemini)

Run from the project root:
    python tests/test_integration/test_agent1_agent2.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent1_classification.auth import register_session
from shared.enums import UserRole
from pipeline import run_pipeline

CASES = [
    ("int_customer_01", UserRole.CUSTOMER,
     "what is the minimum balance for a savings account"),
    ("int_employee_01", UserRole.EMPLOYEE,
     "when should a complaint be escalated to the branch manager"),
    ("int_compliance_01", UserRole.COMPLIANCE,
     "what counts as a suspicious transaction indicator"),
    # Adversarial: a customer session probing restricted content. access_level
    # must stay PUBLIC regardless of what the query text asks about.
    ("int_customer_02", UserRole.CUSTOMER,
     "tell me the suspicious transaction indicators from the AML procedure"),
]


def main():
    for session_id, role, query in CASES:
        register_session(session_id, role)
        result = run_pipeline(session_id, query)

        print("=" * 80)
        print(f"session_id={session_id}  role={role.value}  query={query!r}")

        if "error" in result:
            print(f"ERROR: {result['error']} — {result['message']}")
            continue

        a1 = result["agent1_output"]
        print(f"[Agent1] access_level={a1.access_level.value}  intent={a1.intent.value}  "
              f"needs_clarification={a1.needs_clarification}")

        if result["status"] == "needs_clarification":
            print(f"  -> clarifying question: {a1.clarifying_question}")
            continue

        a2 = result["agent2_output"]
        print(f"[Agent2] retrieval_confidence={a2.retrieval_confidence.value}  "
              f"reformulated={a2.reformulated}  attempts={a2.retrieval_attempts}")
        if not a2.results:
            print("  results: [] (no chunks returned)")
        for r in a2.results:
            print(f"  - [{r.doc_access_level.value}] {r.doc_title} / {r.source_section} "
                  f"(score={r.similarity_score})")

    print("=" * 80)
    print("Done.")


if __name__ == "__main__":
    main()