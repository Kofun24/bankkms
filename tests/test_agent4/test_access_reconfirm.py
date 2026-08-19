"""
Agent 4 — access re-confirmation check.

This is the hard security gate: every cited chunk's doc_access_level
must be <= the session's access_level on the ACCESS_RANK scale
(public=0, internal=1, restricted=2). It must also fail closed when a
cited chunk can't be found in the lookup at all (e.g. a stale/forged
chunk_id) rather than silently letting it through.
"""

import pytest

from agent4_verification.verifier import ACCESS_RANK, check_access_reconfirm


def test_same_level_access_is_allowed(happy_path):
    lookup = {happy_path["chunk"].chunk_id: happy_path["chunk"]}
    ok, violations = check_access_reconfirm("public", happy_path["agent3"], lookup)
    assert ok is True
    assert violations == []


@pytest.mark.parametrize(
    "session_level,doc_level",
    [
        ("internal", "public"),
        ("restricted", "public"),
        ("restricted", "internal"),
    ],
)
def test_higher_session_level_can_see_lower_tier_docs(
    session_level, doc_level, make_chunk, make_citation, make_agent3_output
):
    chunk = make_chunk(doc_access_level=doc_level)
    citation = make_citation()
    agent3 = make_agent3_output(citations=[citation], chunks_used=[chunk.chunk_id])
    lookup = {chunk.chunk_id: chunk}

    ok, violations = check_access_reconfirm(session_level, agent3, lookup)

    assert ok is True
    assert violations == []


@pytest.mark.parametrize(
    "session_level,doc_level",
    [
        ("public", "internal"),
        ("public", "restricted"),
        ("internal", "restricted"),
    ],
)
def test_lower_session_level_is_blocked_from_higher_tier_docs(
    session_level, doc_level, make_chunk, make_citation, make_agent3_output
):
    chunk = make_chunk(doc_id="doc_009", doc_access_level=doc_level)
    citation = make_citation(doc_id="doc_009", chunk_id=chunk.chunk_id)
    agent3 = make_agent3_output(citations=[citation], chunks_used=[chunk.chunk_id])
    lookup = {chunk.chunk_id: chunk}

    ok, violations = check_access_reconfirm(session_level, agent3, lookup)

    assert ok is False
    assert violations == ["doc_009"]


def test_citation_pointing_to_missing_chunk_fails_closed(happy_path):
    """A citation whose chunk_id isn't in the lookup (e.g. forged or
    stale) must count as a violation, not be silently ignored."""
    empty_lookup = {}
    ok, violations = check_access_reconfirm(
        "restricted", happy_path["agent3"], empty_lookup
    )
    assert ok is False
    assert violations == [happy_path["citation"].doc_id]


def test_multiple_citations_can_each_violate_independently(
    make_chunk, make_citation, make_agent3_output
):
    public_chunk = make_chunk(doc_id="doc_pub", chunk_id="c_pub", doc_access_level="public")
    restricted_chunk = make_chunk(
        doc_id="doc_restricted", chunk_id="c_restricted", doc_access_level="restricted"
    )
    cit_pub = make_citation(doc_id="doc_pub", chunk_id="c_pub")
    cit_restricted = make_citation(doc_id="doc_restricted", chunk_id="c_restricted")

    agent3 = make_agent3_output(
        citations=[cit_pub, cit_restricted],
        chunks_used=["c_pub", "c_restricted"],
    )
    lookup = {"c_pub": public_chunk, "c_restricted": restricted_chunk}

    ok, violations = check_access_reconfirm("public", agent3, lookup)

    assert ok is False
    assert violations == ["doc_restricted"]


def test_unknown_access_level_defaults_to_rank_zero():
    """Session access levels outside the known set default to rank 0
    (least privileged) via ACCESS_RANK.get(..., 0), rather than raising."""
    assert ACCESS_RANK.get("nonexistent_level", 0) == 0