def generate_response(agent1_output: dict, agent2_output: dict) -> dict:
    # TODO: replace with real LLM-backed generation, using retrieved_chunks only
    if not agent2_output["retrieved_chunks"]:
        return {
            "draft_answer": "No information available in the knowledge base for this question.",
            "cited_sources": [],
            "confidence": "low",
        }
    return {"draft_answer": "PLACEHOLDER", "cited_sources": [], "confidence": "low"}


if __name__ == "__main__":
    mock_a1 = {"original_question": "What documents do I need to open a savings account?"}
    mock_a2 = {"retrieved_chunks": [], "retrieval_confidence": "low", "retry_attempted": False}
    print(generate_response(mock_a1, mock_a2))