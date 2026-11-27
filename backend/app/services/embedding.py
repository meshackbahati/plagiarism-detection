import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from app.core.model_manager import model_manager

# Sentence boundary: ., ! or ? followed by whitespace and an uppercase
# letter/digit/quote, or a blank line. Avoids splitting "e.g. this" or "3.14".
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])|\n\s*\n")


@dataclass
class TextChunk:
    text: str
    start: int  # char offset in the source text
    end: int
    words: int


def split_sentences(text: str) -> List[Tuple[int, int]]:
    """Return (start, end) char spans of sentences."""
    spans = []
    pos = 0
    for m in _SENTENCE_RE.finditer(text):
        if text[pos:m.start()].strip():
            spans.append((pos, m.start()))
        pos = m.end()
    if text[pos:].strip():
        spans.append((pos, len(text)))
    return spans


def chunk_text(text: str, target_words: int = 80, max_words: int = 160) -> List[TextChunk]:
    """
    Group whole sentences into ~target_words chunks so a chunk never cuts a
    word or sentence in half (which hurt the old fixed 500-character split).
    Very long sentences are split on word boundaries at max_words.
    """
    if not text or not text.strip():
        return []
    chunks: List[TextChunk] = []
    cur_start: Optional[int] = None
    cur_end = 0
    cur_words = 0

    def flush():
        nonlocal cur_start, cur_words
        if cur_start is not None and cur_words:
            chunks.append(TextChunk(text[cur_start:cur_end].strip(), cur_start, cur_end, cur_words))
        cur_start, cur_words = None, 0

    for s_start, s_end in split_sentences(text):
        words = [m for m in re.finditer(r"\S+", text[s_start:s_end])]
        if len(words) > max_words:
            flush()
            for i in range(0, len(words), max_words):
                part = words[i:i + max_words]
                a, b = s_start + part[0].start(), s_start + part[-1].end()
                chunks.append(TextChunk(text[a:b], a, b, len(part)))
            continue
        if cur_start is None:
            cur_start = s_start
        cur_end = s_end
        cur_words += len(words)
        if cur_words >= target_words:
            flush()
    flush()
    return chunks


class EmbeddingService:
    """
    Sentence-transformer embeddings via the shared ModelManager singleton,
    so the model is loaded once per process.
    """

    def __init__(self):
        self._manager = model_manager

    @property
    def model(self):
        return self._manager.embedding_model

    # Kept for backwards compatibility with older callers.
    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        return [c.text for c in chunk_text(text)]

    def embed_chunks(self, chunks: List[TextChunk]) -> Optional[np.ndarray]:
        """Batch-encode chunks into an (n, dim) L2-normalised matrix."""
        model = self.model
        if not model or not chunks:
            return None
        vectors = model.encode(
            [c.text for c in chunks],
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return np.asarray(vectors, dtype=np.float32)

    def encode_chunks(self, text: str) -> Tuple[List[str], list]:
        chunks = chunk_text(text)
        matrix = self.embed_chunks(chunks)
        if matrix is None:
            return [], []
        return [c.text for c in chunks], list(matrix)

    @staticmethod
    def document_vector(matrix: Optional[np.ndarray], chunks: List[TextChunk]) -> Optional[List[float]]:
        """Word-weighted mean of chunk vectors, re-normalised (for pgvector search)."""
        if matrix is None or not len(matrix):
            return None
        weights = np.array([max(1, c.words) for c in chunks], dtype=np.float32)
        vec = (matrix * weights[:, None]).sum(axis=0)
        norm = np.linalg.norm(vec)
        if norm == 0:
            return None
        return (vec / norm).tolist()

    def generate_text_embedding(self, text: str) -> list:
        chunks = chunk_text(text)
        return self.document_vector(self.embed_chunks(chunks), chunks) or []

    @staticmethod
    def hash_content(content) -> str:
        if isinstance(content, str):
            content = content.encode("utf-8")
        return hashlib.sha256(content).hexdigest()
