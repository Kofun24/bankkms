# Agent Interfaces (JSON shapes)

## Agent 1 → Agent 2
{
  "user_role": "customer | employee | compliance_officer",
  "intent": "account_opening | aml | loan_inquiry | complaint | ...",
  "topic": "savings_account | current_account | aml_policy | ...",
  "access_level": "public | internal | restricted",
  "original_question": "string",
  "needs_clarification": false,
  "clarification_question": null
}

## Agent 2 → Agent 3
{
  "retrieved_chunks": [
    {
      "text": "string",
      "source_document": "string",
      "access_level": "public | internal | restricted",
      "version": "string",
      "effective_date": "YYYY-MM-DD",
      "relevance_score": 0.0
    }
  ],
  "retrieval_confidence": "high | medium | low",
  "retry_attempted": false
}

## Agent 3 → Agent 4
{
  "draft_answer": "string",
  "cited_sources": ["string"],
  "confidence": "high | medium | low"
}

## Agent 4 → Final Output
{
  "final_answer": "string or null",
  "status": "approved | knowledge_gap | access_denied | conflict_warning",
  "reason": "string or null",
  "sources_confirmed": ["string"]
}

## Env vars
LLM_API_KEY      - Gemini/Claude/OpenAI key
LLM_PROVIDER     - gemini | claude | openai
VECTOR_DB_PATH   - local path for Chroma/FAISS index