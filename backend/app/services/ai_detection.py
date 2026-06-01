import os
import re
import json
import math
import logging
from typing import Dict, Any, Optional
from collections import Counter

from app.core.provider_router import ProviderRouter, ProviderType
from app.core.model_manager import model_manager

logger = logging.getLogger(__name__)


class AIDetectionService:
    """
    AI-generated text detection.

    Combines three signal sources:
    1. Local model (roberta-base-openai-detector) - HuggingFace classifier
    2. Statistical heuristics - perplexity proxy + burstiness analysis
    3. External providers (OpenAI/Together) - used as supplementary signal

    In LIGHTWEIGHT_MODE, only statistical heuristics are used locally.
    External providers remain available regardless.
    """

    def __init__(self):
        self.router = ProviderRouter()
        self._manager = model_manager

    @property
    def classifier(self):
        """Access the AI classifier via the shared model manager."""
        return self._manager.ai_classifier

    def detect(self, text: str, provider: str = ProviderType.LOCAL, threshold: float = 0.5) -> Dict[str, Any]:
        """
        Detect if text is AI-generated.

        For 'local' provider, combines model output (if available) with
        statistical heuristics for a more robust score.
        """
        try:
            validated_provider = self.router.validate_provider(provider)
            self.router.log_usage(validated_provider, "ai_detection", {"text_length": len(text)})

            if validated_provider == ProviderType.LOCAL:
                return self._detect_local(text, threshold)
            elif validated_provider in (ProviderType.OPENAI, ProviderType.TOGETHER):
                return self._detect_external(text, validated_provider, threshold)

        except ValueError as e:
            logger.error(f"Provider validation failed: {e}")
            return self._error_response(str(e))
        except Exception as e:
            logger.exception(f"AI detection failed: {e}")
            return self._error_response(f"Internal error: {str(e)}")

    def health_check(self) -> Dict[str, Any]:
        """Check if the AI detection service is operational."""
        model_status = self._manager.status()
        return {
            "status": "healthy" if (self.classifier is not None or model_status["lightweight_mode"]) else "limited",
            "local_model_loaded": model_status["ai_classifier"] == "loaded",
            "lightweight_mode": model_status["lightweight_mode"],
            "statistical_heuristics": True,  # Always available
            "external_providers": {
                "openai": self.router.openai_api_key is not None,
                "together": self.router.together_api_key is not None,
            },
        }

    # ── Local detection: model + statistical heuristics ──

    def _detect_local(self, text: str, threshold: float) -> Dict[str, Any]:
        """Run local detection combining model output with statistical analysis."""
        # Statistical heuristics are always available
        stats = self._statistical_analysis(text)

        model_result = self._run_model(text)

        if model_result is not None:
            # Combine model score (70% weight) with heuristics (30% weight)
            combined_score = (model_result["score"] * 0.7) + (stats["score"] * 0.3)
            is_ai = combined_score > threshold
            confidence = abs(combined_score - 0.5) * 2

            return {
                "is_ai": is_ai,
                "score": round(combined_score, 4),
                "confidence": round(confidence, 4),
                "label": "Likely AI" if is_ai else "Likely Human",
                "provider": ProviderType.LOCAL,
                "details": {
                    "model": "roberta-base-openai-detector",
                    "model_score": model_result["score"],
                    "heuristic_score": stats["score"],
                    "chunks_analyzed": model_result.get("chunks_analyzed", 0),
                    "statistics": stats["breakdown"],
                },
            }
        else:
            # Model unavailable - use heuristics alone (less reliable, noted in label)
            is_ai = stats["score"] > threshold
            confidence = abs(stats["score"] - 0.5) * 2

            return {
                "is_ai": is_ai,
                "score": round(stats["score"], 4),
                "confidence": round(confidence * 0.7, 4),  # Lower confidence without model
                "label": "Possibly AI (heuristic only)" if is_ai else "Likely Human (heuristic only)",
                "provider": ProviderType.LOCAL,
                "details": {
                    "model": "unavailable",
                    "heuristic_score": stats["score"],
                    "statistics": stats["breakdown"],
                    "warning": "Local ML model not loaded. Results are heuristic-only and less reliable.",
                },
            }

    def _run_model(self, text: str) -> Optional[Dict[str, Any]]:
        """Run the HuggingFace classifier. Returns None if model unavailable."""
        if not self.classifier:
            return None

        chunk_size = 512
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        chunks = chunks[:20]  # Cap to prevent OOM on massive files

        results = []
        try:
            for chunk in chunks:
                res = self.classifier(chunk[:512])[0]
                results.append(res)
        except Exception as e:
            logger.error(f"Model inference failed: {e}")
            return None

        if not results:
            return None

        # Model returns label='Fake' (AI) or 'Real' (Human)
        ai_probs = []
        for res in results:
            score = res["score"]
            if res["label"] == "Fake":
                ai_probs.append(score)
            else:
                ai_probs.append(1 - score)

        avg_score = sum(ai_probs) / len(ai_probs)
        return {"score": avg_score, "chunks_analyzed": len(results)}

    # ── Statistical heuristics ──

    def _statistical_analysis(self, text: str) -> Dict[str, Any]:
        """
        Analyze text using statistical heuristics that correlate with
        AI-generated content. No ML model required.

        Signals:
        - Burstiness: AI text tends to have uniform sentence lengths.
          Human text has high variance (short punchy sentences mixed with long ones).
        - Vocabulary diversity: AI tends to use a narrower, more 'average' vocabulary.
        - Sentence length uniformity: AI sentences cluster around 15-25 words.
        - Paragraph regularity: AI paragraphs tend to be similar lengths.
        """
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        words = text.split()

        if len(sentences) < 3 or len(words) < 20:
            return {"score": 0.5, "breakdown": {"insufficient_data": True}}

        breakdown = {}
        scores = []

        # 1. Burstiness (sentence length variance)
        sentence_lengths = [len(s.split()) for s in sentences]
        mean_len = sum(sentence_lengths) / len(sentence_lengths)
        variance = sum((l - mean_len) ** 2 for l in sentence_lengths) / len(sentence_lengths)
        std_dev = math.sqrt(variance)
        # Low std_dev relative to mean = more AI-like
        cv = std_dev / mean_len if mean_len > 0 else 0  # coefficient of variation
        # Human text typically has CV > 0.6, AI text often < 0.4
        burstiness_score = max(0, min(1, 1.0 - (cv / 1.0)))
        breakdown["burstiness_cv"] = round(cv, 3)
        breakdown["burstiness_score"] = round(burstiness_score, 3)
        scores.append(("burstiness", burstiness_score, 0.35))

        # 2. Vocabulary diversity (type-token ratio)
        lower_words = [w.lower() for w in words]
        unique_words = len(set(lower_words))
        ttr = unique_words / len(lower_words) if lower_words else 0
        # AI text tends to have moderate TTR (0.3-0.5), human text varies more
        # Very high TTR (>0.7) or very low (<0.2) suggests human
        if ttr > 0.6 or ttr < 0.2:
            vocab_score = 0.3  # Likely human
        elif 0.35 <= ttr <= 0.50:
            vocab_score = 0.65  # AI-typical range
        else:
            vocab_score = 0.5  # Ambiguous
        breakdown["vocabulary_ttr"] = round(ttr, 3)
        breakdown["vocab_score"] = round(vocab_score, 3)
        scores.append(("vocabulary", vocab_score, 0.25))

        # 3. Sentence length uniformity
        # Count what % of sentences fall in the 15-25 word "AI-typical" range
        ai_typical_range = sum(1 for l in sentence_lengths if 12 <= l <= 28)
        uniformity_ratio = ai_typical_range / len(sentence_lengths)
        # Higher ratio = more AI-like
        uniformity_score = min(1.0, uniformity_ratio * 1.2)
        breakdown["sentence_uniformity"] = round(uniformity_ratio, 3)
        breakdown["uniformity_score"] = round(uniformity_score, 3)
        scores.append(("uniformity", uniformity_score, 0.20))

        # 4. Word frequency distribution (Zipf's law deviation)
        word_freq = Counter(lower_words)
        top_10_freq = sum(count for _, count in word_freq.most_common(10))
        top_10_ratio = top_10_freq / len(lower_words) if lower_words else 0
        # AI text tends to have slightly higher top-10 ratio (more repetitive function words)
        if top_10_ratio > 0.25:
            zipf_score = 0.6  # Slightly AI-like
        elif top_10_ratio < 0.15:
            zipf_score = 0.35  # More human-like diversity
        else:
            zipf_score = 0.5
        breakdown["top10_word_ratio"] = round(top_10_ratio, 3)
        breakdown["zipf_score"] = round(zipf_score, 3)
        scores.append(("zipf", zipf_score, 0.20))

        # Weighted average
        combined = sum(score * weight for _, score, weight in scores)
        total_weight = sum(weight for _, _, weight in scores)
        final_score = combined / total_weight if total_weight > 0 else 0.5

        return {"score": round(final_score, 4), "breakdown": breakdown}

    # ── External provider detection ──

    def _detect_external(self, text: str, provider: str, threshold: float) -> Dict[str, Any]:
        """Run detection using OpenAI or Together API."""
        from openai import OpenAI

        api_key = self.router.get_api_key(provider)
        base_url = None
        model = "gpt-4o-mini"  # More cost-effective than gpt-3.5-turbo

        if provider == ProviderType.TOGETHER:
            base_url = "https://api.together.xyz/v1"
            model = "mistralai/Mixtral-8x7B-Instruct-v0.1"

        client = OpenAI(api_key=api_key, base_url=base_url)

        # Use perplexity estimation instead of asking the model to self-classify.
        # Ask the model to rate predictability of each sentence continuation.
        sample_text = text[:3000]

        prompt = f"""You are a text analysis tool. Analyze the following text and estimate
how likely it is to be AI-generated based on these criteria:
- Uniformity of sentence structure and length
- Lack of colloquialisms, typos, or informal language
- Overly balanced paragraph structure
- Predictable word choices

Respond ONLY with a JSON object: {{"score": <float 0.0-1.0 where 0=human and 1=AI>, "reasoning": "<brief explanation>"}}

Text to analyze:
{sample_text}"""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert text analysis system. Output valid JSON only. Be calibrated: 0.5 means uncertain."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            ai_score = float(result.get("score", 0.5))
            # Blend with local heuristics for robustness
            stats = self._statistical_analysis(text)
            blended = (ai_score * 0.75) + (stats["score"] * 0.25)

            is_ai = blended > threshold
            confidence = abs(blended - 0.5) * 2

            return {
                "is_ai": is_ai,
                "score": round(blended, 4),
                "confidence": round(confidence, 4),
                "label": "Likely AI" if is_ai else "Likely Human",
                "provider": provider,
                "details": {
                    "api_score": round(ai_score, 4),
                    "heuristic_score": stats["score"],
                    "reasoning": result.get("reasoning", ""),
                    "model": model,
                },
            }

        except Exception as e:
            logger.error(f"External API error ({provider}): {e}")
            return self._error_response(f"External provider error: {str(e)}")

    def _error_response(self, message: str) -> Dict[str, Any]:
        return {
            "is_ai": False,
            "score": 0.0,
            "confidence": 0.0,
            "label": "Error",
            "provider": "unknown",
            "details": {"error": message},
        }
