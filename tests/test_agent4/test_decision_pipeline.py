"""
Agent 4 — decision priority ordering.

Per the module docstring, the priority is:
    access violation      -> denied   (hard stop, never escalate a leak)
    insufficient evidence -> denied
    factual check fail    -> escalated
    low retrieval conf.   -> escalated
    confidence < threshold-> escalated
    otherwise             -> approved

Version conflict is NOT part of decide()'s priority list -- it's
informational metadata attached to Agent4Output (version_conflict_detected /
conflict_details), not a gate on whether the answer is released. Agent 2
only ever retrieves the current version of a document, so a conflict just
means the document has prior history, not that the answer is wrong. See
test_run_agent4_integration.py for the end-to-end case proving an answer
is still approved and returned when a conflict is detected.

These tests exercise `decide()` directly with every failing condition
set simultaneously, to prove the *ordering* -- not just that each
condition can trigger its own outcome in isolation.
"""

import pytest

from agent4_verification.verifier import CONFIDENCE_THRESHOLD, decide
from shared.enums import EvidenceSufficiency, FactualSupportCheck, VerificationDecision


def test_access_violation_wins_over_every_other_failure():
    """Even if evidence is also insufficient and confidence is low -- an
    access violation must still be reported as the reason. A leak is
    never allowed to be masked as a softer 'escalated' outcome."""
    decision, reason = decide(
        evidence=EvidenceSufficiency.INSUFFICIENT,
        access_ok=False,
        factual=FactualSupportCheck.FAIL,
        factual_confidence=0.0,
        retrieval_confidence_low=True,
    )
    assert decision == VerificationDecision.DENIED
    assert "access_violation" in reason


def test_insufficient_evidence_denies_when_access_is_fine():
    decision, reason = decide(
        evidence=EvidenceSufficiency.INSUFFICIENT,
        access_ok=True,
        factual=FactualSupportCheck.PASS,
        factual_confidence=0.9,
        retrieval_confidence_low=False,
    )
    assert decision == VerificationDecision.DENIED
    assert "insufficient_evidence" in reason


def test_factual_fail_escalates_not_denies():
    decision, reason = decide(
        evidence=EvidenceSufficiency.SUFFICIENT,
        access_ok=True,
        factual=FactualSupportCheck.FAIL,
        factual_confidence=0.0,
        retrieval_confidence_low=False,
    )
    assert decision == VerificationDecision.ESCALATED
    assert reason is not None
    assert "factual_check_failed" in reason


def test_low_retrieval_confidence_escalates():
    decision, reason = decide(
        evidence=EvidenceSufficiency.SUFFICIENT,
        access_ok=True,
        factual=FactualSupportCheck.PASS,
        factual_confidence=0.95,
        retrieval_confidence_low=True,
    )
    assert decision == VerificationDecision.ESCALATED
    assert "low_retrieval_confidence" in reason


def test_confidence_below_threshold_escalates():
    decision, reason = decide(
        evidence=EvidenceSufficiency.SUFFICIENT,
        access_ok=True,
        factual=FactualSupportCheck.PASS,
        factual_confidence=CONFIDENCE_THRESHOLD - 0.01,
        retrieval_confidence_low=False,
    )
    assert decision == VerificationDecision.ESCALATED
    assert "low_confidence" in reason


def test_confidence_at_exact_threshold_is_approved():
    """The check is `< CONFIDENCE_THRESHOLD`, so a confidence exactly
    equal to the threshold should pass through as approved."""
    decision, reason = decide(
        evidence=EvidenceSufficiency.SUFFICIENT,
        access_ok=True,
        factual=FactualSupportCheck.PASS,
        factual_confidence=CONFIDENCE_THRESHOLD,
        retrieval_confidence_low=False,
    )
    assert decision == VerificationDecision.APPROVED


def test_all_checks_passing_approves():
    decision, reason = decide(
        evidence=EvidenceSufficiency.SUFFICIENT,
        access_ok=True,
        factual=FactualSupportCheck.PASS,
        factual_confidence=0.99,
        retrieval_confidence_low=False,
    )
    assert decision == VerificationDecision.APPROVED
    assert reason is None


@pytest.mark.parametrize(
    "factual,retrieval_low,confidence,expected",
    [
        (FactualSupportCheck.FAIL, False, 0.99, VerificationDecision.ESCALATED),
        (FactualSupportCheck.PASS, True, 0.99, VerificationDecision.ESCALATED),
        (FactualSupportCheck.PASS, False, 0.1, VerificationDecision.ESCALATED),
        (FactualSupportCheck.PASS, False, 0.99, VerificationDecision.APPROVED),
    ],
)
def test_each_escalation_trigger_independently(
    factual, retrieval_low, confidence, expected
):
    decision, _ = decide(
        evidence=EvidenceSufficiency.SUFFICIENT,
        access_ok=True,
        factual=factual,
        factual_confidence=confidence,
        retrieval_confidence_low=retrieval_low,
    )
    assert decision == expected