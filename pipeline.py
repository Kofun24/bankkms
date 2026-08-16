from agent1_classification.classifier import classify
from agent2_retrieval.retriever import retrieve
from agent3_response.responder import generate_response
from agent4_verification.verifier import verify


def run_pipeline(question: str, user_role: str) -> dict:
    a1 = classify(question, user_role)
    if a1["needs_clarification"]:
        return {"status": "clarification_needed", "question": a1["clarification_question"]}
    a2 = retrieve(a1)
    a3 = generate_response(a1, a2)
    a4 = verify(a1, a2, a3)
    return a4


if __name__ == "__main__":
    print(run_pipeline("What documents do I need to open a savings account?", "customer"))