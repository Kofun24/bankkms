"""
Agent 4 — access re-confirmation check.

This is the hard security gate: every cited chunk's doc_access_level
must be <= the session's access_level on the shared ACCESS_LEVEL_RANK
scale (public < internal < restricted). It must also fail closed when a
cited chunk can't be found in the lookup at all (e.g. a stale/forged
chunk_id) rather than silently letting it through.
"""

import pytest

from agent4_verification.verifier import check_access_reconfirm
from shared.enums import ACCESS_LEVEL_RANK, AccessLevel


def test_same_level_access_is_allowed(happy_path):
    lookup = {happy_path["chunk"].chunk_id: happy_path["chunk"]}
    ok, violations = check_access_reconfirm(
        AccessLevel.PUBLIC, happy_path["agent3"], lookup
    )
    assert ok is True
    assert violations == []


@pytest.mark.parametrize(
    "session_level,doc_level",
    [
        (AccessLevel.INTERNAL, AccessLevel.PUBLIC),
        (AccessLevel.RESTRICTED, AccessLevel.PUBLIC),
        (AccessLevel.RESTRICTED, AccessLevel.INTERNAL),
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
        (AccessLevel.PUBLIC, AccessLevel.INTERNAL),
        (AccessLevel.PUBLIC, AccessLevel.RESTRICTED),
        (AccessLevel.INTERNAL, AccessLevel.RESTRICTED),
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
        AccessLevel.RESTRICTED, happy_path["agent3"], empty_lookup
    )
    assert ok is False
    assert violations == [happy_path["citation"].doc_id]


def test_multiple_citations_can_each_violate_independently(
    make_chunk, make_citation, make_agent3_output
):
    public_chunk = make_chunk(
        doc_id="doc_pub", chunk_id="c_pub", doc_access_level=AccessLevel.PUBLIC
    )
    restricted_chunk = make_chunk(
        doc_id="doc_restricted", chunk_id="c_restricted", doc_access_level=AccessLevel.RESTRICTED
    )
    cit_pub = make_citation(doc_id="doc_pub", chunk_id="c_pub")
    cit_restricted = make_citation(doc_id="doc_restricted", chunk_id="c_restricted")

    agent3 = make_agent3_output(
        citations=[cit_pub, cit_restricted],
        chunks_used=["c_pub", "c_restricted"],
    )
    lookup = {"c_pub": public_chunk, "c_restricted": restricted_chunk}

    ok, violations = check_access_reconfirm(AccessLevel.PUBLIC, agent3, lookup)

    assert ok is False
    assert violations == ["doc_restricted"]


def test_access_level_rank_ordering_is_public_lt_internal_lt_restricted():
    assert (
        ACCESS_LEVEL_RANK[AccessLevel.PUBLIC]
        < ACCESS_LEVEL_RANK[AccessLevel.INTERNAL]
        < ACCESS_LEVEL_RANK[AccessLevel.RESTRICTED]
    )