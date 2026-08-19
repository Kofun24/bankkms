"""
Agent 4 — factual support check.

Covers three layers:
  1. check_factual_support's own short-circuits (no citations; chunks_used
     not a subset of cited chunk_ids) which must never even reach the LLM.
  2. llm_factual_support_check's offline fallback heuristic when no
     Gemini client is configured.
  3. llm_factual_support_check with a mocked Gemini client: happy path,
     malformed JSON, invalid verdict string, and a raised exception.

All Gemini calls are mocked via the `fake_gemini` / `failing_gemini`
fixtures from conftest.py — no real network calls are made.
"""

from agent4_verification.verifier import (
    check_factual_support,
    llm_factual_support_check,
)


# --------------------------------------------------------------------------
# check_factual_support: short-circuits before any LLM call
# --------------------------------------------------------------------------

def test_no_citations_fails_without_calling_llm(make_agent3_output):
    agent3 = make_agent3_output(citations=[], chunks_used=[])
    verdict, confidence = check_factual_support(agent3, {})
    assert (verdict, confidence) == ("fail", 0.0)


def test_chunks_used_not_subset_of_cited_fails_fast(
    happy_path, make_agent3_output, make_citation
):
    """If Agent 3 claims to have used a chunk it never cited, that's a
    red flag on its own -- Agent 4 should fail without spending an LLM
    call verifying it."""
    citation = make_citation()
    agent3 = make_agent3_output(
        citations=[citation], chunks_used=["some_uncited_chunk_id"]
    )
    lookup = {happy_path["chunk"].chunk_id: happy_path["chunk"]}
    verdict, confidence = check_factual_support(agent3, lookup)
    assert (verdict, confidence) == ("fail", 0.0)


def test_valid_citations_reach_the_llm_layer(happy_path):
    """Sanity check that the happy-path fixture reaches the (mocked-off)
    LLM layer and gets the offline fallback verdict, rather than
    short-circuiting."""
    lookup = {happy_path["chunk"].chunk_id: happy_path["chunk"]}
    verdict, confidence = check_factual_support(happy_path["agent3"], lookup)
    assert verdict == "pass"  # fallback heuristic: has chunk_texts -> pass, low confidence
    assert confidence == 0.5


# --------------------------------------------------------------------------
# llm_factual_support_check: offline fallback (no_gemini is autouse)
# --------------------------------------------------------------------------

def test_fallback_fails_with_no_chunk_texts():
    verdict, confidence = llm_factual_support_check("some answer", [])
    assert (verdict, confidence) == ("fail", 0.0)


def test_fallback_passes_with_low_confidence_when_chunks_present():
    """No Gemini client configured but chunks exist -> can't verify, but
    also can't prove it's wrong, so the heuristic passes with confidence
    0.5. Combined with the default 0.6 threshold, this alone is not
    enough to reach 'approved' -- see test_run_agent4_integration.py."""
    verdict, confidence = llm_factual_support_check(
        "The minimum balance is LKR 1,000.", ["chunk text here"]
    )
    assert (verdict, confidence) == ("pass", 0.5)


# --------------------------------------------------------------------------
# llm_factual_support_check: mocked Gemini client
# --------------------------------------------------------------------------

def test_gemini_pass_verdict_is_parsed(fake_gemini):
    fake_gemini('{"verdict": "pass", "confidence": 0.93, "reason": "fully supported"}')
    verdict, confidence = llm_factual_support_check(
        "The minimum balance is LKR 1,000.", ["The minimum balance is LKR 1,000."]
    )
    assert verdict == "pass"
    assert confidence == 0.93


def test_gemini_fail_verdict_is_parsed(fake_gemini):
    fake_gemini('{"verdict": "fail", "confidence": 0.2, "reason": "unsupported claim"}')
    verdict, confidence = llm_factual_support_check(
        "The minimum balance is LKR 5,000.", ["The minimum balance is LKR 1,000."]
    )
    assert verdict == "fail"
    assert confidence == 0.2


def test_gemini_response_wrapped_in_markdown_fences_is_still_parsed(fake_gemini):
    fake_gemini('```json\n{"verdict": "pass", "confidence": 0.8, "reason": "ok"}\n```')
    verdict, confidence = llm_factual_support_check("answer", ["chunk"])
    assert verdict == "pass"
    assert confidence == 0.8


def test_gemini_malformed_json_fails_closed(fake_gemini):
    fake_gemini("this is not json at all")
    verdict, confidence = llm_factual_support_check("answer", ["chunk"])
    assert (verdict, confidence) == ("fail", 0.0)


def test_gemini_invalid_verdict_string_defaults_to_fail(fake_gemini):
    fake_gemini('{"verdict": "maybe", "confidence": 0.9, "reason": "unclear"}')
    verdict, confidence = llm_factual_support_check("answer", ["chunk"])
    assert verdict == "fail"
    assert confidence == 0.9  # confidence is still parsed even if verdict is coerced


def test_gemini_missing_fields_default_safely(fake_gemini):
    fake_gemini("{}")
    verdict, confidence = llm_factual_support_check("answer", ["chunk"])
    assert verdict == "fail"
    assert confidence == 0.0


def test_gemini_exception_fails_closed(failing_gemini):
    verdict, confidence = llm_factual_support_check("answer", ["chunk"])
    assert (verdict, confidence) == ("fail", 0.0)