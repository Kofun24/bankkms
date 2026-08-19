"""
Agent 4 — evidence sufficiency check.

Rule under test: `check_evidence_sufficiency` returns EvidenceSufficiency.
SUFFICIENT only when Agent 3's output is grounded AND has at least one
citation AND has at least one chunk_used. Any single missing piece must
flip it to INSUFFICIENT.
"""

from agent4_verification.verifier import check_evidence_sufficiency
from shared.enums import EvidenceSufficiency


def test_sufficient_when_grounded_with_citations_and_chunks(happy_path):
    assert check_evidence_sufficiency(happy_path["agent3"]) == EvidenceSufficiency.SUFFICIENT


def test_insufficient_when_not_grounded(make_agent3_output, make_citation):
    agent3 = make_agent3_output(
        grounded=False, citations=[make_citation()], chunks_used=["doc_001_c03"]
    )
    assert check_evidence_sufficiency(agent3) == EvidenceSufficiency.INSUFFICIENT


def test_insufficient_when_no_citations(make_agent3_output):
    agent3 = make_agent3_output(grounded=True, citations=[], chunks_used=["doc_001_c03"])
    assert check_evidence_sufficiency(agent3) == EvidenceSufficiency.INSUFFICIENT


def test_insufficient_when_no_chunks_used(make_agent3_output, make_citation):
    agent3 = make_agent3_output(grounded=True, citations=[make_citation()], chunks_used=[])
    assert check_evidence_sufficiency(agent3) == EvidenceSufficiency.INSUFFICIENT


def test_insufficient_when_everything_missing(make_agent3_output):
    agent3 = make_agent3_output(grounded=False, citations=[], chunks_used=[])
    assert check_evidence_sufficiency(agent3) == EvidenceSufficiency.INSUFFICIENT