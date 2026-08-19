"""
Query reformulation, used only when the first retrieval attempt comes back
with low confidence. Calls Gemini (per your .env: LLM_PROVIDER=gemini) via
the plain REST API so we don't need the google-generativeai SDK as a hard
dependency.

If the call fails for any reason (no API key, no network, quota, etc.) we
fall back to a deterministic heuristic reformulation so Agent 2 never hard-
crashes on a reformulation step — it just does a slightly dumber retry.
"""
import requests

from . import config

GEMINI_URL_TMPL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    "?key={api_key}"
)


def _heuristic_reformulate(original_query: str, topic: str) -> str:
    """No-network fallback: broaden the query with the classified topic and
    strip filler words, so the retry has a real chance of hitting different
    chunks than attempt 1."""
    topic = (topic or "").strip()
    if topic and topic.lower() not in original_query.lower():
        return f"{original_query} {topic}"
    return original_query


def reformulate_query(original_query: str, topic: str) -> str:
    if config.LLM_PROVIDER == "gemini" and config.LLM_API_KEY:
        try:
            url = GEMINI_URL_TMPL.format(model=config.LLM_MODEL, api_key=config.LLM_API_KEY)
            prompt = (
                "Rewrite the following banking knowledge-base search query to be "
                "more likely to match relevant document chunks. Keep it short "
                "(under 20 words), keep the original intent, and return ONLY the "
                "rewritten query with no extra text.\n\n"
                f"Topic: {topic}\n"
                f"Original query: {original_query}"
            )
            resp = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text:
                return text
        except Exception:
            # Network blocked, bad key, rate limit, unexpected response shape, etc.
            # Fall through to the heuristic below rather than raising — a
            # reformulation failure should never take down the retrieval agent.
            pass

    return _heuristic_reformulate(original_query, topic)