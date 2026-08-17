# BankKMS — Agent Interface Contracts (Draft v1)

Purpose: freeze the JSON shape each agent emits so agents can be built in parallel without
blocking on each other. Every agent takes the previous agent's output as (part of) its input,
plus its own additions. Treat this as a living doc — update it once the team agrees on changes
in the Aug 16–17 session, and note the version/date at the top.

---

## Agent 1 — Query & User Classification

**Input:** raw user message + session context (role is NOT derived from the message text).

```json
{
  "session_id": "sess_8823",
  "user_role": "customer | employee | compliance",
  "raw_query": "string, sanitized (control chars stripped, length-capped)",
  "timestamp": "ISO 8601"
}
```

**Output → passed to Agent 2:**

```json
{
  "session_id": "sess_8823",
  "user_role": "customer | employee | compliance",
  "access_level": "public | internal | restricted",
  "intent": "account_info | procedure_lookup | policy_check | complaint | fraud_report | other",
  "topic": "free-text short label, e.g. 'minimum balance requirement'",
  "normalized_query": "cleaned/rephrased version of raw_query for retrieval",
  "confidence": 0.0,
  "needs_clarification": false,
  "clarifying_question": null,
  "flags": {
    "suspicious_input": false,
    "possible_injection_attempt": false
  },
  "timestamp": "ISO 8601"
}
```

**Notes:**
- `access_level` is derived from `user_role` via a fixed mapping table, never inferred from `raw_query` — this is the anti-injection control your own RAI plan calls for.
- If `needs_clarification` is `true`, Agent 1 returns this object directly to the user (does not call Agent 2) and waits for a follow-up message.
- `flags` feeds Agent 5 (Audit Logging) and gives you ready-made evidence for your individual assignment's injection test cases.

---

## Agent 2 — Knowledge Retrieval

**Input:** Agent 1's output.

**Output → passed to Agent 3:**

```json
{
  "session_id": "sess_8823",
  "query_used": "string (possibly reformulated)",
  "reformulated": false,
  "retrieval_attempts": 1,
  "access_level": "public | internal | restricted",
  "results": [
    {
      "doc_id": "doc_014",
      "doc_title": "AML Procedure v2",
      "chunk_id": "doc_014_c07",
      "chunk_text": "string",
      "similarity_score": 0.82,
      "doc_access_level": "restricted",
      "doc_version": "v2",
      "effective_date": "2025-01-01",
      "source_section": "Section 4.2"
    }
  ],
  "retrieval_confidence": "high | medium | low",
  "access_filter_applied": true,
  "timestamp": "ISO 8601"
}
```

**Notes:**
- `access_filter_applied: true` is a hard requirement — Agent 2 must never return a chunk whose `doc_access_level` exceeds the incoming `access_level`. This is your first of two access checks (the second is Agent 4).
- If `retrieval_confidence` is `low` on first pass, Agent 2 reformulates the query once and retries (`retrieval_attempts: 2`, `reformulated: true`) before handing off — don't loop indefinitely.
- Empty `results` is valid and must be passed through, not hidden — Agent 3 needs to know there's nothing to answer from.

---

## Agent 3 — Knowledge Analysis & Response

**Input:** Agent 2's output.

**Output → passed to Agent 4:**

```json
{
  "session_id": "sess_8823",
  "answer_text": "string — grounded answer, or refusal if no evidence",
  "grounded": true,
  "citations": [
    {
      "doc_id": "doc_014",
      "doc_title": "AML Procedure v2",
      "section": "Section 4.2",
      "chunk_id": "doc_014_c07"
    }
  ],
  "chunks_used": ["doc_014_c07", "doc_014_c09"],
  "chunks_discarded": ["doc_014_c11"],
  "synthesis_notes": "brief note on how multiple chunks were combined, if applicable",
  "timestamp": "ISO 8601"
}
```

**Notes:**
- If `results` from Agent 2 was empty or irrelevant, `grounded` is `false` and `answer_text` should be an explicit "I don't have information on this" — never fall back to general LLM knowledge. This is the single most important rule in your whole system and the first thing your Agent 3 owner (and Member 3's RAI audit) will test.
- Every claim in `answer_text` should map to at least one entry in `citations` — Agent 4 will check this.

---

## Agent 4 — Verification & Governance

**Input:** Agent 3's output + original `access_level`/`user_role` from Agent 1.

**Output → passed to Agent 5 (log) and to the user (if approved):**

```json
{
  "session_id": "sess_8823",
  "decision": "approved | denied | escalated",
  "denial_reason": null,
  "evidence_sufficiency": "sufficient | insufficient",
  "factual_support_check": "pass | fail",
  "version_conflict_detected": false,
  "conflict_details": null,
  "access_reconfirmed": true,
  "final_answer": "string — only populated if decision == approved",
  "final_citations": [
    { "doc_id": "doc_014", "doc_title": "AML Procedure v2", "section": "Section 4.2" }
  ],
  "confidence": 0.0,
  "timestamp": "ISO 8601"
}
```

**Notes:**
- This is your second access check. Even if Agent 2 filtered correctly, Agent 4 re-confirms `access_level` against every `doc_id` in `citations` before releasing anything — defense in depth, and a clean explainability story for the viva ("why was access denied" maps directly to `denial_reason`).
- `decision: escalated` is what feeds Agent 6 — low confidence, unresolved version conflict, or failed factual-support check should route here instead of a hard `denied`.

---

## Agent 5 — Audit & Compliance Logging (extension)

**Input:** hooked into Agents 1–4 at each decision point (not a single upstream agent).

**Output:** append-only log record, one per stage per session.

```json
{
  "log_id": "log_00019281",
  "session_id": "sess_8823",
  "stage": "classification | retrieval | generation | verification",
  "agent": "Agent 1",
  "payload_snapshot": { "...": "the relevant agent's output object, verbatim" },
  "decision_summary": "short human-readable line, e.g. 'access_level=restricted approved'",
  "timestamp": "ISO 8601",
  "immutable_hash": "sha256 of payload_snapshot, for tamper-evidence"
}
```

**Notes:**
- Immutable in practice = append-only store (or hash-chained log) — doesn't need to be fancy, but the design should defend "immutable" if asked in the viva.
- This is the direct data source for the individual security-audit assignment's evidence sections, so keep `payload_snapshot` complete rather than summarized.

---

## Agent 6 — Escalation & Human Handoff (extension)

**Input:** Agent 4's output (primarily `decision: escalated`, but also watches for patterns across a session, e.g. repeated denials).

**Output:**

```json
{
  "session_id": "sess_8823",
  "escalation_triggered": true,
  "trigger_reason": "low_confidence | version_conflict | suspicious_pattern | repeated_denial",
  "routed_to": "human_review_queue",
  "user_facing_message": "string — what the user sees while waiting, not a raw refusal",
  "priority": "low | medium | high",
  "timestamp": "ISO 8601"
}
```

**Notes:**
- Distinguish this from a flat `denied` in Agent 4 — escalation means "unresolved," not "no." The `user_facing_message` should read as "this needs a closer look," not a rejection.

---

## Cross-cutting field conventions

- `session_id` and `timestamp` appear in every agent's output — non-negotiable, since Agent 5 needs to stitch the full trail together.
- Use the same `access_level` and `user_role` enums everywhere (`public | internal | restricted`, `customer | employee | compliance`) — don't let different agents invent their own casing/spelling.
- Every agent that can fail should have an explicit failure/refusal shape rather than throwing — the verification and escalation logic depends on structured signals, not exceptions.

**Next step for the team:** walk through one end-to-end example query for each `user_role` (customer/employee/compliance) through all 4 core agents using these exact shapes, before anyone starts coding. That'll surface any field mismatches before Aug 25.