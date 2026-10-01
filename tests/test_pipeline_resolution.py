"""
tests/test_pipeline_resolution.py

Unit tests for pipeline status resolution, specifically validating that
legitimate access and evidence denials are not masked as generic escalations
(regression tests for VULN-02).
"""

import pytest
from datetime import datetime, timezone
from shared.enums import EscalationReason, Priority, VerificationDecision
from shared.schemas import Agent4Output, Agent6Output
from pipeline import resolve_pipeline_status


def _make_agent4(
    decision=VerificationDecision.APPROVED,
    confidence=0.9,
    denial_reason=None,
    version_conflict_detected=False,
    final_answer="Standard savings account requires LKR 1,000 minimum balance.",
):
    return Agent4Output(
        session_id="sess_RESOLVE_TEST",
        decision=decision,
        denial_reason=denial_reason,
        evidence_sufficiency="sufficient" if decision == VerificationDecision.APPROVED else "insufficient",
        factual_support_check="pass" if decision == VerificationDecision.APPROVED else "fail",
        version_conflict_detected=version_conflict_detected,
        access_reconfirmed=True,
        final_answer=final_answer if decision == VerificationDecision.APPROVED else None,
        confidence=confidence,
        timestamp=datetime.now(timezone.utc),
    )


def _make_agent6(
    escalation_triggered=False,
    trigger_reason=EscalationReason.LOW_CONFIDENCE,
    message="",
):
    return Agent6Output(
        session_id="sess_RESOLVE_TEST",
        escalation_triggered=escalation_triggered,
        trigger_reason=trigger_reason,
        routed_to="human_review_queue" if escalation_triggered else "none",
        user_facing_message=message,
        priority=Priority.LOW,
        timestamp=datetime.now(timezone.utc),
    )


class TestPipelineStatusResolution:
    """VULN-02 regression tests: Legitimate denials must not be masked as generic escalations."""

    def test_insufficient_evidence_denial_resolves_to_denied_status(self):
        """PI-19 scenario: retrieval succeeded, generation failed to ground,
        verification denied for insufficient_evidence with confidence=0.0."""
        agent4 = _make_agent4(
            decision=VerificationDecision.DENIED,
            confidence=0.0,
            denial_reason="insufficient_evidence: no grounded, cited content available",
        )
        # Agent 6 should NOT have triggered for low confidence on a denial
        agent6 = _make_agent6(escalation_triggered=False)

        status, message = resolve_pipeline_status(agent4, agent6)

        assert status == "denied"
        assert "reliable information" in message.lower()
        assert "member of our team" not in message.lower()

    def test_access_violation_denial_resolves_to_denied_status(self):
        """Access violation must return a clear access denial."""
        agent4 = _make_agent4(
            decision=VerificationDecision.DENIED,
            confidence=0.0,
            denial_reason="access_violation: cited document(s) exceed session access_level",
        )
        agent6 = _make_agent6(escalation_triggered=False)

        status, message = resolve_pipeline_status(agent4, agent6)

        assert status == "denied"
        assert "outside what your account is authorized to access" in message.lower()

    def test_denial_even_if_agent6_incorrectly_flags_low_confidence_still_denies(self):
        """Defense-in-depth: Even if Agent 6's low confidence trigger somehow fired on confidence=0.0,
        pipeline.py's status resolution must prioritize the legitimate denial."""
        agent4 = _make_agent4(
            decision=VerificationDecision.DENIED,
            confidence=0.0,
            denial_reason="insufficient_evidence: no grounded, cited content available",
        )
        agent6 = _make_agent6(
            escalation_triggered=True,
            trigger_reason=EscalationReason.LOW_CONFIDENCE,
            message="Passed to a team member for a closer look.",
        )

        status, message = resolve_pipeline_status(agent4, agent6)

        assert status == "denied"
        assert "reliable information" in message.lower()

    def test_denial_with_repeated_denial_escalates_to_human(self):
        """When a user has repeated denials in the same session, human handoff is warranted."""
        agent4 = _make_agent4(
            decision=VerificationDecision.DENIED,
            confidence=0.0,
            denial_reason="insufficient_evidence: no grounded, cited content available",
        )
        agent6 = _make_agent6(
            escalation_triggered=True,
            trigger_reason=EscalationReason.REPEATED_DENIAL,
            message="A team member will reach out to help directly.",
        )

        status, message = resolve_pipeline_status(agent4, agent6)

        assert status == "escalated"
        assert "reach out" in message.lower()

    def test_denial_with_suspicious_pattern_escalates_to_security(self):
        """When prompt-injection attempt is detected, escalation takes precedence."""
        agent4 = _make_agent4(
            decision=VerificationDecision.DENIED,
            confidence=0.0,
            denial_reason="access_violation: cited document(s) exceed session access_level",
        )
        agent6 = _make_agent6(
            escalation_triggered=True,
            trigger_reason=EscalationReason.SUSPICIOUS_PATTERN,
            message="We're taking a closer look at this request before responding.",
        )

        status, message = resolve_pipeline_status(agent4, agent6)

        assert status == "escalated"
        assert "taking a closer look" in message.lower()

    def test_approved_answer_with_low_confidence_escalates(self):
        """If an answer was approved but factual confidence is low, escalate."""
        agent4 = _make_agent4(
            decision=VerificationDecision.APPROVED,
            confidence=0.3,
        )
        agent6 = _make_agent6(
            escalation_triggered=True,
            trigger_reason=EscalationReason.LOW_CONFIDENCE,
            message="Passed to a member of our team for a closer look.",
        )

        status, message = resolve_pipeline_status(agent4, agent6)

        assert status == "escalated"
        assert "closer look" in message.lower()

    def test_approved_answer_with_high_confidence_answers_normally(self):
        """Confident approved answer returns status='answered'."""
        agent4 = _make_agent4(
            decision=VerificationDecision.APPROVED,
            confidence=0.9,
            final_answer="Account opening requires valid NIC and proof of billing address.",
        )
        agent6 = _make_agent6(escalation_triggered=False)

        status, message = resolve_pipeline_status(agent4, agent6)

        assert status == "answered"
        assert "Account opening requires" in message

    def test_approved_answer_with_version_conflict_appends_notice(self):
        """Approved answer with document version history appends transparency notice."""
        agent4 = _make_agent4(
            decision=VerificationDecision.APPROVED,
            confidence=0.9,
            version_conflict_detected=True,
            final_answer="Account interest rate is 6.5% p.a.",
        )
        agent6 = _make_agent6(escalation_triggered=False)

        status, message = resolve_pipeline_status(agent4, agent6)

        assert status == "answered"
        assert "reflect the current version" in message
