from enum import Enum


class UserRole(str, Enum):
    CUSTOMER = "customer"
    EMPLOYEE = "employee"
    COMPLIANCE = "compliance"


class AccessLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


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
}