"""
diagnose_auditstage_enum.py

Read-only check: shows exactly what values Postgres's `auditstage` enum
type currently accepts, vs what database.models.AuditStage expects.
Run this BEFORE fix_audit_log_table.py so you can see the actual
mismatch, not just take my word for it.

Run:
    python diagnose_auditstage_enum.py
"""

from sqlalchemy import text

from database.config import SessionLocal
from database.models import AuditStage

db = SessionLocal()
try:
    result = db.execute(text("SELECT enum_range(NULL::auditstage)")).scalar()
    print("Values currently allowed by Postgres's auditstage enum type:")
    print(f"  {result}")
finally:
    db.close()

expected = [e.value for e in AuditStage]
print(f"\nValues database.models.AuditStage expects (via values_callable):")
print(f"  {expected}")

print("\nIf these two lists don't match, that's the bug -- the live Postgres")
print("enum type was created before/differently from the current model")
print("definition. Since audit_log has 0 rows, the safe fix is to drop and")
print("recreate both cleanly: python fix_audit_log_table.py")