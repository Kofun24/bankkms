"""
Pluggable embedding backend for Agent 2.

Two providers are supported, chosen via EMBEDDING_PROVIDER in .env:

- "tfidf": scikit-learn TfidfVectorizer. Deterministic, no model download,
  no network needed. Good enough to prove out chunking / access-filtering /
  retry logic, and what this repo runs in CI / local dev by default.

- "sentence-transformers": a real sentence embedding model (e.g.
  all-MiniLM-L6-v2). Higher retrieval quality, but requires downloading the
  model weights the first time (needs outbound network access). Recommended
  for your final submission / demo if your machine has internet access.

The vectorizer/model is fit once at ingest time and persisted, then reused
(not refit) at query time so query and document vectors live in the same
space.
"""
import pickle
from pathlib import Path
from typing import Protocol

from . import config


class Embedder(Protocol):
    def fit(self, texts: list[str]) -> None: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def save(self) -> None: ...
    def load(self) -> bool: ...


class TfidfEmbedder:
    """Default offline embedder."""

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            max_features=4096,
        )
        self._fitted = False
        self._path = Path(config.VECTOR_DB_PATH) / "tfidf_vectorizer.pkl"

    def fit(self, texts: list[str]) -> None:
        self._vectorizer.fit(texts)
        self._fitted = True

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._fitted:
            raise RuntimeError("TfidfEmbedder must be fit() or load()ed before embed().")
        return self._vectorizer.transform(texts).toarray().tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            pickle.dump(self._vectorizer, f)

    def load(self) -> bool:
        if not self._path.exists():
            return False
        with open(self._path, "rb") as f:
            self._vectorizer = pickle.load(f)
        self._fitted = True
        return True


class SentenceTransformerEmbedder:
    """Production embedder. Requires network access to download model weights
    the first time it runs on a given machine."""

    def __init__(self):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(config.EMBEDDING_MODEL)

    def fit(self, texts: list[str]) -> None:
        # No fitting needed — the model is pre-trained.
        pass

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def save(self) -> None:
        pass

    def load(self) -> bool:
        return True


def get_embedder() -> Embedder:
    if config.EMBEDDING_PROVIDER == "sentence-transformers":
        return SentenceTransformerEmbedder()
    return TfidfEmbedder()