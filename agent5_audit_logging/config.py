"""
Config for Agent 5 — Audit & Compliance Logging.

Reads from the project .env. Nothing here should be hardcoded elsewhere in
the agent5_audit_logging package; always import from this module.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Storage backend ---
# "file" (default): append-only JSONL, one record per line, hash-chained
#   via file order. No DB dependency — this is what every existing test
#   uses, and it's fine for local dev/CI.
# "db": Postgres `audit_log` table (database/models.py). Production
#   backend — set AUDIT_LOG_BACKEND=db in .env once you're ready to point
#   Agent 5 at the real shared database.
AUDIT_LOG_BACKEND: str = os.getenv("AUDIT_LOG_BACKEND", "file")

# --- File backend settings (used when AUDIT_LOG_BACKEND=file, or when a
# caller passes an explicit log_path override regardless of backend) ---
AUDIT_LOG_DIR: str = os.getenv("AUDIT_LOG_DIR", "./audit_logs")
AUDIT_LOG_FILE: str = os.getenv("AUDIT_LOG_FILE", "audit_log.jsonl")
AUDIT_LOG_PATH: str = str(Path(AUDIT_LOG_DIR) / AUDIT_LOG_FILE)

Path(AUDIT_LOG_DIR).mkdir(parents=True, exist_ok=True)