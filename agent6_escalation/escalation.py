"""
agent6_escalation/escalation.py

Agent 6 — Escalation & Human Handoff.

Input: primarily Agent 4's output (decision == escalated), but per
interfaces.md this agent also watches for patterns across a session
(e.g. repeated denials) — those checks need session-level context that
isn't wired up yet and are left as TODOs for whoever owns that piece.

This module currently implements:
  - the LOW_CONFIDENCE trigger (Member 3 / Agent 3 owner's contribution)
  - the VERSION_CONFLICT trigger (Member 4 / Agent 4 owner's contribution)
  - the overall Agent 6 entry point that turns a triggered check into a
    structured Agent6Output per interfaces.md

SUSPICIOUS_PATTERN and REPEATED_DENIAL triggers are stubbed — they need
session history / flags from Agent 1 and Agent 5 respectively.
"""

from typing import Optional

from shared.enums import EscalationReason, Priority, VerificationDecision
from shared.schemas import Agent4Output, Agent6Output

# Threshold used to decide when Agent 4's confidence is too low
ESCALATION_CONFIDENCE_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Trigger checks — each returns True/False for whether ITS condition fired.
# ---------------------------------------------------------------------------

# Check whether Agent 4's confidence is below the escalation threshold
def check_low_confidence_trigger(agent4_output: Agent4Output) -> bool:
    """Member 3 / Agent 3 owner's contribution.

    Fires when Agent 4's confidence in the final answer is below the
    escalation threshold — regardless of whether Agent 4 called it
    'approved' or already flagged it 'escalated' itself.
    """
    return agent4_output.confidence < ESCALATION_CONFIDENCE_THRESHOLD


# Check whether Agent 4 detected conflicting document versions
def check_version_conflict_trigger(agent4_output: Agent4Output) -> bool:
    """Member 4 / Agent 4 owner's contribution.

    Fires when Agent 4 detected conflicting document versions that it
    couldn't resolve on its own.
    """
    return agent4_output.version_conflict_detected


# Placeholder for future suspicious-pattern detection
def check_suspicious_pattern_trigger(agent4_output: Agent4Output) -> bool:
    """TODO (Member 1 / Agent 1 owner): needs session-level flags
    (e.g. agent1_output.flags.possible_injection_attempt across the
    session), not available from a single Agent4Output alone."""
    return False


# Placeholder for future repeated-denial detection
def check_repeated_denial_trigger(agent4_output: Agent4Output) -> bool:
    """TODO (whoever owns session/audit history, likely tied to Agent 5):
    needs a count of prior 'denied' decisions for this session_id, not
    available from a single Agent4Output alone."""
    return False


# ---------------------------------------------------------------------------
# Trigger resolution
# ---------------------------------------------------------------------------

# Define trigger order and the check used for each escalation reason
_TRIGGER_CHECKS: list[tuple[EscalationReason, callable]] = [
    (EscalationReason.VERSION_CONFLICT, check_version_conflict_trigger),
    (EscalationReason.SUSPICIOUS_PATTERN, check_suspicious_pattern_trigger),
    (EscalationReason.REPEATED_DENIAL, check_repeated_denial_trigger),
    (EscalationReason.LOW_CONFIDENCE, check_low_confidence_trigger),
]

# Assign escalation priority based on the detected reason
_PRIORITY_BY_REASON = {
    EscalationReason.SUSPICIOUS_PATTERN: Priority.HIGH,
    EscalationReason.VERSION_CONFLICT: Priority.MEDIUM,
    EscalationReason.REPEATED_DENIAL: Priority.MEDIUM,
    EscalationReason.LOW_CONFIDENCE: Priority.LOW,
}

# Define the user-facing message for each escalation reason
_USER_MESSAGE_BY_REASON = {
    EscalationReason.LOW_CONFIDENCE: (
        "We want to make sure you get an accurate answer, so this question "
        "has been passed to a member of our team for a closer look. "
        "We'll follow up shortly."
    ),
    EscalationReason.VERSION_CONFLICT: (
        "This answer touches on a policy that may have recently changed. "
        "We've flagged it for a team member to confirm the current details "
        "before responding."
    ),
    EscalationReason.SUSPICIOUS_PATTERN: (
        "We're taking a closer look at this request before responding. "
        "A member of our team will follow up shortly."
    ),
    EscalationReason.REPEATED_DENIAL: (
        "It looks like we haven't been able to fully answer your recent "
        "questions. A team member will reach out to help directly."
    ),
}


# Check all triggers and return the first matching escalation reason
def determine_trigger_reason(agent4_output: Agent4Output) -> Optional[EscalationReason]:
    """Runs all trigger checks in priority order, returns the first reason
    that fires, or None if nothing warrants escalation."""
    for reason, check_fn in _TRIGGER_CHECKS:
        if check_fn(agent4_output):
            return reason
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Main Agent 6 workflow: determine whether the request needs human escalation
def evaluate_escalation(agent4_output: Agent4Output) -> Agent6Output:
    """Main entry point for Agent 6.

    Runs all trigger checks against Agent 4's output. If none fire and
    Agent 4 didn't already mark the decision as escalated, returns a
    'no escalation needed' Agent6Output (escalation_triggered=False) so
    the pipeline always gets a well-formed object rather than None.
    """
    reason = determine_trigger_reason(agent4_output)

    # Return normally when no escalation condition is detected
    if reason is None and agent4_output.decision != VerificationDecision.ESCALATED:
        return Agent6Output(
            session_id=agent4_output.session_id,
            escalation_triggered=False,
            trigger_reason=EscalationReason.LOW_CONFIDENCE,  # placeholder, unused when triggered=False
            routed_to="none",
            user_facing_message="",
            priority=Priority.LOW,
        )

    # Use a default reason if Agent 4 escalated without a detected trigger
    if reason is None:
        reason = EscalationReason.LOW_CONFIDENCE

    # Return the structured escalation result for human review
    return Agent6Output(
        session_id=agent4_output.session_id,
        escalation_triggered=True,
        trigger_reason=reason,
        routed_to="human_review_queue",
        user_facing_message=_USER_MESSAGE_BY_REASON[reason],
        priority=_PRIORITY_BY_REASON[reason],
    )


if __name__ == "__main__":
    # Simple manual test for low-confidence and normal cases
    from datetime import datetime

    mock_low_confidence = Agent4Output(
        session_id="sess_TEST_ESC01",
        decision=VerificationDecision.APPROVED,
        evidence_sufficiency="sufficient",
        factual_support_check="pass",
        access_reconfirmed=True,
        final_answer="Some tentative answer.",
        confidence=0.3,
    )
    print(evaluate_escalation(mock_low_confidence))

    mock_no_trigger = Agent4Output(
        session_id="sess_TEST_ESC02",
        decision=VerificationDecision.APPROVED,
        evidence_sufficiency="sufficient",
        factual_support_check="pass",
        access_reconfirmed=True,
        final_answer="A confident, well-grounded answer.",
        confidence=0.9,
    )
    print(evaluate_escalation(mock_no_trigger))