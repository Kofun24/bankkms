"""
agent1_classification/classifier.py

Intent/topic classification for Agent 1 — the final step that assembles
Agent1Output. Runs AFTER auth.py (role/access resolution) and sanitizer.py
(cleaning + injection flagging).

Design:
  - classify_query() is the single public entry point Agent 1 exposes.
  - The actual intent/topic classification is pluggable: defaults to a
    lightweight rule-based classifier (no API key needed, fast to test),
    but accepts an LLM-backed classifier function for production use
    (e.g. gemini_classify from gemini_classifier.py).
  - Confidence below CONFIDENCE_THRESHOLD triggers a clarifying question
    instead of guessing, per the project plan.
"""

import os
from typing import Callable, Optional

from dotenv import load_dotenv

from agent1_classification.auth import resolve_access
from agent1_classification.sanitizer import sanitize_query, SanitizationResult
from shared.enums import Intent
from shared.schemas import Agent1Output, InputFlags

load_dotenv()

# Read from .env so the whole team shares one source of truth (currently 0.6).
# Falls back to 0.55 if the var is missing, so the module doesn't crash for
# teammates who haven't set up .env yet.
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.55"))

# Keyword sets for the rule-based fallback classifier.
_INTENT_KEYWORDS: dict[Intent, list[tuple[str, int]]] = {
    Intent.ACCOUNT_INFO: [
        ("balance", 8), ("interest rate", 9), ("savings account", 9),
        ("current account", 9), ("minimum balance", 9), ("statement", 8),
        ("account", 3),  # generic, low weight — overlaps with other intents
    ],
    Intent.PROCEDURE_LOOKUP: [
        ("how do i", 9), ("steps to", 9), ("procedure", 9),
        ("process for", 9), ("what documents", 9), ("how to open", 9),
        ("how to apply", 9), ("requirements for", 9),
    ],
    Intent.POLICY_CHECK: [
        ("kyc", 10), ("aml", 10), ("policy", 8), ("regulation", 9),
        ("compliant", 8), ("am i allowed", 8), ("is it allowed", 8),
        ("guideline", 8),
    ],
    Intent.COMPLAINT: [
        ("complaint", 10), ("unhappy", 8), ("issue with", 7),
        ("problem with", 7), ("not satisfied", 8), ("want to report", 7),
        ("poor service", 9),
    ],
    Intent.FRAUD_REPORT: [
        ("fraud", 10), ("unauthorized transaction", 10), ("scam", 10),
        ("suspicious activity", 9), ("someone accessed my account", 10),
        ("stolen", 9),
    ],
}

_GENERIC_CLARIFYING_QUESTION = (
    "Could you clarify what you're asking about? For example, are you asking "
    "about an account, a procedure, a policy, or reporting an issue?"
)

ClassifierFn = Callable[[str], tuple[Intent, str, float]]
# A classifier function takes cleaned_text and returns (intent, topic, confidence)


def _rule_based_classify(cleaned_text: str) -> tuple[Intent, str, float]:
    """
    Default fallback classifier: weighted keyword matching against
    _INTENT_KEYWORDS. Scores are summed per intent (not just the single
    longest match) so multiple weak signals can outweigh one generic
    overlapping keyword from another category.
    """
    text_lower = cleaned_text.lower()

    scores: dict[Intent, int] = {intent: 0 for intent in _INTENT_KEYWORDS}
    matched_terms: dict[Intent, list[str]] = {intent: [] for intent in _INTENT_KEYWORDS}

    for intent, keyword_weights in _INTENT_KEYWORDS.items():
        for kw, weight in keyword_weights:
            if kw in text_lower:
                scores[intent] += weight
                matched_terms[intent].append(kw)

    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]

    if best_score == 0:
        return Intent.OTHER, cleaned_text[:60], 0.3

    # Confidence scales with total matched weight, capped at 0.9
    # (rule-based approach is never fully certain without real NLU)
    confidence = min(0.9, 0.5 + (best_score / 30))

    # Use the highest-weight matched term as the topic label
    topic_terms = matched_terms[best_intent]
    topic = max(topic_terms, key=lambda t: dict(_INTENT_KEYWORDS[best_intent])[t])

    return best_intent, topic, confidence


def _generate_clarifying_question(cleaned_text: str, intent: Intent) -> str:
    if not cleaned_text.strip():
        return "It looks like your message was empty — could you tell me what you'd like help with?"
    return _GENERIC_CLARIFYING_QUESTION


def classify_query(
    session_id: str,
    raw_query: str,
    classifier_fn: Optional[ClassifierFn] = None,
) -> Agent1Output:
    """
    Main entry point for Agent 1. Orchestrates auth -> sanitize -> classify
    and returns the full Agent1Output contract for Agent 2.

    Args:
        session_id: the caller's session, previously registered via auth.register_session()
        raw_query: the raw user text
        classifier_fn: optional override for intent/topic classification.
            Defaults to the rule-based classifier. Pass gemini_classify
            (or any ClassifierFn) here for LLM-backed classification.

    Raises:
        UnknownSessionError, UnauthorizedRoleError — propagated from auth.py.
    """
    ctx = resolve_access(session_id)  # role + access_level, fixed system state

    sanitized: SanitizationResult = sanitize_query(raw_query)

    classify = classifier_fn or _rule_based_classify
    intent, topic, confidence = classify(sanitized.cleaned_text)

    needs_clarification = confidence < CONFIDENCE_THRESHOLD
    clarifying_question = (
        _generate_clarifying_question(sanitized.cleaned_text, intent)
        if needs_clarification
        else None
    )

    flags = InputFlags(
        suspicious_input=sanitized.suspicious_input,
        possible_injection_attempt=sanitized.possible_injection_attempt,
    )

    return Agent1Output(
        session_id=session_id,
        user_role=ctx.user_role,
        access_level=ctx.access_level,
        intent=intent,
        topic=topic,
        normalized_query=sanitized.cleaned_text,
        confidence=confidence,
        needs_clarification=needs_clarification,
        clarifying_question=clarifying_question,
        flags=flags,
    )