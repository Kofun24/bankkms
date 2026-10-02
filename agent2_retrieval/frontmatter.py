"""
Standalone frontmatter parser, extracted so backend/main.py can read a
document's metadata directly from uploaded file bytes, before any file
exists on disk — without importing ingest.py's file-path-based internals.
"""
import re

import yaml


class MissingFrontmatterError(Exception):
    pass


def parse_frontmatter(raw_text: str) -> dict:
    """Parses the --- ... --- YAML block at the top of a document's raw
    text. Raises MissingFrontmatterError if the block isn't present —
    every document in this system (hand-authored or admin-uploaded) is
    required to have one; it's the single source of truth for doc_id,
    title, access_level, version, and effective_date.

    Line endings are normalized to \\n first, since files uploaded from
    Windows machines often use \\r\\n, which otherwise breaks the regex
    match even though the frontmatter block is clearly present."""
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    match = re.match(r"^---\n(.*?)\n---\n", normalized, re.DOTALL)
    if not match:
        raise MissingFrontmatterError(
            "Document is missing a YAML frontmatter block (--- ... ---) "
            "at the top of the file. Every document must declare doc_id, "
            "doc_title, access_level, version, and effective_date there."
        )
    return yaml.safe_load(match.group(1))