"""
agent4_verification/verifier.py

Agent 4 — Verification & Governance

Consumes the real Agent1Output / Agent2Output / Agent3Output produced by
Agents 1-3 (shared.schemas) and returns the shared Agent4Output. This
module owns no data shapes of its own — it only adds decision logic on
top of the shared contracts, so it never needs Agent 1-3 to change.

Reads config from .env:
    LLM_PROVIDER=gemini
    LLM_MODEL=gemini-2.0-flash
    CONFIDENCE_THRESHOLD=0.6
    GEMINI_API_KEY=...          <- required to call Gemini for real;
                                    falls back to an offline heuristic
                                    (see llm_factual_support_check) if unset.

Pipeline:
    1. evidence_sufficiency   — did Agent 3 have grounded, cited content?
    2. access_reconfirm       — does every cited doc respect the session's
                                 fixed access_level (Agent1Output.access_level,
                                 never re-derived from user text)?
    3. factual_support_check  — LLM call (Gemini) checking answer_text is
                                 backed by the cited chunks
    4. version_conflict_check — same doc_title cited at different versions?

Decision priority:
    access violation           -> denied  (hard stop, never escalate a leak)
    insufficient evidence      -> denied
    factual check fail         -> escalated
    version conflict           -> escalated
    low retrieval confidence   -> escalated
    confidence < threshold     -> escalated
    otherwise                  -> approved
"""

from __future__ import annotations

import json
import os
from typing import Optional

from dotenv import load_dotenv

from shared.enums import (
    ACCESS_LEVEL_RANK,
    AccessLevel,
    EvidenceSufficiency,
    FactualSupportCheck,
    RetrievalConfidence,
    VerificationDecision,
)
from shared.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Agent4Output,
    Citation,
    FinalCitation,
    RetrievedChunk,
)

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


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
) -> tuple[FactualSupportCheck, float]:
    """
    Asks Gemini whether answer_text is fully supported by chunk_texts.
    Returns (verdict, confidence).

    Falls back to a simple heuristic (empty check) if Gemini is unavailable
    (no API key set, package not installed, or the call fails) so Agent 4
    still runs end-to-end without a live LLM connection. Note: the fallback
    caps confidence at 0.5, which sits below the default CONFIDENCE_THRESHOLD
    (0.6) — so without a configured GEMINI_API_KEY, Agent 4 will escalate
    rather than approve, by design (fail safe, not silently approve
    unverified content).
    """
    client = _get_gemini_client()

    if client is None or not chunk_texts:
        if not chunk_texts:
            return FactualSupportCheck.FAIL, 0.0
        return FactualSupportCheck.PASS, 0.5

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
        verdict_str = parsed.get("verdict", "fail")
        confidence = float(parsed.get("confidence", 0.0))
        verdict = (
            FactualSupportCheck.PASS if verdict_str == "pass" else FactualSupportCheck.FAIL
        )
        return verdict, confidence
    except Exception:
        # LLM call failed or returned unparseable output — fail closed
        # rather than silently approving unverified content.
        return FactualSupportCheck.FAIL, 0.0


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_evidence_sufficiency(agent3: Agent3Output) -> EvidenceSufficiency:
    if agent3.grounded and agent3.citations and agent3.chunks_used:
        return EvidenceSufficiency.SUFFICIENT
    return EvidenceSufficiency.INSUFFICIENT


def check_access_reconfirm(
    session_access_level: AccessLevel,
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
) -> tuple[bool, list[str]]:
    """Re-checks every citation against the session's fixed access_level
    (from Agent 1, never re-derived from user text). A citation whose
    chunk_id can't be resolved in chunk_lookup fails closed — it's
    treated as a violation, not silently ignored."""
    session_rank = ACCESS_LEVEL_RANK.get(session_access_level, 0)
    violating_docs: list[str] = []

    for citation in agent3.citations:
        chunk = chunk_lookup.get(citation.chunk_id)
        if chunk is None:
            violating_docs.append(citation.doc_id)
            continue
        if ACCESS_LEVEL_RANK.get(chunk.doc_access_level, 99) > session_rank:
            violating_docs.append(citation.doc_id)

    return (len(violating_docs) == 0, violating_docs)


def check_factual_support(
    agent3: Agent3Output, chunk_lookup: dict[str, RetrievedChunk]
) -> tuple[FactualSupportCheck, float]:
    if not agent3.citations:
        return FactualSupportCheck.FAIL, 0.0

    cited_ids = {c.chunk_id for c in agent3.citations}
    used_ids = set(agent3.chunks_used)
    if not used_ids.issubset(cited_ids):
        return FactualSupportCheck.FAIL, 0.0  # used but uncited content -> fail fast

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
    evidence: EvidenceSufficiency,
    access_ok: bool,
    factual: FactualSupportCheck,
    factual_confidence: float,
    version_conflict: bool,
    retrieval_confidence_low: bool,
) -> tuple[VerificationDecision, Optional[str]]:
    if not access_ok:
        return (
            VerificationDecision.DENIED,
            "access_violation: cited document(s) exceed session access_level",
        )

    if evidence == EvidenceSufficiency.INSUFFICIENT:
        return (
            VerificationDecision.DENIED,
            "insufficient_evidence: no grounded, cited content available",
        )

    if factual == FactualSupportCheck.FAIL:
        return VerificationDecision.ESCALATED, None

    if version_conflict:
        return VerificationDecision.ESCALATED, None

    if retrieval_confidence_low:
        return VerificationDecision.ESCALATED, None

    if factual_confidence < CONFIDENCE_THRESHOLD:
        return VerificationDecision.ESCALATED, None

    return VerificationDecision.APPROVED, None


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def run_agent4(
    agent1_output: Agent1Output,
    agent2_output: Agent2Output,
    agent3_output: Agent3Output,
) -> Agent4Output:
    """Runs Agent 4 against the real outputs of Agents 1-3.

    agent1_output.access_level is used as the authoritative session access
    level for the RBAC re-check (it's fixed system state set by Agent 1's
    ROLE_ACCESS_MAP, never derived from raw user text) — not
    agent2_output.access_level, which is just what was passed down for
    filtering and could theoretically drift from the session's true role.
    """
    chunk_lookup = {c.chunk_id: c for c in agent2_output.results}

    evidence = check_evidence_sufficiency(agent3_output)
    access_ok, violating_docs = check_access_reconfirm(
        agent1_output.access_level, agent3_output, chunk_lookup
    )
    factual, factual_confidence = check_factual_support(agent3_output, chunk_lookup)
    conflict_detected, conflict_details = check_version_conflict(
        agent3_output, chunk_lookup
    )
    retrieval_confidence_low = (
        agent2_output.retrieval_confidence == RetrievalConfidence.LOW
    )

    decision, denial_reason = decide(
        evidence, access_ok, factual, factual_confidence,
        conflict_detected, retrieval_confidence_low,
    )

    if decision == VerificationDecision.DENIED and not access_ok:
        denial_reason = f"{denial_reason} (doc_ids: {', '.join(violating_docs)})"

    approved = decision == VerificationDecision.APPROVED

    return Agent4Output(
        session_id=agent3_output.session_id,
        decision=decision,
        denial_reason=denial_reason if decision == VerificationDecision.DENIED else None,
        evidence_sufficiency=evidence,
        factual_support_check=factual,
        version_conflict_detected=conflict_detected,
        conflict_details=conflict_details,
        access_reconfirmed=access_ok,
        final_answer=agent3_output.answer_text if approved else None,
        final_citations=(
            [
                FinalCitation(doc_id=c.doc_id, doc_title=c.doc_title, section=c.section)
                for c in agent3_output.citations
            ]
            if approved
            else []
        ),
        confidence=round(factual_confidence, 2),
    )


# --------------------------------------------------------------------------
# Manual smoke test — run with: python -m agent4_verification.verifier
# --------------------------------------------------------------------------

if __name__ == "__main__":
    from shared.enums import Intent, UserRole

    demo_agent1 = Agent1Output(
        session_id="sess_demo",
        user_role=UserRole.CUSTOMER,
        access_level=AccessLevel.PUBLIC,
        intent=Intent.ACCOUNT_INFO,
        topic="savings_account",
        normalized_query="What is the minimum balance for a savings account?",
        confidence=0.9,
    )

    demo_chunk = RetrievedChunk(
        doc_id="doc_001",
        doc_title="Savings Account Guide",
        chunk_id="doc_001_c03",
        chunk_text="The minimum balance for a standard savings account is LKR 1,000.",
        similarity_score=0.91,
        doc_access_level=AccessLevel.PUBLIC,
        doc_version="v1",
        effective_date="2024-06-01",
        source_section="Section 2.1",
    )
    demo_agent2 = Agent2Output(
        session_id="sess_demo",
        query_used="minimum balance savings account",
        access_level=AccessLevel.PUBLIC,
        results=[demo_chunk],
        retrieval_confidence=RetrievalConfidence.HIGH,
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

    result = run_agent4(demo_agent1, demo_agent2, demo_agent3)
    print(result.model_dump_json(indent=2))