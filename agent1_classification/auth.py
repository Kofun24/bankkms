"""
agent1_classification/auth.py

Handles role/session resolution for Agent 1 — backed by the real
PostgreSQL database (users, sessions tables) instead of an in-memory dict.

Design principle (unchanged from the prototype):
Role and access level are FIXED SYSTEM STATE, established at session/login
time — never inferred from the user's free-text query. This remains the
system's primary defense against prompt injection attempts to escalate
privileges.

Access model:
  - Customer: no login required. Anonymous sessions auto-provisioned at
    access_level=public.
  - Employee: login required, access_level=internal.
  - Compliance: login required, access_level=restricted.
  - Admin: login required, access_level=NONE — manages employees and
    documents, but has no knowledge-base query access at all. If an
    admin session is ever routed into the query pipeline (e.g. Agent 2),
    it should retrieve nothing and Agent 4 should deny/refuse, since
    there is no access level to search against.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from passlib.context import CryptContext
from sqlalchemy.orm import Session as DBSession

from database.config import SessionLocal
from database.models import Session as SessionRow, User, UserRole as DBUserRole, SessionRole
from shared.enums import AccessLevel, ROLE_ACCESS_MAP, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SESSION_LIFETIME_HOURS = 8


class UnknownSessionError(Exception):
    """Raised when a session_id has no valid record and anonymous access isn't allowed."""
    pass


class UnauthorizedRoleError(Exception):
    """Raised when a role is not recognized, not in the access map, or lacks
    permission for the attempted operation."""
    pass


class InvalidCredentialsError(Exception):
    """Raised when username/password don't match, or the account is inactive."""
    pass


class NoQueryAccessError(Exception):
    """Raised if an Admin session attempts to query the knowledge base —
    Admins manage the system but have no query access at all."""
    pass


@dataclass
class SessionContext:
    session_id: str
    user_role: UserRole
    access_level: AccessLevel
    anonymous: bool = False


def _get_db() -> DBSession:
    return SessionLocal()


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_user(username: str, plain_password: str, role: UserRole) -> None:
    """Creates a new employee/compliance/admin account. Customers never
    get a user record."""
    if role == UserRole.CUSTOMER:
        raise UnauthorizedRoleError("Customers do not have user accounts.")

    db = _get_db()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            raise ValueError(f"Username {username!r} already exists.")

        user = User(
            username=username,
            password_hash=hash_password(plain_password),
            role=DBUserRole(role.value),
        )
        db.add(user)
        db.commit()
    finally:
        db.close()


def login(username: str, plain_password: str) -> SessionContext:
    """
    Real login for employee/compliance/admin accounts. Deliberately raises
    the same InvalidCredentialsError whether the username doesn't exist,
    the password is wrong, or the account is inactive — standard practice
    against username enumeration.
    """
    db = _get_db()
    try:
        user = db.query(User).filter(User.username == username).first()

        if user is None or not user.is_active or not verify_password(plain_password, user.password_hash):
            raise InvalidCredentialsError("Invalid username or password.")

        session_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_LIFETIME_HOURS)

        session_row = SessionRow(
            session_token=session_token,
            user_id=user.id,
            role=SessionRole(user.role.value),
            is_anonymous=False,
            expires_at=expires_at,
        )
        db.add(session_row)
        db.commit()

        user_role = UserRole(user.role.value)
        return SessionContext(
            session_id=session_token,
            user_role=user_role,
            access_level=ROLE_ACCESS_MAP[user_role],
            anonymous=False,
        )
    finally:
        db.close()


def register_session(session_id: str, user_role: UserRole) -> None:
    """Kept for tests and anonymous provisioning. Not used for real
    employee/compliance/admin login — use login() for that."""
    if not isinstance(user_role, UserRole):
        raise UnauthorizedRoleError(f"Invalid role: {user_role!r}")

    db = _get_db()
    try:
        existing = db.query(SessionRow).filter(SessionRow.session_token == session_id).first()
        if existing:
            return

        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_LIFETIME_HOURS)
        session_row = SessionRow(
            session_token=session_id,
            user_id=None,
            role=SessionRole(user_role.value),
            is_anonymous=(user_role == UserRole.CUSTOMER),
            expires_at=expires_at,
        )
        db.add(session_row)
        db.commit()
    finally:
        db.close()


def resolve_access(session_id: str, allow_anonymous: bool = False) -> SessionContext:
    """
    The core function Agent 1 calls for every incoming query.

    Note: this resolves WHO the session belongs to and their access_level —
    it does not by itself block Admin sessions from calling this function
    (an Admin still needs resolve_access() to prove who they are for admin
    operations). The block on Admins querying the knowledge base happens
    in require_query_access(), called specifically by the query pipeline
    entry point, not here.
    """
    db = _get_db()
    try:
        session_row = db.query(SessionRow).filter(
            SessionRow.session_token == session_id
        ).first()

        is_valid = (
            session_row is not None
            and session_row.revoked_at is None
            and session_row.expires_at > datetime.now(timezone.utc)
        )

        if not is_valid:
            if not allow_anonymous:
                raise UnknownSessionError(f"No valid session found for session_id={session_id!r}")

            register_session(session_id, UserRole.CUSTOMER)
            user_role = UserRole.CUSTOMER
            is_anonymous = True
        else:
            user_role = UserRole(session_row.role.value)
            is_anonymous = session_row.is_anonymous

        access_level = ROLE_ACCESS_MAP.get(user_role)
        if access_level is None:
            raise UnauthorizedRoleError(f"No access mapping defined for role: {user_role}")

        return SessionContext(
            session_id=session_id,
            user_role=user_role,
            access_level=access_level,
            anonymous=is_anonymous,
        )
    finally:
        db.close()


def require_query_access(session_id: str) -> SessionContext:
    """
    Gate for the knowledge-base query pipeline (Agent 1's entry point).
    Same as resolve_access(), but explicitly rejects Admin sessions —
    Admins manage the system, they do not ask it questions.

    Use this instead of resolve_access() directly inside classify_query().
    """
    ctx = resolve_access(session_id, allow_anonymous=True)
    if ctx.user_role == UserRole.ADMIN:
        raise NoQueryAccessError(
            "Admin accounts manage employees and documents but cannot "
            "query the knowledge base."
        )
    return ctx


def require_admin(session_id: str) -> SessionContext:
    """
    Gate for admin-only operations (add/remove employee, upload document).
    Raises UnauthorizedRoleError if the session isn't an admin account.
    """
    ctx = resolve_access(session_id, allow_anonymous=False)
    if ctx.user_role != UserRole.ADMIN:
        raise UnauthorizedRoleError("This action requires an admin account.")
    return ctx


def end_session(session_id: str) -> None:
    """Revokes a session (logout) by setting revoked_at, preserving the
    row for audit history rather than deleting it."""
    db = _get_db()
    try:
        session_row = db.query(SessionRow).filter(
            SessionRow.session_token == session_id
        ).first()
        if session_row:
            session_row.revoked_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def is_privilege_escalation_attempt(claimed_role_text: Optional[str], actual_role: UserRole) -> bool:
    """Unchanged — flags queries claiming a role different from the
    session's actual fixed role."""
    if not claimed_role_text:
        return False

    claimed_lower = claimed_role_text.lower()
    for role in UserRole:
        if role.value in claimed_lower and role != actual_role:
            return True
    return False