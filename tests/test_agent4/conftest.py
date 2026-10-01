"""
tests/test_agent4/conftest.py

Shared fixtures for Agent 4 (Verification & Governance) tests.

These fixtures use the real shared.enums and shared.schemas objects used
by Agents 1-3. Gemini is disabled by default so the tests remain
deterministic and never make real API calls.

The file also provides terminal reporting for the Individual Assignment:
Privacy & Data Leakage Assessment.

Each AUD-01 ... AUD-15 test prints:
    [PASS] test name
    Purpose: test description

At the end, a complete AUD-01 ... AUD-15 summary is printed.
"""

from __future__ import annotations

import pytest

import agent4_verification.verifier as verifier
from shared.enums import AccessLevel, Intent, RetrievalConfidence, UserRole
from shared.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Citation,
    RetrievedChunk,
)


# ==========================================================================
# Gemini client control
# ==========================================================================

class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeModels:
    def __init__(self, text: str):
        self._text = text

    def generate_content(self, model, contents):
        return _FakeResponse(self._text)


class _FakeGeminiClient:
    """
    Fake Gemini client used by tests that need a controlled
    pass/fail verdict and confidence.
    """

    def __init__(self, response_text: str):
        self.models = _FakeModels(response_text)


class _RaisingClient:
    """
    Fake Gemini client that raises an exception.

    Used to verify that Agent 4 fails closed when the LLM layer
    becomes unavailable.
    """

    class _Models:
        def generate_content(self, model, contents):
            raise RuntimeError("simulated Gemini failure")

    def __init__(self):
        self.models = self._Models()


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    """
    Disable Gemini for every test by default.

    This prevents real network calls and keeps the test suite
    deterministic.
    """
    monkeypatch.setattr(verifier, "_gemini_client", None)
    monkeypatch.setattr(verifier, "GEMINI_API_KEY", None)
    yield


@pytest.fixture
def fake_gemini(monkeypatch):
    """
    Install a fake Gemini client.

    Example:

        fake_gemini(
            '{"verdict": "pass", "confidence": 0.95, "reason": "supported"}'
        )
    """

    def _install(response_text: str):
        monkeypatch.setattr(
            verifier,
            "_gemini_client",
            _FakeGeminiClient(response_text),
        )
        return response_text

    return _install


@pytest.fixture
def failing_gemini(monkeypatch):
    """
    Install a Gemini client that raises an exception.
    """
    monkeypatch.setattr(
        verifier,
        "_gemini_client",
        _RaisingClient(),
    )


# ==========================================================================
# Domain object factories
# ==========================================================================

@pytest.fixture
def make_chunk():
    """
    Factory for a real RetrievedChunk object.
    """

    def _make(
        doc_id="doc_001",
        doc_title="Savings Account Guide",
        chunk_id="doc_001_c03",
        chunk_text=(
            "The minimum balance for a standard savings account "
            "is LKR 1,000."
        ),
        similarity_score=0.91,
        doc_access_level=AccessLevel.PUBLIC,
        doc_version="v1",
        effective_date="2024-06-01",
        source_section="Section 2.1",
    ) -> RetrievedChunk:

        return RetrievedChunk(
            doc_id=doc_id,
            doc_title=doc_title,
            chunk_id=chunk_id,
            chunk_text=chunk_text,
            similarity_score=similarity_score,
            doc_access_level=doc_access_level,
            doc_version=doc_version,
            effective_date=effective_date,
            source_section=source_section,
        )

    return _make


@pytest.fixture
def make_citation():
    """
    Factory for a real Citation object.
    """

    def _make(
        doc_id="doc_001",
        doc_title="Savings Account Guide",
        section="Section 2.1",
        chunk_id="doc_001_c03",
    ) -> Citation:

        return Citation(
            doc_id=doc_id,
            doc_title=doc_title,
            section=section,
            chunk_id=chunk_id,
        )

    return _make


@pytest.fixture
def make_agent1_output():
    """
    Factory for a real Agent1Output object.
    """

    def _make(
        session_id="sess_test",
        user_role=UserRole.CUSTOMER,
        access_level=AccessLevel.PUBLIC,
        intent=Intent.ACCOUNT_INFO,
        topic="savings_account",
        normalized_query=(
            "What is the minimum balance for a savings account?"
        ),
        confidence=0.9,
    ) -> Agent1Output:

        return Agent1Output(
            session_id=session_id,
            user_role=user_role,
            access_level=access_level,
            intent=intent,
            topic=topic,
            normalized_query=normalized_query,
            confidence=confidence,
        )

    return _make


@pytest.fixture
def make_agent2_output():
    """
    Factory for a real Agent2Output object.
    """

    def _make(
        session_id="sess_test",
        query_used="minimum balance savings account",
        access_level=AccessLevel.PUBLIC,
        results=None,
        retrieval_confidence=RetrievalConfidence.HIGH,
    ) -> Agent2Output:

        return Agent2Output(
            session_id=session_id,
            query_used=query_used,
            access_level=access_level,
            results=results or [],
            retrieval_confidence=retrieval_confidence,
        )

    return _make


@pytest.fixture
def make_agent3_output():
    """
    Factory for a real Agent3Output object.
    """

    def _make(
        session_id="sess_test",
        answer_text=(
            "The minimum balance for a standard savings account "
            "is LKR 1,000."
        ),
        grounded=True,
        citations=None,
        chunks_used=None,
    ) -> Agent3Output:

        return Agent3Output(
            session_id=session_id,
            answer_text=answer_text,
            grounded=grounded,
            citations=citations or [],
            chunks_used=chunks_used or [],
        )

    return _make


@pytest.fixture
def happy_path(
    make_chunk,
    make_citation,
    make_agent1_output,
    make_agent2_output,
    make_agent3_output,
):
    """
    Minimal valid public-tier scenario.

    One public document, one citation and one used chunk.
    """

    chunk = make_chunk()
    citation = make_citation()

    agent1 = make_agent1_output()

    agent2 = make_agent2_output(
        results=[chunk],
    )

    agent3 = make_agent3_output(
        citations=[citation],
        chunks_used=[chunk.chunk_id],
    )

    return {
        "chunk": chunk,
        "citation": citation,
        "agent1": agent1,
        "agent2": agent2,
        "agent3": agent3,
    }


# ==========================================================================
# SIMPLE PRIVACY TEST TERMINAL REPORT
# ==========================================================================

_AUD_DESCRIPTIONS = {}


def pytest_collection_modifyitems(config, items):
    """
    Collect the description of every AUD test.
    """

    for item in items:
        if item.name.startswith("test_AUD"):
            docstring = item.function.__doc__

            if docstring:
                description = " ".join(
                    line.strip()
                    for line in docstring.strip().splitlines()
                    if line.strip()
                )
            else:
                description = "No description available."

            _AUD_DESCRIPTIONS[item.nodeid] = description


def pytest_runtest_logreport(report):
    """
    Print a simple result immediately after each test.
    """

    if report.when != "call":
        return

    if "test_AUD" not in report.nodeid:
        return

    test_name = report.nodeid.split("::")[-1]

    # Extract AUD number
    audit_id = test_name.replace("test_", "").split("_")[0]

    if report.passed:
        result = "PASS"
    elif report.failed:
        result = "FAIL"
    elif report.skipped:
        result = "SKIPPED"
    else:
        result = report.outcome.upper()

    description = _AUD_DESCRIPTIONS.get(
        report.nodeid,
        "No description available."
    )

    print()
    print("=" * 70)
    print(f"TEST CASE : {audit_id}")
    print(f"RESULT    : {result}")
    print("-" * 70)
    print(f"Purpose   : {description}")
    print("=" * 70)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Print a simple final summary.
    """

    reports = []

    for outcome in ("passed", "failed", "skipped"):

        for report in terminalreporter.stats.get(outcome, []):

            if report.when != "call":
                continue

            if "test_AUD" not in report.nodeid:
                continue

            reports.append(report)

    if not reports:
        return

    # Sort AUD-01, AUD-02 ... AUD-15
    def get_number(report):
        test_name = report.nodeid.split("::")[-1]

        number = ""

        for char in test_name:
            if char.isdigit():
                number += char

        return int(number) if number else 999

    reports.sort(key=get_number)

    passed = 0
    failed = 0
    skipped = 0

    print()
    print()
    print("=" * 70)
    print("       PRIVACY & DATA LEAKAGE ASSESSMENT")
    print("=" * 70)

    for report in reports:

        test_name = report.nodeid.split("::")[-1]

        number = ""

        for char in test_name:
            if char.isdigit():
                number += char

        audit_id = f"AUD-{int(number):02d}" if number else "AUD-?"

        if report.passed:
            result = "PASS"
            passed += 1

        elif report.failed:
            result = "FAIL"
            failed += 1

        else:
            result = "SKIPPED"
            skipped += 1

        print(f"{audit_id:<10} : {result}")

    total = passed + failed + skipped

    print()
    print("-" * 70)
    print(f"Total Tests : {total}")
    print(f"Passed      : {passed}")
    print(f"Failed      : {failed}")
    print(f"Skipped     : {skipped}")
    print("-" * 70)

    if failed == 0:
        print("FINAL RESULT: ALL PRIVACY TESTS PASSED")
    else:
        print("FINAL RESULT: SOME TESTS FAILED")

    print("=" * 70)