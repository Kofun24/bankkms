"""
agent4_verification/verifier.py

Agent 4 — Verification & Governance

Decision priority:
    1. Access violation         -> DENIED
    2. Insufficient evidence    -> DENIED
    3. Factual check failure    -> ESCALATED
    4. Version conflict         -> ESCALATED
    5. Low retrieval confidence -> ESCALATED
    6. Low factual confidence   -> ESCALATED
    7. Otherwise                -> APPROVED

Security principle:
    Agent 4 must never leak an answer when the cited evidence violates
    the session's access level.

Primary integration interface:
    run_agent4(agent1_output, agent2_output, agent3_output, version_lookup=None)

Backward-compatible interface (still supported):
    run_agent4(Agent4Input(...))

This module has ZERO database dependency by design — fast, offline-
testable, importable in CI without a live DB connection. Real
version-conflict detection against the `documents` table lives in
db_integration.py; pass its `version_lookup_from_db` in production. See
run_live_query.py for a full example wiring Agents 1-4 together with
real data end to end.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Union

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
    RetrievedChunk,
)

# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.0-flash")

try:
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
except ValueError:
    CONFIDENCE_THRESHOLD = 0.6

VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "./knowledge_base/vector_index")

# NOTE: attribute name stays GEMINI_API_KEY (tests monkeypatch this exact
# name — see conftest.py's `no_gemini` fixture), but it's now SOURCED from
# LLM_API_KEY first, matching the .env variable name Agents 1-3 actually
# use. GEMINI_API_KEY/GOOGLE_API_KEY are kept only as back-compat aliases
# for anyone who still has the old name set locally.
GEMINI_API_KEY = (
    os.getenv("LLM_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
)


def _enum_value(value: Any) -> str:
    """Safely get the string value of an Enum, or pass through a plain
    string unchanged. AccessLevel.PUBLIC -> "public"; "public" -> "public"."""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


# ---------------------------------------------------------------------------
# Version record
# ---------------------------------------------------------------------------

@dataclass
class VersionRecord:
    """One row from the `documents` table for a given title. Distinct
    from RetrievedChunk: represents a document's existence/metadata
    regardless of whether Agent 2 was allowed to retrieve it (e.g. a
    superseded, is_current=False version Agent 2 filters out of normal
    retrieval)."""

    doc_id: str
    version: str
    effective_date: str
    is_current: bool


VersionLookupFn = Callable[[str], list[VersionRecord]]


# ---------------------------------------------------------------------------
# Backward-compatible Agent4Input
# ---------------------------------------------------------------------------

@dataclass
class Agent4Input:
    """Backward-compatible wrapper. New code should call
    run_agent4(agent1_output, agent2_output, agent3_output) directly;
    this remains supported for anything still constructing the old shape."""

    session_id: str
    user_role: str
    access_level: str
    agent2_output: Agent2Output
    agent3_output: Agent3Output


# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------

_gemini_client = None


def _get_gemini_client():
    """Lazily configure and cache the Gemini client. Returns None when
    Gemini isn't selected, the key is missing, or the SDK isn't installed —
    callers fall back gracefully rather than crashing."""
    global _gemini_client

    if _gemini_client is not None:
        return _gemini_client
    if LLM_PROVIDER.lower() != "gemini":
        return None
    if not GEMINI_API_KEY:
        return None

    try:
        from google import genai
    except ImportError:
        return None

    try:
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        return None

    return _gemini_client


# ---------------------------------------------------------------------------
# Gemini factual support check
# ---------------------------------------------------------------------------

def llm_factual_support_check(
    answer_text: str,
    chunk_texts: list[str],
) -> tuple[str, float]:
    """
    Ask Gemini whether the answer is fully supported by the retrieved
    evidence. Returns ("pass"|"fail", confidence).

    Offline fallback (no Gemini configured): returns ("pass", 0.5) when
    evidence exists. Since the default approval threshold is 0.6, this
    fallback alone can NEVER independently approve an answer — it forces
    an escalation for human review instead of silently approving
    unverified content.
    """
    if not chunk_texts:
        return "fail", 0.0

    client = _get_gemini_client()
    if client is None:
        return "pass", 0.5

    context = "\n\n".join(f"[Chunk {i + 1}] {text}" for i, text in enumerate(chunk_texts))
    prompt = f"""You are a strict factual verification module for a banking
Knowledge Management System.

Determine whether EVERY factual claim in the ANSWER is directly supported
by the provided CHUNKS.

Rules:
1. Use ONLY the information in the CHUNKS.
2. Do NOT use outside knowledge.
3. If any factual claim is unsupported, return "fail".
4. Be strict. Do not assume missing information or add unsupported facts.
5. Return ONLY valid JSON.

CHUNKS:
{context}

ANSWER:
{answer_text}

Return exactly this JSON structure:
{{"verdict": "pass" or "fail", "confidence": 0.0, "reason": "short explanation"}}
"""

    try:
        response = client.models.generate_content(model=LLM_MODEL, contents=prompt)
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)

        verdict = str(parsed.get("verdict", "fail")).lower()
        confidence = float(parsed.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        if verdict not in {"pass", "fail"}:
            verdict = "fail"

        return verdict, confidence
    except Exception:
        # Fail closed — never approve based on an uncertain/broken result.
        return "fail", 0.0


# ---------------------------------------------------------------------------
# Evidence sufficiency
# ---------------------------------------------------------------------------

def check_evidence_sufficiency(agent3: Agent3Output) -> EvidenceSufficiency:
    """Sufficient only when grounded=True AND at least one citation AND
    at least one chunk_used. A single missing piece flips it to insufficient."""
    if agent3.grounded and bool(agent3.citations) and bool(agent3.chunks_used):
        return EvidenceSufficiency.SUFFICIENT
    return EvidenceSufficiency.INSUFFICIENT


# ---------------------------------------------------------------------------
# Access reconfirmation
# ---------------------------------------------------------------------------

def check_access_reconfirm(
    session_access_level: Union[AccessLevel, str],
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
) -> tuple[bool, list[str]]:
    """
    Second (and last) access gate. Uses shared.enums.ACCESS_LEVEL_RANK —
    the same ordering Agent 2's own allowed_access_levels() filtering is
    built on — so both sides of the system agree on exactly what
    "allowed" means. This is now mostly a data-integrity double-check
    (Agent 2's SQL WHERE clause already blocks disallowed docs before
    they're fetched), but it still catches a citation to a chunk Agent 3
    invented/hallucinated that never appeared in Agent 2's real results.

    Fails closed on:
      - a session access level with no defined rank at all (AccessLevel.NONE
        / Admin should never reach this function — if it does, an upstream
        guard failed, and failing closed here is correct, not something to
        paper over)
      - a citation pointing to a chunk_id missing from chunk_lookup
      - a cited chunk whose doc_access_level has no defined rank
      - a cited chunk whose rank exceeds the session's rank
    """
    try:
        session_level = (
            session_access_level
            if isinstance(session_access_level, AccessLevel)
            else AccessLevel(_enum_value(session_access_level))
        )
    except ValueError:
        session_level = None

    session_rank = ACCESS_LEVEL_RANK.get(session_level) if session_level else None

    if session_rank is None:
        violating = [c.doc_id for c in agent3.citations]
        return False, violating or ["no_valid_session_access_level"]

    violating_docs: list[str] = []

    for citation in agent3.citations:
        chunk = chunk_lookup.get(citation.chunk_id)
        if chunk is None:
            violating_docs.append(citation.doc_id)
            continue

        try:
            doc_level = (
                chunk.doc_access_level
                if isinstance(chunk.doc_access_level, AccessLevel)
                else AccessLevel(_enum_value(chunk.doc_access_level))
            )
        except ValueError:
            violating_docs.append(citation.doc_id)
            continue

        doc_rank = ACCESS_LEVEL_RANK.get(doc_level)
        if doc_rank is None or doc_rank > session_rank:
            violating_docs.append(citation.doc_id)

    return (len(violating_docs) == 0, violating_docs)


# ---------------------------------------------------------------------------
# Factual support
# ---------------------------------------------------------------------------

def check_factual_support(
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
) -> tuple[FactualSupportCheck, float]:
    """
    1. Must have citations.
    2. Every chunk_used must be cited (no used-but-uncited content).
    3. Every cited chunk must actually exist in Agent 2's results.
    4. Gemini verifies the answer text against the cited chunk text.
    """
    if not agent3.citations:
        return FactualSupportCheck.FAIL, 0.0

    cited_ids = {c.chunk_id for c in agent3.citations}
    used_ids = set(agent3.chunks_used)

    if not used_ids.issubset(cited_ids):
        return FactualSupportCheck.FAIL, 0.0

    missing_ids = [cid for cid in cited_ids if cid not in chunk_lookup]
    if missing_ids:
        return FactualSupportCheck.FAIL, 0.0

    chunk_texts = [chunk_lookup[cid].chunk_text for cid in cited_ids]
    verdict, confidence = llm_factual_support_check(agent3.answer_text, chunk_texts)

    if verdict == "pass":
        return FactualSupportCheck.PASS, confidence
    return FactualSupportCheck.FAIL, confidence


# ---------------------------------------------------------------------------
# Version conflict detection
# ---------------------------------------------------------------------------

def check_version_conflict(
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
    version_lookup: Optional[VersionLookupFn] = None,
) -> tuple[bool, Optional[str]]:
    """
    Detects whether any cited document has multiple distinct versions on
    record.

    Production: pass `version_lookup=db_integration.version_lookup_from_db`
    to check the real `documents` table, including versions Agent 2 was
    never allowed to return (Agent 2 filters is_current=False at the SQL
    level, so a single Agent2Output can never itself contain two versions
    of the same doc — this is now the ONLY way to detect a real conflict).

    Offline tests: omit version_lookup — falls back to comparing whatever
    versions are already present in the hand-built Agent2Output passed in.
    """
    if version_lookup is not None:
        return _check_version_conflict_via_db(agent3, chunk_lookup, version_lookup)
    return _check_version_conflict_legacy(agent3, chunk_lookup)


def _check_version_conflict_via_db(
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
    version_lookup: VersionLookupFn,
) -> tuple[bool, Optional[str]]:
    checked_titles: set[str] = set()
    conflicts: dict[str, set[tuple[str, str]]] = {}

    for citation in agent3.citations:
        chunk = chunk_lookup.get(citation.chunk_id)
        if chunk is None:
            continue

        title = chunk.doc_title
        if title in checked_titles:
            continue
        checked_titles.add(title)

        try:
            all_versions = version_lookup(title)
        except Exception:
            # DB lookup itself failed — treat as governance uncertainty,
            # not a silent pass-through.
            conflicts[title] = {("lookup_error", "unknown")}
            continue

        distinct = {(str(v.version), str(v.effective_date)) for v in all_versions}
        if len(distinct) > 1:
            conflicts[title] = distinct

    if not conflicts:
        return False, None

    details = "; ".join(
        f"{title}: versions {sorted(v[0] for v in versions)}"
        for title, versions in conflicts.items()
    )
    return True, details


def _check_version_conflict_legacy(
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
) -> tuple[bool, Optional[str]]:
    """Offline fallback only. Only fires when a test hand-builds an
    Agent2Output containing multiple versions already — never fires
    against real Agent 2 output in production (is_current=False rows are
    filtered upstream at the SQL level)."""
    by_title: dict[str, set[tuple[str, str]]] = {}

    for citation in agent3.citations:
        chunk = chunk_lookup.get(citation.chunk_id)
        if chunk is None:
            continue
        by_title.setdefault(chunk.doc_title, set()).add(
            (str(chunk.doc_version), str(chunk.effective_date))
        )

    conflicts = {t: v for t, v in by_title.items() if len(v) > 1}
    if not conflicts:
        return False, None

    details = "; ".join(
        f"{title}: versions {sorted(v[0] for v in versions)}"
        for title, versions in conflicts.items()
    )
    return True, details


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------

def decide(
    evidence: Union[EvidenceSufficiency, str],
    access_ok: bool,
    factual: Union[FactualSupportCheck, str],
    factual_confidence: float,
    version_conflict: bool,
    retrieval_confidence_low: bool,
) -> tuple[VerificationDecision, Optional[str]]:
    """A security violation must NEVER be softened into an escalation —
    that's why access_ok is checked first and returns DENIED unconditionally.

    Every branch now returns a specific machine-readable reason string
    (not just the DENIED ones) — this is what lets callers like
    pipeline.py show a different, accurate message to the user for each
    distinct failure, instead of one generic sentence per decision type.
    The reason field on Agent4Output is still called `denial_reason` for
    backward compatibility, but it's populated for any non-approved
    decision, denied or escalated."""
    evidence_value = _enum_value(evidence)
    factual_value = _enum_value(factual)

    if not access_ok:
        return (
            VerificationDecision.DENIED,
            "access_violation: cited document(s) exceed session access_level",
        )

    if evidence_value == EvidenceSufficiency.INSUFFICIENT.value:
        return (
            VerificationDecision.DENIED,
            "insufficient_evidence: no grounded, cited content available",
        )

    if factual_value == FactualSupportCheck.FAIL.value:
        return (
            VerificationDecision.ESCALATED,
            "factual_check_failed: the answer could not be fully verified against its cited sources",
        )

    if version_conflict:
        return (
            VerificationDecision.ESCALATED,
            "version_conflict: multiple versions of a cited document exist and require review",
        )

    if retrieval_confidence_low:
        return (
            VerificationDecision.ESCALATED,
            "low_retrieval_confidence: the retrieved evidence was a weak match for this question",
        )

    if factual_confidence < CONFIDENCE_THRESHOLD:
        return (
            VerificationDecision.ESCALATED,
            "low_confidence: verification confidence did not meet the required threshold",
        )

    return VerificationDecision.APPROVED, None


# ---------------------------------------------------------------------------
# Main Agent 4 entry point
# ---------------------------------------------------------------------------

def run_agent4(
    agent1_or_payload: Union[Agent1Output, Agent4Input],
    agent2: Optional[Agent2Output] = None,
    agent3: Optional[Agent3Output] = None,
    version_lookup: Optional[VersionLookupFn] = None,
) -> Agent4Output:
    """
    Primary usage:
        run_agent4(agent1_output, agent2_output, agent3_output)
        run_agent4(agent1_output, agent2_output, agent3_output,
                    version_lookup=db_integration.version_lookup_from_db)

    Backward-compatible usage:
        run_agent4(Agent4Input(...))
    """
    if isinstance(agent1_or_payload, Agent4Input):
        payload = agent1_or_payload
        resolved_agent2 = payload.agent2_output
        resolved_agent3 = payload.agent3_output
        session_id = payload.session_id
        session_access_level = payload.access_level
    else:
        if agent2 is None:
            raise TypeError("run_agent4() requires Agent2Output when Agent1Output is provided.")
        if agent3 is None:
            raise TypeError("run_agent4() requires Agent3Output when Agent1Output is provided.")

        agent1 = agent1_or_payload
        resolved_agent2 = agent2
        resolved_agent3 = agent3
        session_id = agent1.session_id
        # Access level comes from Agent 1's fixed session state — never
        # derived from the user's raw query text.
        session_access_level = agent1.access_level

    session_mismatch = (
        resolved_agent2.session_id != session_id
        or resolved_agent3.session_id != session_id
    )

    chunk_lookup: dict[str, RetrievedChunk] = {
        chunk.chunk_id: chunk for chunk in resolved_agent2.results
    }

    evidence = check_evidence_sufficiency(resolved_agent3)

    access_ok, violating_docs = check_access_reconfirm(
        session_access_level, resolved_agent3, chunk_lookup
    )
    if session_mismatch:
        access_ok = False
        if "session_mismatch" not in violating_docs:
            violating_docs.append("session_mismatch")

    factual, factual_confidence = check_factual_support(resolved_agent3, chunk_lookup)

    conflict_detected, conflict_details = check_version_conflict(
        resolved_agent3, chunk_lookup, version_lookup
    )

    retrieval_confidence_value = _enum_value(resolved_agent2.retrieval_confidence)
    retrieval_confidence_low = retrieval_confidence_value == RetrievalConfidence.LOW.value

    decision, denial_reason = decide(
        evidence=evidence,
        access_ok=access_ok,
        factual=factual,
        factual_confidence=factual_confidence,
        version_conflict=conflict_detected,
        retrieval_confidence_low=retrieval_confidence_low,
    )

    if decision == VerificationDecision.DENIED and not access_ok:
        denial_reason = denial_reason or "access_violation"
        if violating_docs:
            denial_reason += f" (doc_ids: {', '.join(violating_docs)})"

    approved = decision == VerificationDecision.APPROVED

    if approved:
        final_answer = resolved_agent3.answer_text
        final_citations = [
            {"doc_id": c.doc_id, "doc_title": c.doc_title, "section": c.section}
            for c in resolved_agent3.citations
        ]
    else:
        final_answer = None
        final_citations = []

    return Agent4Output(
        session_id=session_id,
        decision=decision,
        denial_reason=denial_reason if decision != VerificationDecision.APPROVED else None,
        evidence_sufficiency=evidence,
        factual_support_check=factual,
        version_conflict_detected=conflict_detected,
        conflict_details=conflict_details,
        access_reconfirmed=access_ok,
        final_answer=final_answer,
        final_citations=final_citations,
        confidence=round(float(factual_confidence), 2),
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Manual smoke test — hand-built data, offline. For a REAL end-to-end run
# against the actual database and Gemini, use run_live_query.py instead.
# ---------------------------------------------------------------------------
#
#   python -m agent4_verification.verifier
#
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from shared.enums import Intent, UserRole

    print("=" * 70)
    print("Agent 4 — Verification & Governance — offline smoke test")
    print("(For a real end-to-end run: python run_live_query.py)")
    print("=" * 70)

    demo_agent1 = Agent1Output(
        session_id="sess_demo",
        user_role=UserRole.CUSTOMER,
        access_level=AccessLevel.PUBLIC,
        intent=Intent.ACCOUNT_INFO,
        topic="savings account",
        normalized_query="minimum savings account balance",
        confidence=0.95,
    )
    demo_agent2 = Agent2Output(
        session_id="sess_demo",
        query_used="minimum savings account balance",
        access_level=AccessLevel.PUBLIC,
        results=[
            RetrievedChunk(
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
        ],
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
    print()
    print(json.dumps(result.model_dump(mode="json"), indent=2))