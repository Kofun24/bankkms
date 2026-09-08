"""
agent1_classification/admin_operations.py

Admin-only operations: managing employee/compliance accounts and document
metadata. Every function here is gated by require_admin() — only a
logged-in Admin session can call these successfully.

Design note: document upload here only handles METADATA (title, access
level, version, file path). Actual chunking and embedding generation is
Agent 2's responsibility — this module hands off a Document row, and
Agent 2's ingestion pipeline picks it up from there. This keeps ownership
boundaries clean: Admin manages *what exists*, Agent 2 manages *how it's
searchable*.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from agent1_classification.auth import (
    UnauthorizedRoleError,
    create_user,
    require_admin,
)
from database.config import SessionLocal
from database.models import Document, User
from database.models import UserRole as DBUserRole
from shared.enums import AccessLevel, UserRole


class DocumentNotFoundError(Exception):
    """Raised when an operation references a doc_id that doesn't exist."""
    pass


class EmployeeNotFoundError(Exception):
    """Raised when an operation references a username that doesn't exist."""
    pass


@dataclass
class EmployeeSummary:
    id: int
    username: str
    role: UserRole
    is_active: bool


@dataclass
class DocumentSummary:
    id: int
    doc_id: str
    title: str
    access_level: AccessLevel
    version: str
    is_current: bool


# ---------------- Employee management ----------------

def admin_add_employee(
    admin_session_id: str,
    username: str,
    password: str,
    role: UserRole,
) -> None:
    """
    Adds a new employee or compliance account. Requires an authenticated
    Admin session. Deliberately does not allow creating another Admin
    account through this function — admin provisioning is a separate,
    more sensitive operation (see admin_promote_to_admin below), not
    something meant to be routine.
    """
    require_admin(admin_session_id)

    if role not in (UserRole.EMPLOYEE, UserRole.COMPLIANCE):
        raise UnauthorizedRoleError(
            "admin_add_employee only creates employee or compliance accounts. "
            "Use admin_promote_to_admin for admin provisioning."
        )

    create_user(username, password, role)


def admin_promote_to_admin(admin_session_id: str, username: str) -> None:
    """
    Promotes an existing employee/compliance account to Admin, OR creates
    a brand-new Admin account if the username doesn't exist yet.
    Deliberately separate from admin_add_employee — this is a sensitive,
    infrequent action that should be easy to find and audit distinctly
    from routine employee onboarding.
    """
    require_admin(admin_session_id)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise EmployeeNotFoundError(f"No account found for username={username!r}")

        user.role = DBUserRole.ADMIN
        db.commit()
    finally:
        db.close()


def admin_deactivate_employee(admin_session_id: str, username: str) -> None:
    """
    Deactivates an account (soft delete — is_active=False), rather than
    deleting the row outright. Preserves history for audit purposes and
    avoids breaking foreign-key references from past sessions.
    """
    require_admin(admin_session_id)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise EmployeeNotFoundError(f"No account found for username={username!r}")

        user.is_active = False
        db.commit()
    finally:
        db.close()


def admin_reactivate_employee(admin_session_id: str, username: str) -> None:
    """Reverses a deactivation."""
    require_admin(admin_session_id)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise EmployeeNotFoundError(f"No account found for username={username!r}")

        user.is_active = True
        db.commit()
    finally:
        db.close()


def admin_list_employees(admin_session_id: str) -> list[EmployeeSummary]:
    """Lists all employee/compliance/admin accounts (never customers,
    since they have no account record at all)."""
    require_admin(admin_session_id)

    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.username).all()
        return [
            EmployeeSummary(
                id=u.id,
                username=u.username,
                role=UserRole(u.role.value),
                is_active=u.is_active,
            )
            for u in users
        ]
    finally:
        db.close()


# ---------------- Document management ----------------

def admin_add_document(
    admin_session_id: str,
    doc_id: str,
    title: str,
    access_level: AccessLevel,
    version: str,
    effective_date: date,
    file_path: str,
) -> DocumentSummary:
    """
    Registers a new document's metadata. Does NOT chunk or embed the
    content — that's Agent 2's ingestion pipeline, triggered separately
    once the Document row exists. This function is purely the
    "this document exists, here's its classification" step.
    """
    require_admin(admin_session_id)

    db = SessionLocal()
    try:
        existing = db.query(Document).filter(Document.doc_id == doc_id).first()
        if existing:
            raise ValueError(f"doc_id {doc_id!r} already exists.")

        doc = Document(
            doc_id=doc_id,
            title=title,
            access_level=access_level,
            version=version,
            effective_date=effective_date,
            file_path=file_path,
            is_current=True,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        return DocumentSummary(
            id=doc.id,
            doc_id=doc.doc_id,
            title=doc.title,
            access_level=AccessLevel(doc.access_level.value),
            version=doc.version,
            is_current=doc.is_current,
        )
    finally:
        db.close()


def admin_retire_document(admin_session_id: str, doc_id: str) -> None:
    """
    Marks a document as no longer current (superseded by a newer version).
    Does not delete the row or its chunks — Agent 4's version-conflict
    detection relies on retired documents still being queryable by history.
    """
    require_admin(admin_session_id)

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if doc is None:
            raise DocumentNotFoundError(f"No document found for doc_id={doc_id!r}")

        doc.is_current = False
        db.commit()
    finally:
        db.close()


def admin_list_documents(admin_session_id: str, current_only: bool = False) -> list[DocumentSummary]:
    """Lists all documents, optionally filtering to only current (non-retired) ones."""
    require_admin(admin_session_id)

    db = SessionLocal()
    try:
        query = db.query(Document)
        if current_only:
            query = query.filter(Document.is_current == True)  # noqa: E712

        docs = query.order_by(Document.doc_id).all()
        return [
            DocumentSummary(
                id=d.id,
                doc_id=d.doc_id,
                title=d.title,
                access_level=AccessLevel(d.access_level.value),
                version=d.version,
                is_current=d.is_current,
            )
            for d in docs
        ]
    finally:
        db.close()