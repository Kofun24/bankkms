"""
Ingestion pipeline for Agent 2 — pgvector version.

Reads knowledge_base/{public,internal,restricted}/*.md — same authoring
workflow as before, nothing changes about how documents are written — and
writes Document + DocumentChunk rows into Postgres via VectorStore. This
doubles as the one-time seed script for the 8 Phase 1 documents, now that
documents/document_chunks are real tables instead of a Chroma collection.

Run standalone:  python -m agent2_retrieval.ingest
"""
import re
from pathlib import Path

import yaml

from shared.enums import AccessLevel

from . import config
from .embeddings import get_embedder
from .vector_store import VectorStore


def _parse_document(path: Path) -> tuple[dict, list[tuple[str, str]]]:
    """Returns (frontmatter_dict, [(section_title, section_body), ...])."""
    raw = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not match:
        raise ValueError(f"{path} is missing YAML frontmatter (--- ... ---) block.")
    frontmatter = yaml.safe_load(match.group(1))
    body = match.group(2).strip()

    sections: list[tuple[str, str]] = []
    parts = re.split(r"^##\s+(.+)$", body, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        text = parts[i + 1].strip()
        if text:
            sections.append((title, text))
    return frontmatter, sections


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
        chunks = [
            {
                "chunk_id": f"{frontmatter['doc_id']}_c{idx:02d}",
                "chunk_text": text,
                "source_section": title,
            }
            for idx, (title, text) in enumerate(sections, start=1)
        ]
        documents.append(
            {
                "doc_id": frontmatter["doc_id"],
                "doc_title": frontmatter["doc_title"],
                "access_level": AccessLevel(frontmatter["access_level"]),
                "version": str(frontmatter["version"]),
                "effective_date": str(frontmatter["effective_date"]),
                "file_path": str(md_file),
                "chunks": chunks,
            }
        )
    return documents


def run_ingestion(reset: bool = False, kb_dir: str | None = None) -> int:
    """Seeds Postgres from the source documents. Returns the number of NEW
    chunks written.

    reset=True wipes documents/document_chunks first — a full clean rebuild
    (e.g. after switching embedding models). Destructive on the shared
    Supabase instance; confirm with the team before using it.

    Default reset=False is safe to re-run: add_document() is idempotent per
    doc_id and skips re-chunking anything already seeded, so running this
    twice does not create duplicate rows.
    """
    documents = load_source_documents(kb_dir)
    if not documents:
        raise ValueError("No documents found — check knowledge_base/*/*.md")

    store = VectorStore()
    if reset:
        store.reset()

    embedder = get_embedder()
    total_new_chunks = 0

    for doc in documents:
        doc_row_id, created = store.add_document(
            doc_id=doc["doc_id"],
            title=doc["doc_title"],
            access_level=doc["access_level"],
            version=doc["version"],
            effective_date=doc["effective_date"],
            file_path=doc["file_path"],
        )

        if not created:
            print(f"skip (already seeded): {doc['doc_id']} — {doc['doc_title']}")
            continue

        chunk_texts = [c["chunk_text"] for c in doc["chunks"]]
        embeddings = embedder.embed(chunk_texts)

        for chunk, vector in zip(doc["chunks"], embeddings):
            store.add_chunk(
                document_id=doc_row_id,
                chunk_id=chunk["chunk_id"],
                chunk_text=chunk["chunk_text"],
                source_section=chunk["source_section"],
                embedding=vector,
            )
            total_new_chunks += 1

        print(f"seeded: {doc['doc_id']} — {doc['doc_title']} ({len(doc['chunks'])} chunks)")

    return total_new_chunks


if __name__ == "__main__":
    n = run_ingestion(reset=False)
    print(f"\nDone. {n} new chunks written to document_chunks.")