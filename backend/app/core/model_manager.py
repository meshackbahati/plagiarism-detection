"""
Singleton model manager that lazy-loads ML models on first use and
optionally unloads them after an idle timeout to free memory.

In LIGHTWEIGHT_MODE, no local models are loaded at all - the system
relies entirely on external API providers (OpenAI/Together) for AI
detection and skips plagiarism embedding-based comparison.
"""

import os
import gc
import time
import threading
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class ModelManager:
    """
    Thread-safe singleton that manages ML model lifecycle.

    Models are loaded on first access and optionally unloaded after
    MODEL_UNLOAD_TIMEOUT seconds of inactivity.
    """

    _instance: Optional["ModelManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.lightweight_mode = settings.LIGHTWEIGHT_MODE
        self.unload_timeout = settings.MODEL_UNLOAD_TIMEOUT

        # Models (None = not loaded, False = load attempted and failed)
        self._embedding_model = None
        self._classifier = None

        # Track last access time for auto-unload
        self._embedding_last_used: float = 0
        self._ai_last_used: float = 0

        # Timer for auto-unload
        self._unload_timer: Optional[threading.Timer] = None

        if self.lightweight_mode:
            logger.info("LIGHTWEIGHT_MODE enabled - no local ML models will be loaded")

    # ── Embedding model (sentence-transformers/all-MiniLM-L6-v2, ~80MB) ──

    @property
    def embedding_model(self):
        """Get the embedding model, loading it lazily if needed."""
        if self.lightweight_mode:
            return None

        if self._embedding_model is None:
            with self._lock:
                if self._embedding_model is None:
                    self._load_embedding_model()

        self._embedding_last_used = time.time()
        self._schedule_unload_check()
        return self._embedding_model

    def _load_embedding_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model (all-MiniLM-L6-v2)...")
            self._embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            logger.info("Embedding model loaded (~80MB)")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self._embedding_model = False  # Mark as failed, don't retry

    def unload_embedding_model(self):
        """Explicitly unload the embedding model and free memory."""
        if self._embedding_model and self._embedding_model is not False:
            logger.info("Unloading embedding model to free memory")
            self._embedding_model = None
            gc.collect()

    # ── AI classifier (roberta-base-openai-detector, ~500MB) ──

    @property
    def ai_classifier(self):
        """Get the AI classifier, loading it lazily if needed."""
        if self.lightweight_mode:
            return None

        if self._classifier is None:
            with self._lock:
                if self._classifier is None:
                    self._load_ai_classifier()

        self._ai_last_used = time.time()
        self._schedule_unload_check()
        return self._classifier

    def _load_ai_classifier(self):
        try:
            from transformers import pipeline
            logger.info("Loading AI classifier (roberta-base-openai-detector)...")
            self._classifier = pipeline(
                "text-classification",
                model="roberta-base-openai-detector",
            )
            logger.info("AI classifier loaded (~500MB)")
        except Exception as e:
            logger.error(f"Failed to load AI classifier: {e}")
            self._classifier = False

    def unload_ai_classifier(self):
        """Explicitly unload the AI classifier and free memory."""
        if self._classifier and self._classifier is not False:
            logger.info("Unloading AI classifier to free memory")
            self._classifier = None
            gc.collect()

    # ── Auto-unload after idle timeout ──

    def _schedule_unload_check(self):
        """Schedule a check to unload idle models after timeout."""
        if self.unload_timeout <= 0:
            return  # Auto-unload disabled

        # Cancel existing timer
        if self._unload_timer is not None:
            self._unload_timer.cancel()

        self._unload_timer = threading.Timer(
            self.unload_timeout, self._check_and_unload_idle
        )
        self._unload_timer.daemon = True
        self._unload_timer.start()

    def _check_and_unload_idle(self):
        """Unload models that have been idle longer than the timeout."""
        now = time.time()
        unloaded_any = False

        if (
            self._embedding_model
            and self._embedding_model is not False
            and self._embedding_last_used > 0
            and (now - self._embedding_last_used) > self.unload_timeout
        ):
            self.unload_embedding_model()
            unloaded_any = True

        if (
            self._classifier
            and self._classifier is not False
            and self._ai_last_used > 0
            and (now - self._ai_last_used) > self.unload_timeout
        ):
            self.unload_ai_classifier()
            unloaded_any = True

        if unloaded_any:
            logger.info("Idle models unloaded to free memory")

    # ── Helpers ──

    def unload_all(self):
        """Unload all models immediately."""
        self.unload_embedding_model()
        self.unload_ai_classifier()

    def status(self) -> dict:
        """Return current model status."""
        return {
            "lightweight_mode": self.lightweight_mode,
            "embedding_model": (
                "not_loaded" if self._embedding_model is None
                else "failed" if self._embedding_model is False
                else "loaded"
            ),
            "ai_classifier": (
                "not_loaded" if self._classifier is None
                else "failed" if self._classifier is False
                else "loaded"
            ),
        }


# Module-level singleton
model_manager = ModelManager()
