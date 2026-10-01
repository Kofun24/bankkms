"""
inspect_injection_flags.py — direct DB read of payload_snapshot for
classification-stage audit records, to see sanitizer.py's flags
(suspicious_input, possible_injection_attempt) that the /api/audit-log
endpoint never exposes.

Run from repo root: python inspect_injection_flags.py
"""
from database.config import SessionLocal
from database.models import AuditLog, AuditStage

db = SessionLocal()
try:
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.stage == AuditStage.CLASSIFICATION)
        .order_by(AuditLog.id.desc())
        .limit(30)
        .all()
    )
    for r in rows:
        flags = (r.payload_snapshot or {}).get("flags", {})
        query = (r.payload_snapshot or {}).get("normalized_query", "")[:70]
        print(
            f"[{r.timestamp}] session={r.session_id[:8]}... "
            f"suspicious={flags.get('suspicious_input')} "
            f"injection={flags.get('possible_injection_attempt')} "
            f"| query: {query}"
        )
finally:
    db.close()