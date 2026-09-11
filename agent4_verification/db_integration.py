"""
agent4_verification/db_integration.py

Production version_lookup implementation for Agent 4's version-conflict
check — queries the `documents` table directly via SQLAlchemy, independent
of whatever Agent 2 was allowed to retrieve.

Why this has to be a separate DB query and can't be answered from
Agent2Output alone: Agent 2's pgvector retrieval filters
`Document.is_current.is_(True)` at the SQL level (see
agent2_retrieval/vector_store.py), so a single Agent2Output can only ever
contain the LIVE version of any document. Superseded versions
(is_current=False, soft-deleted via admin_retire_document()) still exist
in the table — this function is the only way Agent 4 can see them.

Usage:
    from agent4_verification.db_integration import version_lookup_from_db
    from agent4_verification.verifier import run_agent4

    result = run_agent4(
        agent1_output, agent2_output, agent3_output,
        version_lookup=version_lookup_from_db,
    )

Kept separate from verifier.py so verifier.py itself has zero DB
dependency — fast, offline-testable, importable in CI without a live
database connection (see verifier.py's module docstring).
"""

from database.config import SessionLocal
from database.models import Document

from .verifier import VersionRecord


def version_lookup_from_db(doc_title: str) -> list[VersionRecord]:
    """
    Returns every known version (current and superseded) of any document
    sharing `doc_title`, sourced directly from the `documents` table —
    including rows Agent 2's retrieval would never return.

    Follows the same SessionLocal() / try-finally pattern used throughout
    the rest of the codebase (admin_operations.py, vector_store.py) rather
    than opening a second, differently-shaped DB connection.
    """
    db = SessionLocal()
    try:
        rows = db.query(Document).filter(Document.title == doc_title).all()
        return [
            VersionRecord(
                doc_id=row.doc_id,
                version=row.version,
                effective_date=str(row.effective_date),
                is_current=row.is_current,
            )
            for row in rows
        ]
    finally:
        db.close()