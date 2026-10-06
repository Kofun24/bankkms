"""
Ingestion pipeline for Agent 2 — pgvector version.

Two entry points:

1. run_ingestion() — bulk ingestion. Scans knowledge_base/{public,internal,
   restricted}/*.md and seeds any document not yet chunked. Used for the
   hand-authored knowledge base and for one-time backfills.

2. ingest_document_by_id(doc_id) — single-document ingestion. Used by the
   Admin Console upload flow: admin_add_document() creates the Document
   metadata row and saves the file to knowledge_base/, then this function
   is called immediately afterward to chunk + embed that one document,
   so it's searchable right away with no separate manual step.

Both paths reuse the same frontmatter parser (agent2_retrieval.frontmatter)
and chunking logic, and both skip a document based on whether it already
HAS CHUNKS (not merely whether a Document row exists) — a row can exist
with zero chunks when created via the upload flow before chunking has run.

Run standalone (bulk):  python -m agent2_retrieval.ingest
"""
import re
from pathlib import Path

from shared.enums import AccessLevel

from . import config
from .embeddings import get_embedder
from .frontmatter import parse_frontmatter, MissingFrontmatterError
from .vector_store import VectorStore


class DocumentNotFoundError(Exception):
    """Raised by ingest_document_by_id when no Document row exists for the
    given doc_id — admin_add_document() must run first."""
    pass


def _parse_document(path: Path) -> tuple[dict, list[tuple[str, str]]]:
    """Returns (frontmatter_dict, [(section_title, section_body), ...]).
    Frontmatter parsing is delegated to the shared parse_frontmatter() so
    there's exactly one definition of the frontmatter format, shared with
    backend/main.py's upload endpoint."""
    raw = path.read_text(encoding="utf-8")
    try:
        frontmatter = parse_frontmatter(raw)
    except MissingFrontmatterError as e:
        raise ValueError(f"{path}: {e}") from e

    body = re.sub(r"^---\n.*?\n---\n", "", raw, count=1, flags=re.DOTALL).strip()
    sections: list[tuple[str, str]] = []
    parts = re.split(r"^##\s+(.+)$", body, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        text = parts[i + 1].strip()
        if text:
            sections.append((title, text))
    return frontmatter, sections


def _chunk_and_embed(store: VectorStore, document_id: int, doc_id: str, sections: list[tuple[str, str]]) -> int:
    """Shared by both entry points: embeds each section and writes chunks."""
    chunks = [
        {"chunk_id": f"{doc_id}_c{idx:02d}", "chunk_text": text, "source_section": title}
        for idx, (title, text) in enumerate(sections, start=1)
    ]
    embedder = get_embedder()
    embeddings = embedder.embed([c["chunk_text"] for c in chunks])
    for chunk, vector in zip(chunks, embeddings):
        store.add_chunk(
            document_id=document_id,
            chunk_id=chunk["chunk_id"],
            chunk_text=chunk["chunk_text"],
            source_section=chunk["source_section"],
            embedding=vector,
        )
    return len(chunks)


def load_source_documents(kb_dir: str | None = None) -> list[dict]:
    """Reads every .md file under knowledge_base/ into per-document chunk
    records, ready for embedding + DB insertion. Skips DOCUMENT_TEMPLATE.md."""
    kb_dir = Path(kb_dir or config.KNOWLEDGE_BASE_DIR)
    if not kb_dir.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {kb_dir}")

    documents: list[dict] = []
    for md_file in sorted(kb_dir.rglob("*.md")):
        if md_file.stem.upper() == "DOCUMENT_TEMPLATE":
            continue
        frontmatter, sections = _parse_document(md_file)
        documents.append(
            {
                "doc_id": frontmatter["doc_id"],
                "doc_title": frontmatter["doc_title"],
                "access_level": AccessLevel(frontmatter["access_level"]),
                "version": str(frontmatter["version"]),
                "effective_date": str(frontmatter["effective_date"]),
                "file_path": str(md_file),
                "is_current": bool(frontmatter.get("is_current", True)),
                "sections": sections,
            }
        )
    return documents


def run_ingestion(reset: bool = False, kb_dir: str | None = None) -> int:
    """Bulk-seeds Postgres from knowledge_base/*/*.md. Returns the number
    of NEW chunks written. Safe to re-run: skips any document that already
    has chunks, regardless of whether its Document row is old or new."""
    documents = load_source_documents(kb_dir)
    if not documents:
        raise ValueError("No documents found — check knowledge_base/*/*.md")

    store = VectorStore()
    if reset:
        store.reset()

    total_new_chunks = 0
    for doc in documents:
        doc_row_id, _created = store.add_document(
            doc_id=doc["doc_id"],
            title=doc["doc_title"],
            access_level=doc["access_level"],
            version=doc["version"],
            effective_date=doc["effective_date"],
            file_path=doc["file_path"],
            is_current=doc["is_current"],
        )

        if store.has_chunks(doc_row_id):
            print(f"skip (already chunked): {doc['doc_id']} — {doc['doc_title']}")
            continue

        n = _chunk_and_embed(store, doc_row_id, doc["doc_id"], doc["sections"])
        total_new_chunks += n
        print(f"seeded: {doc['doc_id']} — {doc['doc_title']} ({n} chunks)")

    return total_new_chunks


def ingest_document_by_id(doc_id: str) -> int:
    """Chunks and embeds a single already-registered Document row.

    Called by the Admin Console upload flow right after admin_add_document()
    creates the metadata row and the file is saved to knowledge_base/.
    Returns the number of chunks written (0 if already chunked).

    Raises:
        DocumentNotFoundError: no Document row exists for doc_id — the
            caller must create it (admin_add_document) before calling this.
        FileNotFoundError: the Document row's file_path doesn't point to
            a real file on disk yet.
    """
    store = VectorStore()
    doc_row = store.get_document(doc_id)
    if doc_row is None:
        raise DocumentNotFoundError(f"No document row for doc_id={doc_id!r}")

    if store.has_chunks(doc_row.id):
        return 0

    file_path = Path(doc_row.file_path)
    if not file_path.exists():
        raise FileNotFoundError(
            f"Document row exists for {doc_id!r} but no file found at "
            f"{file_path}. Save the file there, then retry ingestion."
        )

    _frontmatter, sections = _parse_document(file_path)
    return _chunk_and_embed(store, doc_row.id, doc_id, sections)


if __name__ == "__main__":
    n = run_ingestion(reset=False)
    print(f"\nDone. {n} new chunks written to document_chunks.")