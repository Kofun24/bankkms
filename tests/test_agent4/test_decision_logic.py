"""
Agent 4 — decision priority ordering.

Per the module docstring, the priority is:
    access violation      -> denied   (hard stop, never escalate a leak)
    insufficient evidence -> denied
    factual check fail    -> escalated
    version conflict      -> escalated
    low retrieval conf.   -> escalated
    confidence < threshold-> escalated
    otherwise             -> approved

These tests exercise `decide()` directly with every failing condition
set simultaneously, to prove the *ordering* -- not just that each
condition can trigger its own outcome in isolation.
"""

import pytest

from agent4_verification.verifier import CONFIDENCE_THRESHOLD, decide


def test_access_violation_wins_over_every_other_failure():
    """Even if evidence is also insufficient, there's also a version
    conflict, and confidence is low -- an access violation must still
    be reported as the reason. A leak is never allowed to be masked as
    a softer 'escalated' outcome."""
    decision, reason = decide(
        evidence="insufficient",
        access_ok=False,
        factual="fail",
        factual_confidence=0.0,
        version_conflict=True,
        retrieval_confidence_low=True,
    )
    assert decision == "denied"
    assert "access_violation" in reason


def test_insufficient_evidence_denies_when_access_is_fine():
    decision, reason = decide(
        evidence="insufficient",
        access_ok=True,
        factual="pass",
        factual_confidence=0.9,
        version_conflict=False,
        retrieval_confidence_low=False,
    )
    assert decision == "denied"
    assert "insufficient_evidence" in reason


def test_factual_fail_escalates_not_denies():
    decision, reason = decide(
        evidence="sufficient",
        access_ok=True,
        factual="fail",
        factual_confidence=0.0,
        version_conflict=False,
        retrieval_confidence_low=False,
    )
    assert decision == "escalated"
    assert reason is None


def test_version_conflict_escalates_even_with_good_factual_check():
    decision, reason = decide(
        evidence="sufficient",
        access_ok=True,
        factual="pass",
        factual_confidence=0.95,
        version_conflict=True,
        retrieval_confidence_low=False,
    )
    assert decision == "escalated"


def test_low_retrieval_confidence_escalates():
    decision, reason = decide(
        evidence="sufficient",
        access_ok=True,
        factual="pass",
        factual_confidence=0.95,
        version_conflict=False,
        retrieval_confidence_low=True,
    )
    assert decision == "escalated"


def test_confidence_below_threshold_escalates():
    decision, reason = decide(
        evidence="sufficient",
        access_ok=True,
        factual="pass",
        factual_confidence=CONFIDENCE_THRESHOLD - 0.01,
        version_conflict=False,
        retrieval_confidence_low=False,
    )
    assert decision == "escalated"


def test_confidence_at_exact_threshold_is_approved():
    """The check is `< CONFIDENCE_THRESHOLD`, so a confidence exactly
    equal to the threshold should pass through as approved."""
    decision, reason = decide(
        evidence="sufficient",
        access_ok=True,
        factual="pass",
        factual_confidence=CONFIDENCE_THRESHOLD,
        version_conflict=False,
        retrieval_confidence_low=False,
    )
    assert decision == "approved"


def test_all_checks_passing_approves():
    decision, reason = decide(
        evidence="sufficient",
        access_ok=True,
        factual="pass",
        factual_confidence=0.99,
        version_conflict=False,
        retrieval_confidence_low=False,
    )
    assert decision == "approved"
    assert reason is None


@pytest.mark.parametrize(
    "factual,version_conflict,retrieval_low,confidence,expected",
    [
        ("fail", False, False, 0.99, "escalated"),
        ("pass", True, False, 0.99, "escalated"),
        ("pass", False, True, 0.99, "escalated"),
        ("pass", False, False, 0.1, "escalated"),
        ("pass", False, False, 0.99, "approved"),
    ],
)
def test_each_escalation_trigger_independently(
    factual, version_conflict, retrieval_low, confidence, expected
):
    decision, _ = decide(
        evidence="sufficient",
        access_ok=True,
        factual=factual,
        factual_confidence=confidence,
        version_conflict=version_conflict,
        retrieval_confidence_low=retrieval_low,
    )
    assert decision == expected