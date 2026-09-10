"""
agent4_verification/verifier.py

Agent 4 — Verification & Governance

Decision priority:

    1. Access violation       -> DENIED
    2. Insufficient evidence  -> DENIED
    3. Factual check failure  -> ESCALATED
    4. Version conflict       -> ESCALATED
    5. Low retrieval confidence -> ESCALATED
    6. Low factual confidence -> ESCALATED
    7. Otherwise              -> APPROVED

Security principle:
    Agent 4 must never leak an answer when the cited evidence violates
    the session's access level.

Integration:
    run_agent4(agent1_output, agent2_output, agent3_output)

Backward compatibility:
    run_agent4(agent4_input)

The real shared Pydantic schemas from shared.schemas are used so that
Agent4Output supports model_dump_json().
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Union, Any

from dotenv import load_dotenv

from shared.enums import (
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
    CONFIDENCE_THRESHOLD = float(
        os.getenv("CONFIDENCE_THRESHOLD", "0.6")
    )
except ValueError:
    CONFIDENCE_THRESHOLD = 0.6

VECTOR_DB_PATH = os.getenv(
    "VECTOR_DB_PATH",
    "./knowledge_base/vector_index",
)

GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
)


# ---------------------------------------------------------------------------
# Access level ranking
# ---------------------------------------------------------------------------
#
# Higher number = higher access.
#
# public     -> 0
# internal   -> 1
# restricted -> 2
#
# NONE is intentionally not included because Admin/NONE sessions should
# never reach the knowledge retrieval pipeline.
# ---------------------------------------------------------------------------

ACCESS_RANK = {
    AccessLevel.PUBLIC.value: 0,
    AccessLevel.INTERNAL.value: 1,
    AccessLevel.RESTRICTED.value: 2,
}


def _enum_value(value: Any) -> str:
    """
    Safely convert an Enum or normal string to its string value.

    Example:
        AccessLevel.PUBLIC -> "public"
        "public"           -> "public"
    """
    if hasattr(value, "value"):
        return str(value.value)

    return str(value)


# ---------------------------------------------------------------------------
# Version record
# ---------------------------------------------------------------------------

@dataclass
class VersionRecord:
    """
    Represents one document version from the documents table.

    This is intentionally separate from RetrievedChunk because Agent 2
    normally returns only the current version, while Agent 4 may need to
    check all versions in the database.
    """

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
    """
    Backward-compatible wrapper for older Agent 4 code.

    New integration code should normally call:

        run_agent4(agent1_output, agent2_output, agent3_output)

    Older code may still create:

        Agent4Input(
            session_id=...,
            user_role=...,
            access_level=...,
            agent2_output=...,
            agent3_output=...,
        )
    """

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
    """
    Lazily configure and cache the Gemini client.

    Returns None when:
    - Gemini is not selected
    - API key is missing
    - google-genai is not installed
    """

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
        _gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )
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
    evidence.

    Returns:

        ("pass", confidence)
        ("fail", confidence)

    Important:
        Offline fallback returns pass with confidence 0.5 when evidence
        exists. Because the approval threshold is normally 0.6, this
        fallback can NEVER independently approve an answer.

    This behavior is required by the integration test:
        test_offline_fallback_alone_is_never_enough_to_approve
    """

    # No evidence -> factual verification must fail.
    if not chunk_texts:
        return "fail", 0.0

    client = _get_gemini_client()

    # Offline fallback.
    #
    # Evidence exists, but there is no LLM available to confidently verify
    # the answer. We return pass with 0.5 so the final decision logic can
    # escalate it because 0.5 < 0.6.
    if client is None:
        return "pass", 0.5

    context = "\n\n".join(
        f"[Chunk {i + 1}] {text}"
        for i, text in enumerate(chunk_texts)
    )

    prompt = f"""
You are a strict factual verification module for a banking
Knowledge Management System.

Your job is to determine whether EVERY factual claim in the
ANSWER is directly supported by the provided CHUNKS.

Rules:

1. Use ONLY the information in the CHUNKS.
2. Do NOT use outside knowledge.
3. If any factual claim is unsupported, return "fail".
4. Be strict.
5. Do not assume missing information.
6. Do not add facts that are not explicitly supported.
7. Return ONLY valid JSON.

CHUNKS:
{context}

ANSWER:
{answer_text}

Return exactly this JSON structure:

{{
    "verdict": "pass" or "fail",
    "confidence": 0.0,
    "reason": "short explanation"
}}
"""

    try:
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=prompt,
        )

        raw = response.text.strip()

        # Remove markdown code fences if Gemini adds them.
        raw = raw.replace("```json", "")
        raw = raw.replace("```", "")
        raw = raw.strip()

        parsed = json.loads(raw)

        verdict = str(
            parsed.get("verdict", "fail")
        ).lower()

        confidence = float(
            parsed.get("confidence", 0.0)
        )

        # Clamp confidence to a safe range.
        confidence = max(
            0.0,
            min(1.0, confidence)
        )

        if verdict not in {"pass", "fail"}:
            verdict = "fail"

        return verdict, confidence

    except Exception:
        # Fail closed.
        #
        # If Gemini fails or gives invalid JSON, never approve based on
        # an uncertain result.
        return "fail", 0.0


# ---------------------------------------------------------------------------
# Evidence sufficiency
# ---------------------------------------------------------------------------

def check_evidence_sufficiency(
    agent3: Agent3Output,
) -> EvidenceSufficiency:
    """
    Evidence is sufficient only when Agent 3 produced:

    - grounded=True
    - at least one citation
    - at least one chunk used
    """

    if (
        agent3.grounded
        and bool(agent3.citations)
        and bool(agent3.chunks_used)
    ):
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
    Reconfirm that every cited chunk is allowed for the session.

    Security behavior:

    - Missing cited chunk -> violation
    - Restricted document cited by public user -> violation
    - Internal document cited by public user -> violation
    - Internal user citing public/internal -> allowed
    - Restricted user citing public/internal/restricted -> allowed

    Unknown access levels fail closed.
    """

    session_level = _enum_value(session_access_level)

    # NONE/Admin is intentionally not given a retrieval rank.
    # If it reaches Agent 4, fail closed.
    if session_level not in ACCESS_RANK:
        violating_docs = [
            citation.doc_id
            for citation in agent3.citations
        ]

        # If there are no citations, still return false because this is
        # not a valid retrieval access level.
        return False, violating_docs

    session_rank = ACCESS_RANK[session_level]

    violating_docs: list[str] = []

    for citation in agent3.citations:

        chunk = chunk_lookup.get(
            citation.chunk_id
        )

        # Citation points to a chunk that Agent 2 did not provide.
        # Fail closed.
        if chunk is None:
            violating_docs.append(
                citation.doc_id
            )
            continue

        document_level = _enum_value(
            chunk.doc_access_level
        )

        document_rank = ACCESS_RANK.get(
            document_level
        )

        # Unknown document access level -> fail closed.
        if document_rank is None:
            violating_docs.append(
                citation.doc_id
            )
            continue

        # Document requires more access than the session has.
        if document_rank > session_rank:
            violating_docs.append(
                citation.doc_id
            )

    return (
        len(violating_docs) == 0,
        violating_docs,
    )


# ---------------------------------------------------------------------------
# Factual support
# ---------------------------------------------------------------------------

def check_factual_support(
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
) -> tuple[FactualSupportCheck, float]:
    """
    Verify that Agent 3's answer is supported by the cited chunks.

    Checks:

    1. There must be citations.
    2. Every chunk used must be cited.
    3. Every cited chunk should exist in Agent 2 output.
    4. Gemini verifies the actual answer against chunk text.
    """

    # No citations -> cannot verify factual support.
    if not agent3.citations:
        return (
            FactualSupportCheck.FAIL,
            0.0,
        )

    cited_ids = {
        citation.chunk_id
        for citation in agent3.citations
    }

    used_ids = set(
        agent3.chunks_used
    )

    # Agent 3 claims to have used a chunk that it did not cite.
    #
    # This is a governance problem because the user would not have a
    # corresponding citation for the information used.
    if not used_ids.issubset(cited_ids):
        return (
            FactualSupportCheck.FAIL,
            0.0,
        )

    # Every cited chunk must exist in Agent 2 results.
    missing_ids = [
        chunk_id
        for chunk_id in cited_ids
        if chunk_id not in chunk_lookup
    ]

    if missing_ids:
        return (
            FactualSupportCheck.FAIL,
            0.0,
        )

    chunk_texts = [
        chunk_lookup[chunk_id].chunk_text
        for chunk_id in cited_ids
    ]

    verdict, confidence = (
        llm_factual_support_check(
            agent3.answer_text,
            chunk_texts,
        )
    )

    if verdict == "pass":
        return (
            FactualSupportCheck.PASS,
            confidence,
        )

    return (
        FactualSupportCheck.FAIL,
        confidence,
    )


# ---------------------------------------------------------------------------
# Version conflict detection
# ---------------------------------------------------------------------------

def check_version_conflict(
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
    version_lookup: Optional[VersionLookupFn] = None,
) -> tuple[bool, Optional[str]]:
    """
    Detect whether cited documents have multiple versions.

    Production:
        Pass version_lookup so Agent 4 can query the documents table.

    Offline tests:
        When version_lookup is absent, compare versions that are already
        present in Agent 2 results.

    This keeps the existing test behavior while supporting real
    database-backed conflict detection.
    """

    if version_lookup is not None:
        return _check_version_conflict_via_db(
            agent3,
            chunk_lookup,
            version_lookup,
        )

    return _check_version_conflict_legacy(
        agent3,
        chunk_lookup,
    )


def _check_version_conflict_via_db(
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
    version_lookup: VersionLookupFn,
) -> tuple[bool, Optional[str]]:
    """
    Check every cited document title against the database.

    The database lookup should return all versions, including current and
    superseded versions.
    """

    checked_titles: set[str] = set()

    conflicts: dict[
        str,
        set[tuple[str, str]]
    ] = {}

    for citation in agent3.citations:

        chunk = chunk_lookup.get(
            citation.chunk_id
        )

        if chunk is None:
            continue

        title = chunk.doc_title

        if title in checked_titles:
            continue

        checked_titles.add(title)

        try:
            all_versions = version_lookup(
                title
            )
        except Exception:
            # If the database lookup itself fails, treat it as a conflict
            # / governance uncertainty rather than silently approving.
            conflicts[title] = {
                (
                    "lookup_error",
                    "unknown",
                )
            }
            continue

        distinct = {
            (
                str(version.version),
                str(version.effective_date),
            )
            for version in all_versions
        }

        if len(distinct) > 1:
            conflicts[title] = distinct

    if not conflicts:
        return False, None

    details_parts = []

    for title, versions in conflicts.items():

        versions_sorted = sorted(
            version[0]
            for version in versions
        )

        details_parts.append(
            f"{title}: versions {versions_sorted}"
        )

    return (
        True,
        "; ".join(details_parts),
    )


def _check_version_conflict_legacy(
    agent3: Agent3Output,
    chunk_lookup: dict[str, RetrievedChunk],
) -> tuple[bool, Optional[str]]:
    """
    Offline fallback.

    Detects multiple versions of the same document title when tests
    deliberately place multiple versions inside Agent 2 results.
    """

    by_title: dict[
        str,
        set[tuple[str, str]]
    ] = {}

    for citation in agent3.citations:

        chunk = chunk_lookup.get(
            citation.chunk_id
        )

        if chunk is None:
            continue

        title = chunk.doc_title

        by_title.setdefault(
            title,
            set(),
        ).add(
            (
                str(chunk.doc_version),
                str(chunk.effective_date),
            )
        )

    conflicts = {
        title: versions
        for title, versions in by_title.items()
        if len(versions) > 1
    }

    if not conflicts:
        return False, None

    details_parts = []

    for title, versions in conflicts.items():

        versions_sorted = sorted(
            version[0]
            for version in versions
        )

        details_parts.append(
            f"{title}: versions {versions_sorted}"
        )

    return (
        True,
        "; ".join(details_parts),
    )


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------

def decide(
    evidence: Union[
        EvidenceSufficiency,
        str,
    ],
    access_ok: bool,
    factual: Union[
        FactualSupportCheck,
        str,
    ],
    factual_confidence: float,
    version_conflict: bool,
    retrieval_confidence_low: bool,
) -> tuple[
    VerificationDecision,
    Optional[str],
]:
    """
    Apply Agent 4 decision priority.

    Priority is important because a security violation must NEVER be
    converted into an escalation.

    Priority:

        access violation
            ->
        denied

        insufficient evidence
            ->
        denied

        factual failure
            ->
        escalated

        version conflict
            ->
        escalated

        low retrieval confidence
            ->
        escalated

        low factual confidence
            ->
        escalated

        otherwise
            ->
        approved
    """

    evidence_value = _enum_value(
        evidence
    )

    factual_value = _enum_value(
        factual
    )

    # ---------------------------------------------------------------
    # 1. ACCESS VIOLATION
    # ---------------------------------------------------------------

    if not access_ok:
        return (
            VerificationDecision.DENIED,
            "access_violation: cited document(s) exceed session access_level",
        )

    # ---------------------------------------------------------------
    # 2. INSUFFICIENT EVIDENCE
    # ---------------------------------------------------------------

    if (
        evidence_value
        == EvidenceSufficiency.INSUFFICIENT.value
    ):
        return (
            VerificationDecision.DENIED,
            "insufficient_evidence: no grounded, cited content available",
        )

    # ---------------------------------------------------------------
    # 3. FACTUAL CHECK FAILED
    # ---------------------------------------------------------------

    if (
        factual_value
        == FactualSupportCheck.FAIL.value
    ):
        return (
            VerificationDecision.ESCALATED,
            None,
        )

    # ---------------------------------------------------------------
    # 4. VERSION CONFLICT
    # ---------------------------------------------------------------

    if version_conflict:
        return (
            VerificationDecision.ESCALATED,
            None,
        )

    # ---------------------------------------------------------------
    # 5. LOW RETRIEVAL CONFIDENCE
    # ---------------------------------------------------------------

    if retrieval_confidence_low:
        return (
            VerificationDecision.ESCALATED,
            None,
        )

    # ---------------------------------------------------------------
    # 6. LOW FACTUAL CONFIDENCE
    # ---------------------------------------------------------------

    if factual_confidence < CONFIDENCE_THRESHOLD:
        return (
            VerificationDecision.ESCALATED,
            None,
        )

    # ---------------------------------------------------------------
    # 7. APPROVED
    # ---------------------------------------------------------------

    return (
        VerificationDecision.APPROVED,
        None,
    )


# ---------------------------------------------------------------------------
# Main Agent 4 entry point
# ---------------------------------------------------------------------------

def run_agent4(
    agent1_or_payload: Union[
        Agent1Output,
        Agent4Input,
    ],
    agent2: Optional[Agent2Output] = None,
    agent3: Optional[Agent3Output] = None,
    version_lookup: Optional[VersionLookupFn] = None,
) -> Agent4Output:
    """
    Main Agent 4 entry point.

    Recommended usage:

        result = run_agent4(
            agent1_output,
            agent2_output,
            agent3_output,
        )

    Optional production version lookup:

        result = run_agent4(
            agent1_output,
            agent2_output,
            agent3_output,
            version_lookup=my_version_lookup,
        )

    Backward-compatible usage:

        payload = Agent4Input(...)
        result = run_agent4(payload)

    Parameters
    ----------
    agent1_or_payload:
        Either Agent1Output or old Agent4Input.

    agent2:
        Agent2Output when using the new integration interface.

    agent3:
        Agent3Output when using the new integration interface.

    version_lookup:
        Optional DB-backed version lookup function.
    """

    # ------------------------------------------------------------------
    # Resolve input format
    # ------------------------------------------------------------------

    if isinstance(
        agent1_or_payload,
        Agent4Input,
    ):
        # Old interface:
        #
        # run_agent4(payload)
        #
        agent1 = None
        resolved_agent2 = (
            agent1_or_payload.agent2_output
        )
        resolved_agent3 = (
            agent1_or_payload.agent3_output
        )

        session_id = (
            agent1_or_payload.session_id
        )

        session_access_level = (
            agent1_or_payload.access_level
        )

    else:
        # New integration interface:
        #
        # run_agent4(agent1, agent2, agent3)
        #

        if agent2 is None:
            raise TypeError(
                "run_agent4() requires Agent2Output "
                "when Agent1Output is provided."
            )

        if agent3 is None:
            raise TypeError(
                "run_agent4() requires Agent3Output "
                "when Agent1Output is provided."
            )

        agent1 = agent1_or_payload

        resolved_agent2 = agent2
        resolved_agent3 = agent3

        session_id = agent1.session_id

        # IMPORTANT:
        #
        # Access level comes from Agent 1/session information.
        # It is NOT derived from the user's raw query.
        session_access_level = (
            agent1.access_level
        )

    # ------------------------------------------------------------------
    # Session consistency checks
    # ------------------------------------------------------------------

    # Agent 2 and Agent 3 must belong to the same session.
    #
    # If the session IDs do not match, fail closed.
    session_mismatch = (
        resolved_agent2.session_id != session_id
        or resolved_agent3.session_id != session_id
    )

    # ------------------------------------------------------------------
    # Build chunk lookup
    # ------------------------------------------------------------------

    chunk_lookup: dict[
        str,
        RetrievedChunk,
    ] = {
        chunk.chunk_id: chunk
        for chunk in resolved_agent2.results
    }

    # ------------------------------------------------------------------
    # Evidence check
    # ------------------------------------------------------------------

    evidence = check_evidence_sufficiency(
        resolved_agent3
    )

    # ------------------------------------------------------------------
    # Access reconfirmation
    # ------------------------------------------------------------------

    access_ok, violating_docs = (
        check_access_reconfirm(
            session_access_level,
            resolved_agent3,
            chunk_lookup,
        )
    )

    # Session mismatch is a governance/security failure.
    if session_mismatch:
        access_ok = False

        # Add a useful marker to the violation list.
        if "session_mismatch" not in violating_docs:
            violating_docs.append(
                "session_mismatch"
            )

    # ------------------------------------------------------------------
    # Factual support check
    # ------------------------------------------------------------------

    factual, factual_confidence = (
        check_factual_support(
            resolved_agent3,
            chunk_lookup,
        )
    )

    # ------------------------------------------------------------------
    # Version conflict
    # ------------------------------------------------------------------

    conflict_detected, conflict_details = (
        check_version_conflict(
            resolved_agent3,
            chunk_lookup,
            version_lookup,
        )
    )

    # ------------------------------------------------------------------
    # Retrieval confidence
    # ------------------------------------------------------------------

    retrieval_confidence_value = _enum_value(
        resolved_agent2.retrieval_confidence
    )

    retrieval_confidence_low = (
        retrieval_confidence_value
        == RetrievalConfidence.LOW.value
    )

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    decision, denial_reason = decide(
        evidence=evidence,
        access_ok=access_ok,
        factual=factual,
        factual_confidence=factual_confidence,
        version_conflict=conflict_detected,
        retrieval_confidence_low=retrieval_confidence_low,
    )

    # ------------------------------------------------------------------
    # Add violating document IDs to denial reason
    # ------------------------------------------------------------------

    if (
        decision
        == VerificationDecision.DENIED
        and not access_ok
    ):
        if violating_docs:

            denial_reason = (
                denial_reason
                or "access_violation"
            )

            denial_reason += (
                f" (doc_ids: "
                f"{', '.join(violating_docs)})"
            )

    # ------------------------------------------------------------------
    # FINAL ANSWER SECURITY RULE
    # ------------------------------------------------------------------
    #
    # The answer and citations are returned ONLY when the final decision
    # is APPROVED.
    #
    # This prevents information leakage when:
    #
    # - access is violated
    # - evidence is insufficient
    # - factual verification fails
    # - versions conflict
    # - retrieval confidence is low
    # - factual confidence is too low
    # ------------------------------------------------------------------

    approved = (
        decision
        == VerificationDecision.APPROVED
    )

    if approved:

        final_answer = (
            resolved_agent3.answer_text
        )

        final_citations = [
            {
                "doc_id": citation.doc_id,
                "doc_title": citation.doc_title,
                "section": citation.section,
            }
            for citation in resolved_agent3.citations
        ]

    else:

        final_answer = None

        final_citations = []

    # ------------------------------------------------------------------
    # Build shared Pydantic Agent4Output
    # ------------------------------------------------------------------

    return Agent4Output(
        session_id=session_id,

        decision=decision,

        denial_reason=(
            denial_reason
            if decision
            == VerificationDecision.DENIED
            else None
        ),

        evidence_sufficiency=evidence,

        factual_support_check=factual,

        version_conflict_detected=(
            conflict_detected
        ),

        conflict_details=conflict_details,

        access_reconfirmed=access_ok,

        final_answer=final_answer,

        final_citations=final_citations,

        confidence=round(
            float(factual_confidence),
            2,
        ),

        timestamp=datetime.now(
            timezone.utc
        ),
    )


# ---------------------------------------------------------------------------
# Manual smoke test
# ---------------------------------------------------------------------------
#
# Run:
#
#     python -m agent4_verification.verifier
#
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    print("=" * 70)
    print("Agent 4 — Verification & Governance")
    print("Manual smoke test")
    print("=" * 70)

    # ---------------------------------------------------------------
    # Agent 1
    # ---------------------------------------------------------------

    from shared.enums import (
        AccessLevel,
        Intent,
        RetrievalConfidence,
        UserRole,
    )

    demo_agent1 = Agent1Output(
        session_id="sess_demo",
        user_role=UserRole.CUSTOMER,
        access_level=AccessLevel.PUBLIC,
        intent=Intent.ACCOUNT_INFO,
        topic="savings account",
        normalized_query="minimum savings account balance",
        confidence=0.95,
    )

    # ---------------------------------------------------------------
    # Agent 2
    # ---------------------------------------------------------------

    demo_agent2 = Agent2Output(
        session_id="sess_demo",
        query_used="minimum savings account balance",
        access_level=AccessLevel.PUBLIC,
        results=[
            RetrievedChunk(
                doc_id="doc_001",
                doc_title="Savings Account Guide",
                chunk_id="doc_001_c03",
                chunk_text=(
                    "The minimum balance for a standard "
                    "savings account is LKR 1,000."
                ),
                similarity_score=0.91,
                doc_access_level=AccessLevel.PUBLIC,
                doc_version="v1",
                effective_date="2024-06-01",
                source_section="Section 2.1",
            )
        ],
        retrieval_confidence=RetrievalConfidence.HIGH,
    )

    # ---------------------------------------------------------------
    # Agent 3
    # ---------------------------------------------------------------

    demo_agent3 = Agent3Output(
        session_id="sess_demo",
        answer_text=(
            "The minimum balance for a standard "
            "savings account is LKR 1,000."
        ),
        grounded=True,
        citations=[
            Citation(
                doc_id="doc_001",
                doc_title="Savings Account Guide",
                section="Section 2.1",
                chunk_id="doc_001_c03",
            )
        ],
        chunks_used=[
            "doc_001_c03"
        ],
    )

    # ---------------------------------------------------------------
    # Run Agent 4
    # ---------------------------------------------------------------

    result = run_agent4(
        demo_agent1,
        demo_agent2,
        demo_agent3,
    )

    # ---------------------------------------------------------------
    # Display result
    # ---------------------------------------------------------------

    print()
    print(
        json.dumps(
            result.model_dump(mode="json"),
            indent=2,
        )
    )

    print()
    print("=" * 70)
    print("JSON serialization test")
    print("=" * 70)

    serialized = result.model_dump_json()

    print(serialized)

    print()
    print("Agent 4 smoke test completed.")