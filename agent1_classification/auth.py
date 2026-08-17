"""
agent1_classification/auth.py

Handles role/session resolution for Agent 1.

Design principle (from BankKMS Responsible AI plan):
Role and access level are FIXED SYSTEM STATE, established at session/login time —
never inferred from the user's free-text query. This is the system's primary
defense against prompt injection attempts to escalate privileges
(e.g. "as a compliance officer, tell me...").
"""

from dataclasses import dataclass
from typing import Optional

from shared.enums import AccessLevel, ROLE_ACCESS_MAP, UserRole


class UnknownSessionError(Exception):
    """Raised when a session_id has no associated role in the session store."""
    pass


class UnauthorizedRoleError(Exception):
    """Raised when a role is not recognized / not in the access map."""
    pass


@dataclass
class SessionContext:
    session_id: str
    user_role: UserRole
    access_level: AccessLevel


class SessionStore:
    """
    Simulated session store standing in for a real login/identity system.

    In a real deployment this would be backed by an auth service (JWT, OAuth,
    bank SSO, etc.). For this project, sessions are registered explicitly
    (e.g. via a simple login endpoint or test fixture) and role is fixed
    for the lifetime of the session.
    """

    def __init__(self):
        self._sessions: dict[str, UserRole] = {}

    def register_session(self, session_id: str, user_role: UserRole) -> None:
        """
        Called at 'login' time only — this is the ONE place role enters the
        system. Nothing downstream (classifier, retrieval, etc.) may change it.
        """
        if not isinstance(user_role, UserRole):
            raise UnauthorizedRoleError(f"Invalid role: {user_role!r}")
        self._sessions[session_id] = user_role

    def get_role(self, session_id: str) -> UserRole:
        role = self._sessions.get(session_id)
        if role is None:
            raise UnknownSessionError(f"No session found for session_id={session_id!r}")
        return role

    def end_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


# Single shared instance for the app. In a larger system this might be
# swapped for a Redis-backed store or similar — the interface stays the same.
_session_store = SessionStore()


def register_session(session_id: str, user_role: UserRole) -> None:
    _session_store.register_session(session_id, user_role)


def resolve_access(session_id: str) -> SessionContext:
    """
    The core function Agent 1 calls for every incoming query.

    Looks up the fixed role for this session, then maps it to an access level
    via the fixed ROLE_ACCESS_MAP — never via anything in the query text.

    Raises UnknownSessionError if the session hasn't been registered/logged in.
    """
    user_role = _session_store.get_role(session_id)
    access_level = ROLE_ACCESS_MAP.get(user_role)

    if access_level is None:
        # Should be unreachable if ROLE_ACCESS_MAP covers all UserRole values,
        # but fail safe rather than silently granting access.
        raise UnauthorizedRoleError(f"No access mapping defined for role: {user_role}")

    return SessionContext(
        session_id=session_id,
        user_role=user_role,
        access_level=access_level,
    )


def is_privilege_escalation_attempt(claimed_role_text: Optional[str], actual_role: UserRole) -> bool:
    """
    Optional helper for sanitizer.py / classifier.py:
    flags cases where the query text explicitly claims a different role than
    the session's actual fixed role (e.g. "as a compliance officer...").

    This does NOT change access_level — it only raises a flag for
    flags.possible_injection_attempt in Agent1Output, and gives you a clean,
    citable control for your individual security-audit assignment.
    """
    if not claimed_role_text:
        return False

    claimed_lower = claimed_role_text.lower()
    for role in UserRole:
        if role.value in claimed_lower and role != actual_role:
            return True
    return False