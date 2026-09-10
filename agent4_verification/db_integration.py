"""
agent4_verification/db_integration.py

Production wiring for Agent 4's version-conflict detection against the
real `documents` table (Postgres, via SQLAlchemy).

Why this exists as a separate module:
Per Agent 2's handoff note, Agent2Output now only ever contains the
CURRENT version of a document — `is_current=False` rows are filtered out
at the SQL query level before Agent 2 returns anything. That means
Agent 4 can no longer detect a version conflict just by inspecting
Agent2Output (there's structurally never more than one version in it).
Detecting a real conflict requires an independent query against ALL rows
sharing a document's title, regardless of is_current.

verifier.py itself has NO database dependency — it stays fast, offline,
and unit-testable without a live Postgres connection. This module is the
only place that talks to SQLAlchemy, and it's only imported where the
real pipeline actually has a live db session (never in tests/).

Usage in the real pipeline:

    from agent4_verification.verifier import run_agent4
    from agent4_verification.db_integration import make_sqlalchemy_version_lookup

    version_lookup = make_sqlalchemy_version_lookup(db_session)
    result = run_agent4(payload, version_lookup=version_lookup)
"""

from typing import Callable

from .verifier import VersionRecord


def make_sqlalchemy_version_lookup(db_session) -> Callable[[str], list[VersionRecord]]:
    """
    Returns a version_lookup function bound to a live SQLAlchemy session,
    ready to pass into run_agent4(payload, version_lookup=...).

    Expects a `Document` model matching database/models.py's documented
    columns: Document.doc_id, Document.title, Document.version,
    Document.effective_date, Document.is_current.

    The import of `database.models` is deferred inside this function
    (rather than at module top-level) so this file can still be imported
    — and its docstring/type read — in environments where the `database`
    package isn't installed/available, e.g. when just running Agent 4's
    unit tests. Adjust the import path below if your project's actual
    layout differs from `database.models.Document`.
    """
    # Confirmed against the real schema (database/models.py): Document has
    # doc_id, title, version, effective_date (a Date column), is_current.
    from database.models import Document

    def lookup(doc_title: str) -> list[VersionRecord]:
        rows = (
            db_session.query(Document)
            .filter(Document.title == doc_title)
            .all()
        )
        return [
            VersionRecord(
                doc_id=row.doc_id,
                version=row.version,
                effective_date=str(row.effective_date),
                is_current=row.is_current,
            )
            for row in rows
        ]

    return lookup