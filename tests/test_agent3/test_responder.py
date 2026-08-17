from unittest.mock import patch, MagicMock

import pytest

from agent3_response.responder import analyze_and_respond, _call_llm
from shared.schemas import Agent2Output, RetrievedChunk


def _make_chunk(chunk_id="doc_001_c01", similarity=0.91):
    return RetrievedChunk(
        doc_id="doc_001",
        doc_title="Savings Account Guide",
        chunk_id=chunk_id,
        chunk_text="To open a savings account, customers need a valid NIC or passport.",
        similarity_score=similarity,
        doc_access_level="public",
        doc_version="v1",
        effective_date="2025-01-01",
        source_section="Section 2.1",
    )


def _make_agent2_output(results=None, session_id="sess_TEST"):
    return Agent2Output(
        session_id=session_id,
        query_used="What documents do I need to open a savings account?",
        access_level="public",
        results=results or [],
        retrieval_confidence="high" if results else "low",
    )


class TestGroundingRefusal:
    """Agent 3 must refuse rather than fall back to general knowledge."""

    def test_empty_results_refuses(self):
        result = analyze_and_respond(_make_agent2_output(results=[]))
        assert result.grounded is False
        assert result.citations == []
        assert "don't have information" in result.answer_text.lower()

    def test_low_similarity_chunk_is_discarded_and_refuses(self):
        # Below CONFIDENCE_THRESHOLD (default 0.6) — should never reach the LLM.
        low_score_chunk = _make_chunk(similarity=0.3)
        with patch("agent3_response.responder._call_llm") as mock_llm:
            result = analyze_and_respond(_make_agent2_output(results=[low_score_chunk]))
            mock_llm.assert_not_called()
        assert result.grounded is False
        assert "doc_001_c01" in result.chunks_discarded

    def test_llm_reports_ungrounded_still_refuses(self):
        chunk = _make_chunk()
        with patch("agent3_response.responder._call_llm") as mock_llm:
            mock_llm.return_value = {
                "answer": "I'm not sure.",
                "grounded": False,
                "chunks_used": [],
                "synthesis_notes": "Not enough info in the chunk.",
            }
            result = analyze_and_respond(_make_agent2_output(results=[chunk]))
        assert result.grounded is False
        assert result.citations == []

    def test_llm_error_fails_safe(self):
        chunk = _make_chunk()
        with patch("agent3_response.responder._call_llm", side_effect=Exception("503 UNAVAILABLE")):
            result = analyze_and_respond(_make_agent2_output(results=[chunk]))
        assert result.grounded is False
        assert "refused as fail-safe" in result.synthesis_notes


class TestGroundedAnswer:
    """When the LLM does have grounded evidence, citations must map correctly."""

    def test_successful_grounded_answer_has_matching_citation(self):
        chunk = _make_chunk(chunk_id="doc_001_c01")
        with patch("agent3_response.responder._call_llm") as mock_llm:
            mock_llm.return_value = {
                "answer": "You need a valid NIC or passport and an initial deposit.",
                "grounded": True,
                "chunks_used": ["doc_001_c01"],
                "synthesis_notes": None,
            }
            result = analyze_and_respond(_make_agent2_output(results=[chunk]))

        assert result.grounded is True
        assert len(result.citations) == 1
        assert result.citations[0].doc_id == "doc_001"
        assert result.citations[0].chunk_id == "doc_001_c01"
        assert result.citations[0].section == "Section 2.1"

    def test_hallucinated_chunk_id_is_never_cited(self):
        """If the LLM claims a chunk_id that wasn't actually retrieved, it must
        not appear in citations — this is the anti-hallucination guard."""
        chunk = _make_chunk(chunk_id="doc_001_c01")
        with patch("agent3_response.responder._call_llm") as mock_llm:
            mock_llm.return_value = {
                "answer": "Some answer.",
                "grounded": True,
                "chunks_used": ["doc_001_c01", "doc_999_fake"],
                "synthesis_notes": None,
            }
            result = analyze_and_respond(_make_agent2_output(results=[chunk]))

        cited_ids = [c.chunk_id for c in result.citations]
        assert "doc_999_fake" not in cited_ids
        assert cited_ids == ["doc_001_c01"]

    def test_unused_chunks_are_marked_discarded(self):
        chunk1 = _make_chunk(chunk_id="doc_001_c01")
        chunk2 = _make_chunk(chunk_id="doc_001_c02")
        with patch("agent3_response.responder._call_llm") as mock_llm:
            mock_llm.return_value = {
                "answer": "Some answer.",
                "grounded": True,
                "chunks_used": ["doc_001_c01"],
                "synthesis_notes": None,
            }
            result = analyze_and_respond(_make_agent2_output(results=[chunk1, chunk2]))

        assert "doc_001_c02" in result.chunks_discarded
        assert "doc_001_c02" not in result.chunks_used

    def test_multi_chunk_synthesis_cites_all_used_chunks(self):
        chunk1 = _make_chunk(chunk_id="doc_001_c01")
        chunk2 = _make_chunk(chunk_id="doc_001_c02")
        with patch("agent3_response.responder._call_llm") as mock_llm:
            mock_llm.return_value = {
                "answer": "Combined answer using both sections.",
                "grounded": True,
                "chunks_used": ["doc_001_c01", "doc_001_c02"],
                "synthesis_notes": "Combined deposit rule from c01 with ID rule from c02.",
            }
            result = analyze_and_respond(_make_agent2_output(results=[chunk1, chunk2]))

        cited_ids = {c.chunk_id for c in result.citations}
        assert cited_ids == {"doc_001_c01", "doc_001_c02"}
        assert result.chunks_discarded == []
        assert result.synthesis_notes is not None

    def test_discarded_low_similarity_chunk_cannot_be_cited(self):
        """A chunk filtered out BEFORE the prompt (low similarity) must never
        end up in citations, even if the LLM somehow references its id."""
        good_chunk = _make_chunk(chunk_id="doc_001_c01", similarity=0.9)
        low_chunk = _make_chunk(chunk_id="doc_001_c02", similarity=0.2)
        with patch("agent3_response.responder._call_llm") as mock_llm:
            mock_llm.return_value = {
                "answer": "Some answer.",
                "grounded": True,
                "chunks_used": ["doc_001_c01", "doc_001_c02"],  # c02 was never sent to the LLM
                "synthesis_notes": None,
            }
            result = analyze_and_respond(
                _make_agent2_output(results=[good_chunk, low_chunk])
            )

        cited_ids = [c.chunk_id for c in result.citations]
        assert "doc_001_c02" not in cited_ids
        assert cited_ids == ["doc_001_c01"]


class TestMalformedLLMOutput:
    """The model can return valid JSON with an unexpected shape — must fail safe."""

    def test_grounded_true_but_missing_answer_key_refuses(self):
        chunk = _make_chunk()
        with patch("agent3_response.responder._call_llm") as mock_llm:
            mock_llm.return_value = {
                "grounded": True,
                "chunks_used": ["doc_001_c01"],
                # "answer" key missing entirely
            }
            result = analyze_and_respond(_make_agent2_output(results=[chunk]))

        assert result.grounded is False
        assert result.citations == []
        assert "malformed" in result.synthesis_notes.lower()


class TestRetryLogic:
    """_call_llm should retry transient 503s with backoff, but fail fast on
    anything else. time.sleep is mocked so these tests don't actually wait."""

    def test_retries_on_503_then_succeeds(self):
        mock_response = MagicMock()
        mock_response.text = '{"answer": "ok", "grounded": true, "chunks_used": ["doc_001_c01"], "synthesis_notes": null}'

        with patch("agent3_response.responder._client") as mock_client, \
             patch("agent3_response.responder.time.sleep") as mock_sleep:
            mock_client.models.generate_content.side_effect = [
                Exception("503 UNAVAILABLE"),
                Exception("503 UNAVAILABLE"),
                mock_response,
            ]
            result = _call_llm("some prompt")

        assert result["grounded"] is True
        assert mock_client.models.generate_content.call_count == 3
        assert mock_sleep.call_count == 2  # slept before retry 2 and 3

    def test_exhausts_retries_and_raises(self):
        with patch("agent3_response.responder._client") as mock_client, \
             patch("agent3_response.responder.time.sleep"):
            mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE")

            with pytest.raises(Exception, match="503"):
                _call_llm("some prompt", max_retries=3)

        assert mock_client.models.generate_content.call_count == 3

    def test_non_503_error_fails_immediately_no_retry(self):
        with patch("agent3_response.responder._client") as mock_client, \
             patch("agent3_response.responder.time.sleep") as mock_sleep:
            mock_client.models.generate_content.side_effect = Exception("400 INVALID_ARGUMENT")

            with pytest.raises(Exception, match="400"):
                _call_llm("some prompt")

        assert mock_client.models.generate_content.call_count == 1
        mock_sleep.assert_not_called()


class TestOutputContract:
    """Every output must always carry session_id and timestamp per interfaces.md."""

    def test_session_id_propagates_through(self):
        result = analyze_and_respond(_make_agent2_output(results=[], session_id="sess_XYZ"))
        assert result.session_id == "sess_XYZ"

    def test_timestamp_is_present(self):
        result = analyze_and_respond(_make_agent2_output(results=[]))
        assert result.timestamp is not None