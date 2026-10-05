"""
fix_audit_log_table.py

Fixes the auditstage enum mismatch by dropping and recreating the
audit_log table + its Postgres enum type, using SQLAlchemy's own DDL
generation from database/models.py -- so the new type/table are
guaranteed to match exactly what the current code expects.

SAFETY: refuses to run if audit_log has any rows in it (checked first).
This is only safe because the table is currently empty -- if you've
since written real data to it, do NOT run this; you'd need a proper
ALTER TYPE migration instead (ask if that's the situation).

Run:
    python fix_audit_log_table.py
"""

from sqlalchemy import text

from database.config import SessionLocal, engine
from database.models import AuditLog

db = SessionLocal()
try:
    count = db.query(AuditLog).count()
finally:
    db.close()

print(f"Current row count in audit_log: {count}")

if count > 0:
    print("\n⚠️  REFUSING TO RUN. audit_log has real data in it.")
    print("   Dropping the table would destroy that data.")
    print("   This needs a proper ALTER TYPE migration instead -- ask for help.")
    raise SystemExit(1)

print("\nTable is empty -- safe to drop and recreate.")
confirm = input("Type 'yes' to drop and recreate audit_log + its enum type: ")
if confirm.strip().lower() != "yes":
    print("Aborted, nothing changed.")
    raise SystemExit(0)

with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS audit_log"))
    conn.execute(text("DROP TYPE IF EXISTS auditstage"))
    print("Dropped old audit_log table and auditstage enum type.")

AuditLog.__table__.create(engine)
print("Recreated audit_log table with the current, correct schema.")

print("\nVerifying the fix...")
db = SessionLocal()
try:
    result = db.execute(text("SELECT enum_range(NULL::auditstage)")).scalar()
    print(f"New auditstage enum values: {result}")
finally:
    db.close()

print("\n✅ Done. Now rerun: python check_audit_db.py")