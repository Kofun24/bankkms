"""
Manual live-Gemini check: feeds a deliberately WRONG answer (a number the
chunk never mentions) and confirms Gemini's factual-support check catches
it as "fail". If this passes as "pass", your prompt or threshold needs
tightening before you trust it in the pipeline.

Run:
    python test_gemini_catches_hallucination.py
"""

from agent4_verification.verifier import (
    Agent2Output, Agent3Output, Agent4Input, Citation, RetrievedChunk, run_agent4,
)

a2 = Agent2Output(
    session_id="hallucination_check",
    access_level="public",
    results=[
        RetrievedChunk(
            doc_id="doc_001", doc_title="Savings Account Guide", chunk_id="c1",
            chunk_text="The minimum balance for a standard savings account is LKR 1,000.",
            similarity_score=0.9, doc_access_level="public",
            doc_version="v1", effective_date="2024-06-01",
            source_section="Section 2.1",
        )
    ],
    retrieval_confidence="high",
)

# This answer contradicts the chunk (2,000 vs the chunk's 1,000) AND adds a
# claim the chunk never made (a signup bonus). A real answer should never
# look like this, but Agent 4 should catch it if it somehow did.
a3_bad = Agent3Output(
    session_id="hallucination_check",
    answer_text="The minimum balance for a standard savings account is LKR 2,000, "
                 "and new customers get a LKR 500 signup bonus.",
    grounded=True,
    citations=[Citation(doc_id="doc_001", doc_title="Savings Account Guide",
                          section="Section 2.1", chunk_id="c1")],
    chunks_used=["c1"],
)

payload = Agent4Input(
    session_id="hallucination_check", user_role="customer",
    access_level="public", agent2_output=a2, agent3_output=a3_bad,
)

result = run_agent4(payload)

print("decision:              ", result.decision)
print("factual_support_check: ", result.factual_support_check)
print("confidence:             ", result.confidence)
print("final_answer:           ", result.final_answer)

if result.factual_support_check == "fail" and result.decision != "approved":
    print("\n✅ Gemini correctly caught the hallucinated/contradicted claim.")
else:
    print("\n⚠️  Gemini did NOT catch it — this got approved or passed factual check.")
    print("    Review the prompt in llm_factual_support_check() before trusting this in production.")
