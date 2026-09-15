"""
Config for Agent 2 — Knowledge Retrieval.

Reads from the project .env. Nothing here should be hardcoded elsewhere in
the agent2_retrieval package; always import from this module.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- LLM (used only for query reformulation on low-confidence retrieval) ---
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.0-flash")

# --- Retrieval confidence ---
# CONFIDENCE_THRESHOLD is the boundary between "low" and "medium" confidence.
# Anything CONFIDENCE_THRESHOLD + HIGH_CONFIDENCE_MARGIN or above is "high".
CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
HIGH_CONFIDENCE_MARGIN: float = float(os.getenv("HIGH_CONFIDENCE_MARGIN", "0.2"))


# --- Knowledge base source documents ---
KNOWLEDGE_BASE_DIR: str = os.getenv("KNOWLEDGE_BASE_DIR", "./knowledge_base")

# --- Embeddings ---
# "tfidf"               -> pure-python, no network/model download needed. Good default
#                          for local dev, CI, and this course project.
# "sentence-transformers" -> swap in for production; requires the model to be
#                          downloadable (needs network access to huggingface.co).
EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "tfidf")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# --- Retry / reformulation ---
MAX_RETRIEVAL_ATTEMPTS: int = int(os.getenv("MAX_RETRIEVAL_ATTEMPTS", "2"))
TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "5"))

