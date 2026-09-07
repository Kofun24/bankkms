"""
database/models.py

SQLAlchemy models for BankKMS — matches the schema proposal doc agreed
with the team. Table-by-table:

- users: employee/compliance accounts only. Customers stay anonymous
  (no login, no personal data at public tier), matching auth.py's
  existing design.
- sessions: role is denormalized (copied at creation), never re-derived
  from the user later — this preserves the "access level is fixed
  system state" security principle from auth.py.
- documents: metadata + versioning, one row per document.
- document_chunks: one row per chunk, holds the actual text + pgvector
  embedding. Kept separate from `documents` for the same reason Chroma
  already separates document metadata from chunks.
- audit_log: mirrors agent5_audit_logging's hash-chained record shape,
  with prev_hash now an explicit column instead of implicit file-line
  order.
"""
import enum
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database.config import Base


def utcnow():
    return datetime.now(timezone.utc)


# ---------------- Enums ----------------

class UserRole(str, enum.Enum):
    EMPLOYEE = "employee"
    COMPLIANCE = "compliance"
    ADMIN = "admin"


class SessionRole(str, enum.Enum):
    CUSTOMER = "customer"
    EMPLOYEE = "employee"
    COMPLIANCE = "compliance"
    ADMIN = "admin"


class AccessLevel(str, enum.Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    NONE = "none"


class AuditStage(str, enum.Enum):
    CLASSIFICATION = "classification"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    VERIFICATION = "verification"
    ESCALATION = "escalation"


# ---------------- Tables ----------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole, values_callable=lambda x: [e.value for e in x]), nullable=False)  # employee | compliance | admin
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    sessions = relationship("Session", back_populates="user")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    session_token = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null = anonymous customer
    role = Column(Enum(SessionRole, values_callable=lambda x: [e.value for e in x]), nullable=False)  # fixed at creation, never re-derived
    is_anonymous = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="sessions")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    doc_id = Column(String, unique=True, nullable=False, index=True)  # e.g. "doc_001"
    title = Column(String, nullable=False)
    access_level = Column(Enum(AccessLevel, values_callable=lambda x: [e.value for e in x]), nullable=False)
    version = Column(String, nullable=False)
    effective_date = Column(Date, nullable=False)
    file_path = Column(Text, nullable=False)
    is_current = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_id = Column(String, unique=True, nullable=False, index=True)  # e.g. "doc_001_c01"
    chunk_text = Column(Text, nullable=False)
    source_section = Column(String, nullable=True)
    embedding = Column(Vector(384), nullable=True)  # 384 = all-MiniLM-L6-v2 dimension
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    document = relationship("Document", back_populates="chunks")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    log_id = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    session_id = Column(String, nullable=False, index=True)  # not FK-enforced; may be anonymous
    stage = Column(Enum(AuditStage, values_callable=lambda x: [e.value for e in x]), nullable=False)
    agent = Column(String, nullable=False)
    payload_snapshot = Column(JSONB, nullable=False)
    decision_summary = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    immutable_hash = Column(String(64), nullable=False)
    prev_hash = Column(String(64), nullable=False)