"""
Thin wrapper around Chroma. We always pass pre-computed embeddings ourselves
(via embeddings.py) rather than letting Chroma pick its own default embedding
function — that keeps embedding logic in one place and avoids Chroma trying
to download its own model.
"""
from typing import Optional

import chromadb

from . import config


class VectorStore:
    def __init__(self):
        self._client = chromadb.PersistentClient(path=config.VECTOR_DB_PATH)
        self._collection = self._client.get_or_create_collection(
            name=config.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def is_empty(self) -> bool:
        return self._collection.count() == 0

    def reset(self) -> None:
        self._client.delete_collection(config.COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=config.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None:
        self._collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def query(
        self,
        query_embedding: list[float],
        allowed_access_levels: list[str],
        top_k: int = 5,
    ) -> dict:
        """Access-filtered semantic search. `allowed_access_levels` restricts
        results at the DB query level (not post-filtered), so a chunk whose
        doc_access_level exceeds what's allowed is never returned."""
        return self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"doc_access_level": {"$in": allowed_access_levels}},
        )