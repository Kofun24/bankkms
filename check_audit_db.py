"""
check_audit_db.py

Diagnostic: confirms the Agent 5 -> Postgres write path actually works,
independent of pipeline.py. Run this FIRST if audit_log looks empty --
it isolates "the DB write itself is broken" from "nothing is calling it".

Run:
    python check_audit_db.py
"""

import os

from dotenv import load_dotenv

load_dotenv()

print("=== Env check ===")
db_url = os.getenv("DATABASE_URL")
print("DATABASE_URL set:", bool(db_url), f"(starts with: {db_url[:25]}...)" if db_url else "(MISSING)")
if not db_url:
    print("\nFix: add DATABASE_URL=... to your .env file.")
    raise SystemExit(1)

print("\n=== Connection + table check ===")
try:
    from database.config import SessionLocal
    from database.models import AuditLog
    from sqlalchemy import text

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        print("Database connection: OK")

        count_before = db.query(AuditLog).count()
        print(f"Current row count in audit_log table: {count_before}")
    finally:
        db.close()
except Exception as e:
    print("Connection/table check FAILED:", repr(e))
    print("\nCommon causes: wrong DATABASE_URL, audit_log table doesn't exist yet")
    print("(did you run the Alembic migration / create the table?), network/firewall.")
    raise SystemExit(1)

print("\n=== Direct write test (bypasses pipeline.py entirely) ===")
try:
    from agent5_audit_logging.logger import append_record, verify_chain, read_all_records
    from shared.enums import LogStage

    record = append_record(
        stage=LogStage.CLASSIFICATION,
        agent="check_audit_db_diagnostic",
        session_id="sess_diagnostic_check",
        payload_snapshot={"diagnostic": True},
        decision_summary="diagnostic write from check_audit_db.py",
    )
    print(f"Wrote record: log_id={record.log_id}")

    db = SessionLocal()
    try:
        count_after = db.query(AuditLog).count()
    finally:
        db.close()

    print(f"Row count after write: {count_after}")

    if count_after == count_before + 1:
        print("\n✅ Direct write to agent5_audit_logging.logger WORKS.")
        print("   If your real pipeline run still shows nothing, the problem")
        print("   is that pipeline.py isn't calling log_*() -- check your")
        print("   actual pipeline.py has the log_classification/log_retrieval/")
        print("   log_generation/log_verification calls, not just comments.")
    else:
        print("\n⚠️  Row count didn't increase by exactly 1 -- investigate manually.")

    ok, broken = verify_chain()
    print(f"\nChain intact (whole table): {ok}")
    if not ok:
        print(f"Broken entries: {broken}")

except Exception as e:
    print("Direct write test FAILED:", repr(e))
    import traceback
    traceback.print_exc()
    print("\nThis means the write path itself is broken -- check the")
    print("traceback above (common: import error, wrong column type,")
    print("enum value mismatch between shared.enums.LogStage and")
    print("database.models.AuditStage).")