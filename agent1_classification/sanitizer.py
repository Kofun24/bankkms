"""
agent1_classification/sanitizer.py

Input sanitization and injection-flag detection for Agent 1.

This runs BEFORE classification — every raw_query passes through here first.
Responsibilities:
  1. Clean/normalize the text (strip control chars, cap length, collapse whitespace)
  2. Flag suspicious patterns (heuristic-based, not a hard block)

Important: this module NEVER blocks a query or changes access_level — it only
produces flags that get attached to Agent1Output.flags, and a cleaned string
for the classifier to work with. Actual access enforcement lives in auth.py.
"""

import re
import unicodedata
from dataclasses import dataclass

MAX_QUERY_LENGTH = 2000  # generous cap; tune based on real usage

# Heuristic phrase patterns associated with prompt injection / jailbreak attempts.
# These are intentionally broad — false positives just get flagged for review,
# they don't block anything. Kept as compiled patterns for performance.
INJECTION_PATTERNS = [
    re.compile(r"ignore (all |any )?(previous|prior|above) instructions", re.IGNORECASE),
    re.compile(r"disregard (all |any )?(previous|prior|above)", re.IGNORECASE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"new instructions?\s*:", re.IGNORECASE),
    re.compile(r"reveal (your |the )?(system prompt|instructions|prompt)", re.IGNORECASE),
    re.compile(r"pretend (you are|to be)", re.IGNORECASE),
    re.compile(r"act as (a |an )?", re.IGNORECASE),
    re.compile(r"override (your |the )?(access|permissions|role|restrictions)", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"developer mode", re.IGNORECASE),
    re.compile(r"as (a |an )?(compliance officer|employee|admin|administrator)", re.IGNORECASE),
    re.compile(r"</?(system|assistant|user)>", re.IGNORECASE),  # fake role-tag injection
]

# Control characters (excluding common whitespace like \n, \t) that have no
# legitimate place in a user query and are sometimes used to smuggle payloads.
_CONTROL_CHAR_PATTERN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)


@dataclass
class SanitizationResult:
    cleaned_text: str
    original_length: int
    truncated: bool
    suspicious_input: bool
    possible_injection_attempt: bool
    matched_patterns: list[str]


def _strip_control_characters(text: str) -> str:
    return _CONTROL_CHAR_PATTERN.sub("", text)


def _normalize_unicode(text: str) -> str:
    # NFKC normalization collapses visually-confusable / lookalike unicode
    # characters (a common obfuscation trick for smuggling injection phrases
    # past naive keyword filters).
    return unicodedata.normalize("NFKC", text)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _detect_injection_patterns(text: str) -> list[str]:
    matches = []
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            matches.append(pattern.pattern)
    return matches


def sanitize_query(raw_query: str) -> SanitizationResult:
    """
    Main entry point. Call this first, before classifier.py touches the query.

    Returns a SanitizationResult with:
      - cleaned_text: safe to pass into the classifier / LLM prompt
      - suspicious_input: True if any heuristic red flag fired
      - possible_injection_attempt: True if a strong injection-style pattern matched
      - matched_patterns: the specific patterns that fired (useful for
        individual assignment evidence / logging)
    """
    if raw_query is None:
        raw_query = ""

    original_length = len(raw_query)

    text = _strip_control_characters(raw_query)
    text = _normalize_unicode(text)
    text = _collapse_whitespace(text)

    truncated = False
    if len(text) > MAX_QUERY_LENGTH:
        text = text[:MAX_QUERY_LENGTH]
        truncated = True

    matched_patterns = _detect_injection_patterns(text)

    return SanitizationResult(
        cleaned_text=text,
        original_length=original_length,
        truncated=truncated,
        suspicious_input=bool(matched_patterns) or truncated,
        possible_injection_attempt=bool(matched_patterns),
        matched_patterns=matched_patterns,
    )