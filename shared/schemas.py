from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .enums import (
    AccessLevel,
    EscalationReason,
    EvidenceSufficiency,
    FactualSupportCheck,
    Intent,
    LogStage,
    Priority,
    RetrievalConfidence,
    UserRole,
    VerificationDecision,
)


# ---------- Agent 1: Query & User Classification ----------

class Agent1Input(BaseModel):
    session_id: str
    user_role: UserRole
    raw_query: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class InputFlags(BaseModel):
    suspicious_input: bool = False
    possible_injection_attempt: bool = False


class Agent1Output(BaseModel):
    session_id: str
    user_role: UserRole
    access_level: AccessLevel
    intent: Intent
    topic: str
    normalized_query: str
    confidence: float
    needs_clarification: bool = False
    clarifying_question: Optional[str] = None
    flags: InputFlags = Field(default_factory=InputFlags)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------- Agent 2: Knowledge Retrieval ----------

class RetrievedChunk(BaseModel):
    doc_id: str
    doc_title: str
    chunk_id: str
    chunk_text: str
    similarity_score: float
    doc_access_level: AccessLevel
    doc_version: str
    effective_date: str
    source_section: str


class Agent2Output(BaseModel):
    session_id: str
    query_used: str
    reformulated: bool = False
    retrieval_attempts: int = 1
    access_level: AccessLevel
    results: list[RetrievedChunk] = Field(default_factory=list)
    retrieval_confidence: RetrievalConfidence
    access_filter_applied: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------- Agent 3: Knowledge Analysis & Response ----------

class Citation(BaseModel):
    doc_id: str
    doc_title: str
    section: str
    chunk_id: str


class Agent3Output(BaseModel):
    session_id: str
    answer_text: str
    grounded: bool
    citations: list[Citation] = Field(default_factory=list)
    chunks_used: list[str] = Field(default_factory=list)
    chunks_discarded: list[str] = Field(default_factory=list)
    synthesis_notes: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------- Agent 4: Verification & Governance ----------

class FinalCitation(BaseModel):
    doc_id: str
    doc_title: str
    section: str


class Agent4Output(BaseModel):
    session_id: str
    decision: VerificationDecision
    denial_reason: Optional[str] = None
    evidence_sufficiency: EvidenceSufficiency
    factual_support_check: FactualSupportCheck
    version_conflict_detected: bool = False
    conflict_details: Optional[str] = None
    access_reconfirmed: bool
    final_answer: Optional[str] = None
    final_citations: list[FinalCitation] = Field(default_factory=list)
    confidence: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------- Agent 5: Audit & Compliance Logging ----------

class AuditLogRecord(BaseModel):
    log_id: str
    session_id: str
    stage: LogStage
    agent: str
    payload_snapshot: dict
    decision_summary: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    immutable_hash: str


# ---------- Agent 6: Escalation & Human Handoff ----------

class Agent6Output(BaseModel):
    session_id: str
    escalation_triggered: bool
    trigger_reason: EscalationReason
    routed_to: str = "human_review_queue"
    user_facing_message: str
    priority: Priority
    timestamp: datetime = Field(default_factory=datetime.utcnow)