from enum import Enum


class UserRole(str, Enum):
    CUSTOMER = "customer"
    EMPLOYEE = "employee"
    COMPLIANCE = "compliance"
    ADMIN = "admin"


class AccessLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    NONE = "none"


class Intent(str, Enum):
    ACCOUNT_INFO = "account_info"
    PROCEDURE_LOOKUP = "procedure_lookup"
    POLICY_CHECK = "policy_check"
    COMPLAINT = "complaint"
    FRAUD_REPORT = "fraud_report"
    OTHER = "other"


class RetrievalConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class VerificationDecision(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"
    ESCALATED = "escalated"


class FactualSupportCheck(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class EvidenceSufficiency(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"


class LogStage(str, Enum):
    CLASSIFICATION = "classification"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    VERIFICATION = "verification"


class EscalationReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    VERSION_CONFLICT = "version_conflict"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    REPEATED_DENIAL = "repeated_denial"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Fixed mapping: role -> access level. Access level must NEVER be derived
# from raw user text — only from this table, keyed by the session's fixed role.
ROLE_ACCESS_MAP = {
    UserRole.CUSTOMER: AccessLevel.PUBLIC,
    UserRole.EMPLOYEE: AccessLevel.INTERNAL,
    UserRole.COMPLIANCE: AccessLevel.RESTRICTED,
    UserRole.ADMIN: AccessLevel.NONE,
}

# Hierarchy used by Agent 2 / Agent 4 to decide which doc access levels
# a given session access_level is permitted to see. NONE (Admin) intentionally
# has no rank — Admin has zero query access and is blocked at Agent 1's
# require_query_access() before ever reaching Agent 2. Calling this with
# NONE means that guard failed upstream, so it raises loudly rather than
# silently returning an empty or wrong list.
ACCESS_LEVEL_RANK = {
    AccessLevel.PUBLIC: 1,
    AccessLevel.INTERNAL: 2,
    AccessLevel.RESTRICTED: 3,
}


def allowed_access_levels(access_level: AccessLevel) -> list[AccessLevel]:
    """All doc access levels a session with `access_level` is permitted to retrieve."""
    if access_level not in ACCESS_LEVEL_RANK:
        raise ValueError(
            f"access_level={access_level!r} has no defined retrieval rank "
            "(Admin/NONE sessions must never reach Agent 2)."
        )
    max_rank = ACCESS_LEVEL_RANK[access_level]
    return [lvl for lvl, rank in ACCESS_LEVEL_RANK.items() if rank <= max_rank]