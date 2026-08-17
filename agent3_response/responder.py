# agent3_response/responder.py
"""
Agent 3 — Knowledge Analysis & Response

Synthesizes a grounded, cited answer from Agent 2's retrieved chunks.
Hard rule: if there is no sufficient retrieved evidence, this agent must
refuse rather than fall back on general LLM knowledge.
"""

import json
import os

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

from shared.schemas import Agent2Output, Agent3Output, Citation, RetrievedChunk

# Chunks below this similarity score are treated as noise and discarded
# before they ever reach the LLM prompt. Shared across agents via .env —
# if this was meant to be Agent-4-only, split it into its own var instead.
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))

# Below this many usable chunks, don't even attempt synthesis — same
# effect as empty results from Agent 2.
MIN_USABLE_CHUNKS = 1

LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.6-flash")

REFUSAL_TEXT = (
    "I don't have information on this in the knowledge base available to you. "
    "I can't answer from general knowledge — please rephrase your question or "
    "contact a human representative for further help."
)

_client = genai.Client(api_key=os.getenv("LLM_API_KEY"))

SYSTEM_PROMPT = """You are the Knowledge Analysis & Response agent in a bank's \
internal knowledge system. You must answer STRICTLY and ONLY using the \
numbered source chunks provided below. Do not use any outside knowledge, \
even if you believe it is correct.

Rules:
1. Every factual claim in your answer must be traceable to at least one chunk.
2. If the chunks do not contain enough information to answer the question, \
say so plainly instead of guessing or filling gaps.
3. Do not mention "chunks", "sources", or internal IDs in the answer text \
itself — write a natural answer for the end user; citations are tracked \
separately.
4. Respond with ONLY a JSON object, no prose outside it, no markdown fences, \
in this exact shape:
{
  "answer": "string, the final answer for the user",
  "grounded": true or false,
  "chunks_used": ["chunk_id", ...],
  "synthesis_notes": "string or null, e.g. how multiple chunks were combined"
}
"""


def _filter_chunks(
    results: list[RetrievedChunk],
) -> tuple[list[RetrievedChunk], list[str]]:
    """Split retrieved chunks into usable vs. discarded by similarity score."""
    usable = [c for c in results if c.similarity_score >= CONFIDENCE_THRESHOLD]
    discarded = [c.chunk_id for c in results if c.similarity_score < CONFIDENCE_THRESHOLD]
    return usable, discarded


def _build_user_prompt(query: str, chunks: list[RetrievedChunk]) -> str:
    lines = [f'User question: "{query}"', "", "Source chunks:"]
    for i, c in enumerate(chunks, start=1):
        lines.append(
            f"[{i}] chunk_id={c.chunk_id} doc_id={c.doc_id} "
            f'doc_title="{c.doc_title}" section="{c.source_section}" '
            f"version={c.doc_version} effective_date={c.effective_date}\n"
            f"{c.chunk_text}"
        )
    return "\n\n".join(lines)


def _call_llm(user_prompt: str) -> dict:
    response = _client.models.generate_content(
        model=LLM_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=1000,
        ),
    )
    return json.loads(response.text)


def _citations_from_chunk_ids(
    chunk_ids: list[str], chunks: list[RetrievedChunk]
) -> list[Citation]:
    by_id = {c.chunk_id: c for c in chunks}
    citations = []
    for cid in chunk_ids:
        c = by_id.get(cid)
        if c is None:
            continue  # never trust a chunk_id the LLM invented
        citations.append(
            Citation(
                doc_id=c.doc_id,
                doc_title=c.doc_title,
                section=c.source_section,
                chunk_id=c.chunk_id,
            )
        )
    return citations


def analyze_and_respond(agent2_output: Agent2Output) -> Agent3Output:
    """Main entry point for Agent 3."""

    usable_chunks, discarded_ids = _filter_chunks(agent2_output.results)

    if len(usable_chunks) < MIN_USABLE_CHUNKS:
        return Agent3Output(
            session_id=agent2_output.session_id,
            answer_text=REFUSAL_TEXT,
            grounded=False,
            citations=[],
            chunks_used=[],
            chunks_discarded=[c.chunk_id for c in agent2_output.results],
            synthesis_notes="No chunks met the confidence threshold; refused rather than guessing.",
        )

    user_prompt = _build_user_prompt(agent2_output.query_used, usable_chunks)

    try:
        llm_result = _call_llm(user_prompt)
    except (json.JSONDecodeError, Exception) as exc:
        return Agent3Output(
            session_id=agent2_output.session_id,
            answer_text=REFUSAL_TEXT,
            grounded=False,
            citations=[],
            chunks_used=[],
            chunks_discarded=discarded_ids,
            synthesis_notes=f"LLM call/parse failed, refused as fail-safe: {exc}",
        )

    grounded = bool(llm_result.get("grounded", False))
    chunks_used = llm_result.get("chunks_used", [])

    if not grounded or not chunks_used:
        return Agent3Output(
            session_id=agent2_output.session_id,
            answer_text=REFUSAL_TEXT,
            grounded=False,
            citations=[],
            chunks_used=[],
            chunks_discarded=discarded_ids + [c.chunk_id for c in usable_chunks],
            synthesis_notes=llm_result.get("synthesis_notes")
            or "Model reported insufficient grounding.",
        )

    citations = _citations_from_chunk_ids(chunks_used, usable_chunks)
    unused_ids = [c.chunk_id for c in usable_chunks if c.chunk_id not in chunks_used]

    answer_text = llm_result.get("answer")
    if not answer_text:
        # grounded=True but no usable answer text — malformed model output,
        # fail safe instead of crashing or returning an empty answer.
        return Agent3Output(
            session_id=agent2_output.session_id,
            answer_text=REFUSAL_TEXT,
            grounded=False,
            citations=[],
            chunks_used=[],
            chunks_discarded=discarded_ids + [c.chunk_id for c in usable_chunks],
            synthesis_notes="Malformed model output: grounded=True but no answer text; refused as fail-safe.",
        )

    return Agent3Output(
        session_id=agent2_output.session_id,
        answer_text=answer_text,
        grounded=True,
        citations=citations,
        chunks_used=chunks_used,
        chunks_discarded=discarded_ids + unused_ids,
        synthesis_notes=llm_result.get("synthesis_notes"),
    )


if __name__ == "__main__":
    # Quick manual smoke test with a real chunk — exercises the actual Gemini call.
    mock_agent2_output = Agent2Output(
        session_id="sess_TEST02",
        query_used="What documents do I need to open a savings account?",
        access_level="public",
        results=[
            RetrievedChunk(
                doc_id="doc_001",
                doc_title="Savings Account Guide",
                chunk_id="doc_001_c01",
                chunk_text=(
                    "To open a savings account, customers need a valid NIC "
                    "or passport, proof of address, and an initial deposit "
                    "of LKR 1,000."
                ),
                similarity_score=0.91,
                doc_access_level="public",
                doc_version="v1",
                effective_date="2025-01-01",
                source_section="Section 2.1",
            )
        ],
        retrieval_confidence="high",
    )
    print(analyze_and_respond(mock_agent2_output))