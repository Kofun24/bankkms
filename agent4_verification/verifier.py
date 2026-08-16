def verify(agent1_output: dict, agent2_output: dict, agent3_output: dict) -> dict:
    # TODO: replace with real checks - evidence sufficiency, factual support, conflicts, access
    if not agent2_output["retrieved_chunks"]:
        return {
            "final_answer": None,
            "status": "knowledge_gap",
            "reason": "There is insufficient approved information to answer this question.",
            "sources_confirmed": [],
        }
    return {
        "final_answer": agent3_output["draft_answer"],
        "status": "approved",
        "reason": None,
        "sources_confirmed": agent3_output["cited_sources"],
    }


if __name__ == "__main__":
    mock_a1 = {"user_role": "customer", "access_level": "public"}
    mock_a2 = {"retrieved_chunks": [], "retrieval_confidence": "low", "retry_attempted": False}
    mock_a3 = {"draft_answer": "PLACEHOLDER", "cited_sources": [], "confidence": "low"}
    print(verify(mock_a1, mock_a2, mock_a3))