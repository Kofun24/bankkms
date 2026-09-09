"""
Vector store for Agent 2 — pgvector via SQLAlchemy (replaces the earlier
Chroma-based implementation).

Reads/writes through database.models.Document / DocumentChunk, using the
shared engine/session factory from database.config so Agent 2 never opens
a second, separate DB connection.

AccessLevel note: shared.enums.AccessLevel (used by Agent2Output /
RetrievedChunk, the frozen inter-agent contract) and database.models.AccessLevel
(used by the ORM columns) are two distinct Enum classes with matching
string values. They're converted explicitly at this boundary rather than
relied on to compare equal implicitly — safer if the two enums ever drift.
"""
from contextlib import contextmanager

from sqlalchemy.orm import Session as DBSession

from database.config import SessionLocal
from database.models import AccessLevel as DBAccessLevel
from database.models import Document, DocumentChunk
from shared.enums import AccessLevel as SharedAccessLevel


def to_db_access_level(level: SharedAccessLevel) -> DBAccessLevel:
    return DBAccessLevel(level.value)


def to_shared_access_level(level: DBAccessLevel) -> SharedAccessLevel:
    return SharedAccessLevel(level.value)


@contextmanager
def get_session():
    """Plain context-manager wrapper around SessionLocal. database.config's
    get_db_session() is written as a FastAPI dependency generator, which
    isn't the right shape to call directly from a standalone agent/script."""
    db: DBSession = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class VectorStore:
    """pgvector-backed store. Embeddings are computed by our own embedder
    (embeddings.py) and passed in — never generated inside the DB layer."""

    def is_empty(self) -> bool:
        with get_session() as db:
            return db.query(DocumentChunk.id).first() is None

    def reset(self) -> None:
        """Deletes all chunks and documents. Use for a full clean rebuild
        (e.g. after switching embedding models). Destructive on the shared
        Supabase instance — check with the team before running this."""
        with get_session() as db:
            db.query(DocumentChunk).delete()
            db.query(Document).delete()
            db.commit()

    def add_document(
        self,
        doc_id: str,
        title: str,
        access_level: SharedAccessLevel,
        version: str,
        effective_date: str,
        file_path: str,
    ) -> tuple[int, bool]:
        """Inserts a Document row if doc_id doesn't already exist.
        Returns (internal_id, was_created) — was_created lets the caller
        skip re-chunking a document that's already seeded."""
        with get_session() as db:
            existing = db.query(Document).filter_by(doc_id=doc_id).first()
            if existing:
                return existing.id, False
            doc = Document(
                doc_id=doc_id,
                title=title,
                access_level=to_db_access_level(access_level),
                version=version,
                effective_date=effective_date,
                file_path=file_path,
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            return doc.id, True

    def add_chunk(
        self,
        document_id: int,
        chunk_id: str,
        chunk_text: str,
        source_section: str,
        embedding: list[float],
    ) -> None:
        with get_session() as db:
            chunk = DocumentChunk(
                document_id=document_id,
                chunk_id=chunk_id,
                chunk_text=chunk_text,
                source_section=source_section,
                embedding=embedding,
            )
            db.add(chunk)
            db.commit()

    def query(
        self,
        query_embedding: list[float],
        allowed_access_levels: list[SharedAccessLevel],
        top_k: int = 5,
    ) -> list[dict]:
        """Access-filtered nearest-neighbor search using pgvector's cosine
        distance. Filtering happens in the SQL WHERE clause, not as a
        post-filter — a chunk whose document access_level exceeds what's
        allowed is never fetched, let alone returned. Also excludes
        superseded document versions (is_current=False)."""
        db_levels = [to_db_access_level(lvl) for lvl in allowed_access_levels]

        with get_session() as db:
            rows = (
                db.query(
                    DocumentChunk,
                    Document,
                    DocumentChunk.embedding.cosine_distance(query_embedding).label("distance"),
                )
                .join(Document, DocumentChunk.document_id == Document.id)
                .filter(Document.access_level.in_(db_levels))
                .filter(Document.is_current.is_(True))
                .order_by("distance")
                .limit(top_k)
                .all()
            )

            return [
                {
                    "chunk_id": chunk.chunk_id,
                    "chunk_text": chunk.chunk_text,
                    "doc_id": doc.doc_id,
                    "doc_title": doc.title,
                    "doc_access_level": to_shared_access_level(doc.access_level),
                    "doc_version": doc.version,
                    "effective_date": str(doc.effective_date),
                    "source_section": chunk.source_section or "",
                    "distance": float(distance),
                }
                for chunk, doc, distance in rows
            ]