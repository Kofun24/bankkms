"""
Agent 4 — version conflict detection.

Rule under test: if two citations resolve to chunks that share the same
doc_title but differ in (doc_version, effective_date), that's a
conflict Agent 4 must surface (e.g. "minimum balance v1" vs "v2" cited
in the same answer).

Note: these tests exercise the LEGACY offline path (no version_lookup
passed -- comparing versions already present in Agent2Output). The real
DB-backed path (agent4_verification.db_integration.version_lookup_from_db)
needs a live database and isn't covered by this offline suite; verify it
manually via run_live_query.py.
"""

from agent4_verification.verifier import check_version_conflict


def test_no_conflict_with_single_citation(happy_path):
    lookup = {happy_path["chunk"].chunk_id: happy_path["chunk"]}
    detected, details = check_version_conflict(happy_path["agent3"], lookup)
    assert detected is False
    assert details is None


def test_no_conflict_when_same_doc_cited_twice_identically(
    make_chunk, make_citation, make_agent3_output
):
    chunk = make_chunk()
    citation_a = make_citation()
    citation_b = make_citation(section="Section 2.2")  # different section, same doc/version
    agent3 = make_agent3_output(
        citations=[citation_a, citation_b], chunks_used=[chunk.chunk_id]
    )
    lookup = {chunk.chunk_id: chunk}

    detected, details = check_version_conflict(agent3, lookup)

    assert detected is False
    assert details is None


def test_no_conflict_across_different_doc_titles(
    make_chunk, make_citation, make_agent3_output
):
    chunk_a = make_chunk(doc_id="doc_a", chunk_id="c_a", doc_title="Savings Account Guide")
    chunk_b = make_chunk(doc_id="doc_b", chunk_id="c_b", doc_title="Current Account Guide")
    cit_a = make_citation(doc_id="doc_a", doc_title="Savings Account Guide", chunk_id="c_a")
    cit_b = make_citation(doc_id="doc_b", doc_title="Current Account Guide", chunk_id="c_b")
    agent3 = make_agent3_output(citations=[cit_a, cit_b], chunks_used=["c_a", "c_b"])
    lookup = {"c_a": chunk_a, "c_b": chunk_b}

    detected, details = check_version_conflict(agent3, lookup)

    assert detected is False


def test_conflict_detected_for_same_title_different_versions(
    make_chunk, make_citation, make_agent3_output
):
    chunk_v1 = make_chunk(
        doc_id="doc_010", chunk_id="c1", doc_title="Minimum Balance Policy",
        doc_version="v1", effective_date="2024-01-01",
    )
    chunk_v2 = make_chunk(
        doc_id="doc_010b", chunk_id="c2", doc_title="Minimum Balance Policy",
        doc_version="v2", effective_date="2025-01-01",
    )
    cit_v1 = make_citation(doc_id="doc_010", doc_title="Minimum Balance Policy", chunk_id="c1")
    cit_v2 = make_citation(doc_id="doc_010b", doc_title="Minimum Balance Policy", chunk_id="c2")
    agent3 = make_agent3_output(citations=[cit_v1, cit_v2], chunks_used=["c1", "c2"])
    lookup = {"c1": chunk_v1, "c2": chunk_v2}

    detected, details = check_version_conflict(agent3, lookup)

    assert detected is True
    assert "Minimum Balance Policy" in details
    assert "v1" in details and "v2" in details


def test_conflict_ignores_citations_with_missing_chunks(
    make_chunk, make_citation, make_agent3_output
):
    """A citation whose chunk can't be resolved shouldn't crash the
    check -- it's just excluded from the by-title grouping (access
    re-confirmation is what's responsible for catching that case)."""
    chunk = make_chunk()
    real_citation = make_citation()
    dangling_citation = make_citation(doc_id="doc_ghost", chunk_id="does_not_exist")
    agent3 = make_agent3_output(
        citations=[real_citation, dangling_citation], chunks_used=[chunk.chunk_id]
    )
    lookup = {chunk.chunk_id: chunk}

    detected, details = check_version_conflict(agent3, lookup)

    assert detected is False
    assert details is None