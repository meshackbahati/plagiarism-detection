import os
import hashlib
from typing import List, Tuple

from app.core.model_manager import model_manager


class EmbeddingService:
    """
    Text embedding service using sentence-transformers.

    Delegates model loading to the shared ModelManager singleton so the
    ~80MB model is only loaded once per process, regardless of how many
    EmbeddingService instances exist.
    """

    def __init__(self):
        # Use the shared model manager - no direct model loading
        self._manager = model_manager

    @property
    def model(self):
        """Access the embedding model via the manager (lazy-loaded)."""
        return self._manager.embedding_model

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Split text into overlapping chunks."""
        if not text:
            return []
        chunks = []
        step = chunk_size - overlap
        for i in range(0, len(text), step):
            chunks.append(text[i:i + chunk_size])
            if i + chunk_size >= len(text):
                break
        return chunks

    def encode_chunks(self, text: str) -> Tuple[List[str], list]:
        """
        Generate embeddings for each chunk of text.
        Returns (chunks, embeddings) where embeddings is a list of numpy arrays.
        """
        if not self.model:
            return [], []

        chunks = self.chunk_text(text)
        if not chunks:
            return [], []

        embeddings = [self.model.encode(chunk) for chunk in chunks]
        return chunks, embeddings

    def generate_text_embedding(self, text: str) -> list:
        """Generate a single document-level embedding by averaging chunk embeddings."""
        if not self.model:
            return []

        chunks, embeddings = self.encode_chunks(text)
        if not embeddings:
            return []

        import numpy as np
        avg_embedding = np.mean(embeddings, axis=0)
        return avg_embedding.tolist()

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()
