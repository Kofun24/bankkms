"""
Config for Agent 5 — Audit & Compliance Logging.

Reads from the project .env. Nothing here should be hardcoded elsewhere in
the agent5_audit_logging package; always import from this module.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Audit log storage ---
# Append-only JSONL, one record per line, hash-chained for tamper-evidence
# (each record's immutable_hash is computed over its own content plus the
# previous record's hash — see logger.py). No database needed for this
# project's scope; the chain itself is what makes tampering detectable.
AUDIT_LOG_DIR: str = os.getenv("AUDIT_LOG_DIR", "./audit_logs")
AUDIT_LOG_FILE: str = os.getenv("AUDIT_LOG_FILE", "audit_log.jsonl")
AUDIT_LOG_PATH: str = str(Path(AUDIT_LOG_DIR) / AUDIT_LOG_FILE)

Path(AUDIT_LOG_DIR).mkdir(parents=True, exist_ok=True)