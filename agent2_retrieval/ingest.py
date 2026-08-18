"""
Ingestion pipeline for Agent 2.

Each source document is a Markdown file with YAML frontmatter:

    ---
    doc_id: doc_014
    doc_title: AML Procedure
    access_level: restricted
    version: v2
    effective_date: 2025-01-01
    ---

    ## Section 4.2: Suspicious Transaction Indicators
    ...body...

Chunking strategy: split on level-2 headers ("## ..."). Each resulting chunk
maps 1:1 to a `source_section`, which keeps citations in Agent 3/4 meaningful
instead of arbitrary character-window chunks.

Run standalone:  python -m agent2_retrieval.ingest
"""
import re
from pathlib import Path

import yaml

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
    # parts[0] is any preamble before the first header (usually empty)
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        text = parts[i + 1].strip()
        if text:
            sections.append((title, text))
    return frontmatter, sections


def load_source_documents(kb_dir: str | None = None) -> list[dict]:
    """Reads every .md file under knowledge_base/ (public/, internal/,
    restricted/ subfolders) into chunk records, ready for embedding +
    insertion. The folder a document sits in is just for human organization —
    the authoritative access_level always comes from the file's frontmatter."""
    kb_dir = Path(kb_dir or config.KNOWLEDGE_BASE_DIR)
    if not kb_dir.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {kb_dir}")

    chunks: list[dict] = []
    for md_file in sorted(kb_dir.rglob("*.md")):
        if md_file.stem.upper() == "DOCUMENT_TEMPLATE":
            continue
        frontmatter, sections = _parse_document(md_file)
        doc_id = frontmatter["doc_id"]
        for idx, (section_title, section_text) in enumerate(sections, start=1):
            chunk_id = f"{doc_id}_c{idx:02d}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "doc_title": frontmatter["doc_title"],
                    "chunk_text": section_text,
                    "doc_access_level": frontmatter["access_level"],
                    "doc_version": str(frontmatter["version"]),
                    "effective_date": str(frontmatter["effective_date"]),
                    "source_section": section_title,
                }
            )
    return chunks


def run_ingestion(reset: bool = True, kb_dir: str | None = None) -> int:
    """Builds/rebuilds the vector index from the source documents. Returns
    the number of chunks ingested."""
    chunks = load_source_documents(kb_dir)
    if not chunks:
        raise ValueError("No chunks found — check knowledge_base/documents/*.md")

    embedder = get_embedder()
    # Fit on the full corpus so the TF-IDF vocabulary covers every document.
    embedder.fit([c["chunk_text"] for c in chunks])
    embedder.save()

    store = VectorStore()
    if reset:
        store.reset()

    embeddings = embedder.embed([c["chunk_text"] for c in chunks])
    store.add_chunks(
        ids=[c["chunk_id"] for c in chunks],
        documents=[c["chunk_text"] for c in chunks],
        embeddings=embeddings,
        metadatas=[
            {
                "doc_id": c["doc_id"],
                "doc_title": c["doc_title"],
                "doc_access_level": c["doc_access_level"],
                "doc_version": c["doc_version"],
                "effective_date": c["effective_date"],
                "source_section": c["source_section"],
            }
            for c in chunks
        ],
    )
    return len(chunks)


if __name__ == "__main__":
    n = run_ingestion()
    print(f"Ingested {n} chunks into the vector store at {config.VECTOR_DB_PATH}")