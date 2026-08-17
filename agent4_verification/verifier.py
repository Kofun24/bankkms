"""
agent4_verification/verifier.py

Agent 4 — Verification & Governance

Reads config from .env:
    LLM_PROVIDER=gemini
    LLM_MODEL=gemini-2.0-flash
    CONFIDENCE_THRESHOLD=0.6
    VECTOR_DB_PATH=./knowledge_base/vector_index
    GEMINI_API_KEY=...            <- add this too, required to call Gemini

Pipeline:
    1. evidence_sufficiency   — did Agent 3 have grounded, cited content?
    2. access_reconfirm       — does every cited doc respect this session's access_level?
    3. factual_support_check  — LLM call (Gemini) checking answer_text is backed by chunks
    4. version_conflict_check — same doc_title cited at different versions?

Decision priority:
    access violation           -> denied  (hard stop, never escalate a leak)
    insufficient evidence      -> denied
    factual check fail         -> escalated
    version conflict           -> escalated
    confidence < threshold     -> escalated
    otherwise                  -> approved
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "./knowledge_base/vector_index")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# Access level ordering used for the reconfirmation check.
ACCESS_RANK = {"public": 0, "internal": 1, "restricted": 2}


# --------------------------------------------------------------------------
# Data shapes (dataclasses, no pydantic dependency needed for this module)
# --------------------------------------------------------------------------

@dataclass
class RetrievedChunk:
    doc_id: str
    doc_title: str
    chunk_id: str
    chunk_text: str
    similarity_score: float
    doc_access_level: str          # "public" | "internal" | "restricted"
    doc_version: str
    effective_date: str
    source_section: str


@dataclass
class Citation:
    doc_id: str
    doc_title: str
    section: str
    chunk_id: str


@dataclass
class Agent2Output:
    session_id: str
    access_level: str
    results: list[RetrievedChunk] = field(default_factory=list)
    retrieval_confidence: str = "medium"   # "high" | "medium" | "low"


@dataclass
class Agent3Output:
    session_id: str
    answer_text: str
    grounded: bool
    citations: list[Citation] = field(default_factory=list)
    chunks_used: list[str] = field(default_factory=list)


@dataclass
class Agent4Input:
    session_id: str
    user_role: str
    access_level: str              # "public" | "internal" | "restricted"
    agent2_output: Agent2Output
    agent3_output: Agent3Output


@dataclass
class Agent4Output:
    session_id: str
    decision: str                  # "approved" | "denied" | "escalated"
    denial_reason: Optional[str]
    evidence_sufficiency: str      # "sufficient" | "insufficient"
    factual_support_check: str     # "pass" | "fail"
    version_conflict_detected: bool
    conflict_details: Optional[str]
    access_reconfirmed: bool
    final_answer: Optional[str]
    final_citations: list[dict]
    confidence: float
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "decision": self.decision,
            "denial_reason": self.denial_reason,
            "evidence_sufficiency": self.evidence_sufficiency,
            "factual_support_check": self.factual_support_check,
            "version_conflict_detected": self.version_conflict_detected,
            "conflict_details": self.conflict_details,
            "access_reconfirmed": self.access_reconfirmed,
            "final_answer": self.final_answer,
            "final_citations": self.final_citations,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }


# --------------------------------------------------------------------------
# Gemini call for factual support checking
# --------------------------------------------------------------------------
#
# Uses the current `google-genai` SDK (the old `google-generativeai`
# package is deprecated/end-of-life as of 2026 and should not be used).
#   pip install google-genai

_gemini_client = None


def _get_gemini_client():
    """Lazily configure and cache the Gemini client. Returns None if the
    SDK or API key isn't available, so callers can fall back gracefully."""
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    if LLM_PROVIDER != "gemini":
        return None
    if not GEMINI_API_KEY:
        return None

    try:
        from google import genai
    except ImportError:
        return None

    _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def llm_factual_support_check(
    answer_text: str, chunk_texts: list[str]
) -> tuple[str, float]:
    """
    Asks Gemini whether answer_text is fully supported by chunk_texts.
    Returns (verdict, confidence) where verdict is "pass" | "fail".

    Falls back to a simple heuristic (empty check) if Gemini is unavailable
    (no API key set, package not installed, or the call fails) so Agent 4
    still runs end-to-end without a live LLM connection.
    """
    client = _get_gemini_client()

    if client is None or not chunk_texts:
        # Fallback heuristic: can't verify without an LLM or without any
        # chunks to check against -> fail closed, don't approve blindly.
        return ("fail", 0.0) if not chunk_texts else ("pass", 0.5)

    context = "\n\n".join(f"[Chunk {i+1}] {t}" for i, t in enumerate(chunk_texts))
    prompt = f"""You are a strict fact-checking module for a banking knowledge system.

Below is an ANSWER and a set of source CHUNKS it is supposed to be based on.
Decide if every factual claim in the ANSWER is directly supported by the CHUNKS.
Do not use outside knowledge. Be strict: any unsupported claim means "fail".

CHUNKS:
{context}

ANSWER:
{answer_text}

Respond ONLY with JSON, no markdown fences, no preamble:
{{"verdict": "pass" or "fail", "confidence": <float 0.0-1.0>, "reason": "<short reason>"}}
"""

    try:
        response = client.models.generate_content(model=LLM_MODEL, contents=prompt)
        raw = response.text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        verdict = parsed.get("verdict", "fail")
        confidence = float(parsed.get("confidence", 0.0))
        if verdict not in ("pass", "fail"):
            verdict = "fail"
        return verdict, confidence
    except Exception:
        # LLM call failed or returned unparseable output — fail closed
        # rather than silently approving unverified content.
        return "fail", 0.0


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_evidence_sufficiency(agent3: Agent3Output) -> str:
    if agent3.grounded and agent3.citations and agent3.chunks_used:
        return "sufficient"
    return "insufficient"


def check_access_reconfirm(
    session_access_level: str,
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
) -> tuple[bool, list[str]]:
    session_rank = ACCESS_RANK.get(session_access_level, 0)
    violating_docs: list[str] = []

    for citation in agent3.citations:
        chunk = chunk_lookup.get(citation.chunk_id)
        if chunk is None:
            violating_docs.append(citation.doc_id)
            continue
        if ACCESS_RANK.get(chunk.doc_access_level, 99) > session_rank:
            violating_docs.append(citation.doc_id)

    return (len(violating_docs) == 0, violating_docs)


def check_factual_support(
    agent3: Agent3Output, chunk_lookup: dict[str, RetrievedChunk]
) -> tuple[str, float]:
    if not agent3.citations:
        return "fail", 0.0

    cited_ids = {c.chunk_id for c in agent3.citations}
    used_ids = set(agent3.chunks_used)
    if not used_ids.issubset(cited_ids):
        return "fail", 0.0  # used but uncited content -> fail fast, skip LLM call

    chunk_texts = [
        chunk_lookup[cid].chunk_text for cid in cited_ids if cid in chunk_lookup
    ]
    return llm_factual_support_check(agent3.answer_text, chunk_texts)


def check_version_conflict(
    agent3: Agent3Output, chunk_lookup: dict[str, RetrievedChunk]
) -> tuple[bool, Optional[str]]:
    by_title: dict[str, set[tuple[str, str]]] = {}

    for citation in agent3.citations:
        chunk = chunk_lookup.get(citation.chunk_id)
        if chunk is None:
            continue
        by_title.setdefault(chunk.doc_title, set()).add(
            (chunk.doc_version, chunk.effective_date)
        )

    conflicts = {t: v for t, v in by_title.items() if len(v) > 1}
    if not conflicts:
        return False, None

    details = "; ".join(
        f"{title}: versions {sorted(v[0] for v in versions)}"
        for title, versions in conflicts.items()
    )
    return True, details


def decide(
    evidence: str,
    access_ok: bool,
    factual: str,
    factual_confidence: float,
    version_conflict: bool,
    retrieval_confidence_low: bool,
) -> tuple[str, Optional[str]]:
    if not access_ok:
        return "denied", "access_violation: cited document(s) exceed session access_level"

    if evidence == "insufficient":
        return "denied", "insufficient_evidence: no grounded, cited content available"

    if factual == "fail":
        return "escalated", None

    if version_conflict:
        return "escalated", None

    if retrieval_confidence_low:
        return "escalated", None

    if factual_confidence < CONFIDENCE_THRESHOLD:
        return "escalated", None

    return "approved", None


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def run_agent4(payload: Agent4Input) -> Agent4Output:
    chunk_lookup = {c.chunk_id: c for c in payload.agent2_output.results}

    evidence = check_evidence_sufficiency(payload.agent3_output)
    access_ok, violating_docs = check_access_reconfirm(
        payload.access_level, payload.agent3_output, chunk_lookup
    )
    factual, factual_confidence = check_factual_support(
        payload.agent3_output, chunk_lookup
    )
    conflict_detected, conflict_details = check_version_conflict(
        payload.agent3_output, chunk_lookup
    )
    retrieval_confidence_low = payload.agent2_output.retrieval_confidence == "low"

    decision, denial_reason = decide(
        evidence, access_ok, factual, factual_confidence,
        conflict_detected, retrieval_confidence_low,
    )

    if decision == "denied" and not access_ok:
        denial_reason += f" (doc_ids: {', '.join(violating_docs)})"

    approved = decision == "approved"

    return Agent4Output(
        session_id=payload.session_id,
        decision=decision,
        denial_reason=denial_reason if decision == "denied" else None,
        evidence_sufficiency=evidence,
        factual_support_check=factual,
        version_conflict_detected=conflict_detected,
        conflict_details=conflict_details,
        access_reconfirmed=access_ok,
        final_answer=payload.agent3_output.answer_text if approved else None,
        final_citations=(
            [
                {"doc_id": c.doc_id, "doc_title": c.doc_title, "section": c.section}
                for c in payload.agent3_output.citations
            ]
            if approved
            else []
        ),
        confidence=round(factual_confidence, 2),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# --------------------------------------------------------------------------
# Manual smoke test — run with: python -m agent4_verification.verifier
# --------------------------------------------------------------------------

if __name__ == "__main__":
    demo_agent2 = Agent2Output(
        session_id="sess_demo",
        access_level="public",
        results=[
            RetrievedChunk(
                doc_id="doc_001",
                doc_title="Savings Account Guide",
                chunk_id="doc_001_c03",
                chunk_text="The minimum balance for a standard savings account is LKR 1,000.",
                similarity_score=0.91,
                doc_access_level="public",
                doc_version="v1",
                effective_date="2024-06-01",
                source_section="Section 2.1",
            ),
        ],
        retrieval_confidence="high",
    )
    demo_agent3 = Agent3Output(
        session_id="sess_demo",
        answer_text="The minimum balance for a standard savings account is LKR 1,000.",
        grounded=True,
        citations=[
            Citation(doc_id="doc_001", doc_title="Savings Account Guide",
                      section="Section 2.1", chunk_id="doc_001_c03")
        ],
        chunks_used=["doc_001_c03"],
    )
    demo_payload = Agent4Input(
        session_id="sess_demo",
        user_role="customer",
        access_level="public",
        agent2_output=demo_agent2,
        agent3_output=demo_agent3,
    )

    result = run_agent4(demo_payload)
    print(json.dumps(result.to_dict(), indent=2))