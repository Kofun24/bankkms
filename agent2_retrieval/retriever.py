"""
Agent 2 — Knowledge Retrieval (pgvector version).

Input:  Agent1Output   (from shared.schemas)
Output: Agent2Output   (from shared.schemas)

Same contract and retry/reformulation logic as before — only the storage
backend underneath changed.
"""
from shared.enums import AccessLevel, RetrievalConfidence, allowed_access_levels
from shared.schemas import Agent1Output, Agent2Output, RetrievedChunk

from . import config
from .embeddings import get_embedder
from .llm_reformulator import reformulate_query
from .vector_store import VectorStore


class Agent2Retriever:
    def __init__(self):
        self._embedder = get_embedder()
        if not self._embedder.load():
            raise RuntimeError(
                "Embedder not ready. If EMBEDDING_PROVIDER=tfidf, run ingestion "
                "first: python -m agent2_retrieval.ingest"
            )
        self._store = VectorStore()
        if self._store.is_empty():
            raise RuntimeError(
                "document_chunks table is empty. Run ingestion first: "
                "python -m agent2_retrieval.ingest"
            )

    def _search(self, query_text: str, access_level: AccessLevel, top_k: int) -> list[RetrievedChunk]:
        query_embedding = self._embedder.embed_query(query_text)
        allowed = allowed_access_levels(access_level)
        rows = self._store.query(query_embedding, allowed_access_levels=allowed, top_k=top_k)

        chunks: list[RetrievedChunk] = []
        for row in rows:
            # pgvector's cosine_distance = 1 - cosine_similarity
            similarity = max(0.0, min(1.0, 1 - row["distance"]))
            chunks.append(
                RetrievedChunk(
                    doc_id=row["doc_id"],
                    doc_title=row["doc_title"],
                    chunk_id=row["chunk_id"],
                    chunk_text=row["chunk_text"],
                    similarity_score=round(similarity, 4),
                    doc_access_level=row["doc_access_level"],
                    doc_version=row["doc_version"],
                    effective_date=row["effective_date"],
                    source_section=row["source_section"],
                )
            )
        return chunks

    @staticmethod
    def _confidence(chunks: list[RetrievedChunk]) -> RetrievalConfidence:
        if not chunks:
            return RetrievalConfidence.LOW
        top_score = chunks[0].similarity_score
        if top_score >= config.CONFIDENCE_THRESHOLD + config.HIGH_CONFIDENCE_MARGIN:
            return RetrievalConfidence.HIGH
        if top_score >= config.CONFIDENCE_THRESHOLD:
            return RetrievalConfidence.MEDIUM
        return RetrievalConfidence.LOW

    def run(self, agent1_output: Agent1Output) -> Agent2Output:
        query = agent1_output.normalized_query
        access_level = agent1_output.access_level

        chunks = self._search(query, access_level, top_k=config.TOP_K)
        confidence = self._confidence(chunks)
        reformulated = False
        attempts = 1

        if confidence == RetrievalConfidence.LOW and config.MAX_RETRIEVAL_ATTEMPTS > 1:
            reformulated_query = reformulate_query(query, agent1_output.topic)
            if reformulated_query != query:
                retry_chunks = self._search(reformulated_query, access_level, top_k=config.TOP_K)
                retry_confidence = self._confidence(retry_chunks)
                attempts = 2
                reformulated = True
                query = reformulated_query
                if retry_chunks and (
                    not chunks or retry_chunks[0].similarity_score > chunks[0].similarity_score
                ):
                    chunks, confidence = retry_chunks, retry_confidence
                else:
                    rank = {RetrievalConfidence.LOW: 0, RetrievalConfidence.MEDIUM: 1, RetrievalConfidence.HIGH: 2}
                    confidence = max([confidence, retry_confidence], key=lambda c: rank[c])

        return Agent2Output(
            session_id=agent1_output.session_id,
            query_used=query,
            reformulated=reformulated,
            retrieval_attempts=attempts,
            access_level=access_level,
            results=chunks,
            retrieval_confidence=confidence,
            access_filter_applied=True,
        )