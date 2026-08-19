"""
Agent 2 — Knowledge Retrieval.

Input:  Agent1Output   (from shared.schemas)
Output: Agent2Output    (from shared.schemas)

Implements the contract in docs/interfaces.md:
- access_filter_applied must always be True: a chunk whose doc_access_level
  exceeds the incoming access_level is never returned. This is enforced at
  the vector-store query level (see vector_store.query's `where` clause),
  not by filtering after the fact.
- If retrieval_confidence is "low" on the first pass, the query is
  reformulated once and retried (retrieval_attempts=2, reformulated=True)
  before handing off — it does not loop indefinitely.
- Empty `results` is valid and is passed through as-is.
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
                "No fitted embedder found. Run ingestion first: "
                "python -m agent2_retrieval.ingest"
            )
        self._store = VectorStore()
        if self._store.is_empty():
            raise RuntimeError(
                "Vector store is empty. Run ingestion first: "
                "python -m agent2_retrieval.ingest"
            )

    def _search(self, query_text: str, access_level: AccessLevel, top_k: int) -> list[RetrievedChunk]:
        query_embedding = self._embedder.embed_query(query_text)
        allowed = [lvl.value for lvl in allowed_access_levels(access_level)]
        raw = self._store.query(query_embedding, allowed_access_levels=allowed, top_k=top_k)

        chunks: list[RetrievedChunk] = []
        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        dists = raw.get("distances", [[]])[0]

        for chunk_id, text, meta, dist in zip(ids, docs, metas, dists):
            # Chroma with cosine space returns a distance in [0, 2]; similarity = 1 - dist/2
            similarity = max(0.0, min(1.0, 1 - (dist / 2)))
            chunks.append(
                RetrievedChunk(
                    doc_id=meta["doc_id"],
                    doc_title=meta["doc_title"],
                    chunk_id=chunk_id,
                    chunk_text=text,
                    similarity_score=round(similarity, 4),
                    doc_access_level=AccessLevel(meta["doc_access_level"]),
                    doc_version=meta["doc_version"],
                    effective_date=meta["effective_date"],
                    source_section=meta["source_section"],
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
                # Keep whichever pass did better instead of blindly trusting the retry.
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