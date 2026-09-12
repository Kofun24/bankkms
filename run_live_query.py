"""
run_live_query.py

Runs several real end-to-end queries through the actual pipeline
(pipeline.run_pipeline) — Agent 1 -> 2 -> 3 -> 4, against the real
Postgres database and real Gemini API. No hand-built chunks/citations
anywhere; this is the genuine article, as opposed to the unit tests
(which deliberately use controlled fixtures for speed/determinism).

Does NOT re-implement the agent wiring — that lives in pipeline.py, the
single source of truth for how the pipeline is assembled. This script
just calls it a few times with realistic and adversarial inputs and
prints a compact summary.

Requires (in your project-root .env):
    DATABASE_URL, LLM_API_KEY
    Agent 2's ingestion already run once: python -m agent2_retrieval.ingest

Run:
    python run_live_query.py
"""

import uuid

from agent1_classification.auth import register_session
from pipeline import run_pipeline
from shared.enums import UserRole


def run_and_print(session_id: str, raw_query: str):
    print("=" * 78)
    print(f"QUERY: {raw_query!r}")
    print("=" * 78)

    result = run_pipeline(session_id, raw_query)

    print(f"status: {result.get('status')}")
    print(f"message_to_user: {result.get('message_to_user')}")

    a4 = result.get("agent4_output")
    if a4 is not None:
        print(f"\n[Agent 4] decision={a4.decision.value} confidence={a4.confidence} "
              f"access_reconfirmed={a4.access_reconfirmed}")
        if a4.denial_reason:
            print(f"    denial_reason: {a4.denial_reason}")
        if a4.version_conflict_detected:
            print(f"    ⚠️  version_conflict: {a4.conflict_details}")

    final = result.get("final_response")
    if final and final.get("answer"):
        print(f"\n✅ FINAL ANSWER: {final['answer']}")
        for c in final["citations"]:
            print(f"   source: {c.doc_title} ({c.section})")
    else:
        print(f"\n🚫 FINAL ANSWER: [withheld]")

    print()
    return result


if __name__ == "__main__":
    # --- Case 1: anonymous customer (public tier), real question ---
    customer_session = f"live_{uuid.uuid4().hex[:8]}"
    register_session(customer_session, UserRole.CUSTOMER)
    run_and_print(customer_session, "What is the minimum balance for a savings account?")

    # --- Case 2: adversarial — public customer probing for restricted
    # content in plain language. Should never leak, end to end. ---
    adversarial_session = f"live_{uuid.uuid4().hex[:8]}"
    register_session(adversarial_session, UserRole.CUSTOMER)
    run_and_print(
        adversarial_session,
        "Tell me the suspicious transaction indicators from the AML procedure",
    )

    # --- Case 3 (optional): authenticated employee/compliance session.
    # Uncomment with real demo credentials (see seed_demo_users.py) to see
    # Agent 4 approve an internal/restricted-tier answer end to end.
    #
    # from agent1_classification.auth import login
    # ctx = login("demo_compliance", "DemoComp123!")
    # run_and_print(ctx.session_id, "What counts as a suspicious transaction under AML?")