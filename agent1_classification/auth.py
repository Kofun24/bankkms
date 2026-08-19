"""
agent1_classification/auth.py

Handles role/session resolution for Agent 1.

Design principle (from BankKMS Responsible AI plan):
Role and access level are FIXED SYSTEM STATE, established at session/login time —
never inferred from the user's free-text query. This is the system's primary
defense against prompt injection attempts to escalate privileges
(e.g. "as a compliance officer, tell me...").

Access model:
  - Customers: no login required. Public-tier knowledge base content carries
    no personal/sensitive data, so anonymous sessions are auto-provisioned
    at access_level=public. This is a deliberate least-privilege /
    data-minimization design choice, not an oversight.
  - Employees / Compliance: login required (simulated fixed-credentials
    check elsewhere in the app). Sessions must be explicitly registered
    via register_session() before resolve_access() will succeed for them.
"""

from dataclasses import dataclass
from typing import Optional

from shared.enums import AccessLevel, ROLE_ACCESS_MAP, UserRole


class UnknownSessionError(Exception):
    """Raised when a session_id has no associated role and anonymous access isn't allowed."""
    pass


class UnauthorizedRoleError(Exception):
    """Raised when a role is not recognized / not in the access map."""
    pass


@dataclass
class SessionContext:
    session_id: str
    user_role: UserRole
    access_level: AccessLevel
    anonymous: bool = False


class SessionStore:
    """
    Simulated session store standing in for a real login/identity system.
    """

    def __init__(self):
        self._sessions: dict[str, UserRole] = {}

    def register_session(self, session_id: str, user_role: UserRole) -> None:
        if not isinstance(user_role, UserRole):
            raise UnauthorizedRoleError(f"Invalid role: {user_role!r}")
        self._sessions[session_id] = user_role

    def get_role(self, session_id: str) -> Optional[UserRole]:
        return self._sessions.get(session_id)

    def has_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    def end_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


_session_store = SessionStore()


def register_session(session_id: str, user_role: UserRole) -> None:
    _session_store.register_session(session_id, user_role)


def resolve_access(session_id: str, allow_anonymous: bool = False) -> SessionContext:
    """
    The core function Agent 1 calls for every incoming query.

    Args:
        session_id: the caller's session identifier.
        allow_anonymous: if True, an unregistered session_id is treated as
            an anonymous customer and auto-provisioned at access_level=public,
            rather than raising UnknownSessionError. Use this for the
            customer-facing entry point only — employee/compliance entry
            points should call with allow_anonymous=False (the default) so
            a missing login is a hard error, not a silent downgrade.

    Raises:
        UnknownSessionError: session not found and allow_anonymous=False.
        UnauthorizedRoleError: role has no entry in ROLE_ACCESS_MAP.
    """
    existing_role = _session_store.get_role(session_id)

    if existing_role is None:
        if not allow_anonymous:
            raise UnknownSessionError(f"No session found for session_id={session_id!r}")
        # Auto-provision anonymous customer session — public tier only.
        _session_store.register_session(session_id, UserRole.CUSTOMER)
        existing_role = UserRole.CUSTOMER
        is_anonymous = True
    else:
        is_anonymous = False

    access_level = ROLE_ACCESS_MAP.get(existing_role)
    if access_level is None:
        raise UnauthorizedRoleError(f"No access mapping defined for role: {existing_role}")

    return SessionContext(
        session_id=session_id,
        user_role=existing_role,
        access_level=access_level,
        anonymous=is_anonymous,
    )


def is_privilege_escalation_attempt(claimed_role_text: Optional[str], actual_role: UserRole) -> bool:
    if not claimed_role_text:
        return False

    claimed_lower = claimed_role_text.lower()
    for role in UserRole:
        if role.value in claimed_lower and role != actual_role:
            return True
    return False