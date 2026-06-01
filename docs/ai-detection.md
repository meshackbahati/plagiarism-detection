# AI-Generated Content Detection

## Overview

The AI detection system uses a hybrid approach combining three signal sources:

1. **Local ML Model** -- HuggingFace `roberta-base-openai-detector` classifier
2. **Statistical Heuristics** -- Zero-dependency text analysis (burstiness, vocabulary, uniformity)
3. **External Providers** -- OpenAI/Together APIs for supplementary analysis

In **Lightweight Mode**, only statistical heuristics run locally (no model loaded). External providers remain available regardless of mode.

## Detection Methods

### Statistical Heuristics (Always Available)

These heuristics require no ML model and run on any machine. They analyze statistical patterns that correlate with AI-generated text:

**Burstiness** (weight: 35%):
- Measures sentence length variance (coefficient of variation)
- Human text is "bursty" -- short punchy sentences mixed with long ones (CV > 0.6)
- AI text tends toward uniform sentence lengths (CV < 0.4)

**Vocabulary Diversity** (weight: 25%):
- Type-token ratio (unique words / total words)
- AI text typically falls in a narrow TTR range (0.35-0.50)
- Human text varies more widely (very high or very low TTR)

**Sentence Length Uniformity** (weight: 20%):
- Percentage of sentences in the 12-28 word "AI-typical" range
- AI sentences cluster around 15-25 words
- Human writing has more variation

**Word Frequency Distribution** (weight: 20%):
- Top-10 most common words ratio (Zipf's law analysis)
- AI text tends to have higher repetition of function words

### Local Model (Default)

**Model:** `roberta-base-openai-detector`

**Architecture:**
- Base: RoBERTa (125M parameters)
- Training: Fine-tuned on GPT-2/GPT-3 outputs
- Output: Binary classification (Real/Fake)
- Memory: ~500MB

**Scoring:**
When the model is available, the final score blends:
- **70%** model output (chunked inference, max 20 chunks of 512 chars)
- **30%** statistical heuristics

When the model is unavailable (lightweight mode or load failure):
- **100%** statistical heuristics with a lower confidence indicator

**Inference Process:**
1. Chunk text into 512-character segments (max 20 chunks)
2. Run each chunk through classifier
3. Aggregate scores: `Fake` label uses score directly, `Real` label inverts it
4. Average all chunk scores for model score
5. Blend with heuristic score (70/30 weighting)

**Model Lifecycle:**
- Loaded lazily on first use via the shared `ModelManager`
- Auto-unloaded after `MODEL_UNLOAD_TIMEOUT` seconds of inactivity (default: 300s)
- Skipped entirely in `LIGHTWEIGHT_MODE=true`

### External Providers

#### OpenAI API

**Model:** `gpt-4o-mini`

**Process:** Text is sent with a structural analysis prompt asking the model to evaluate uniformity, predictability, and formality patterns. The API score is then blended 75% API + 25% local heuristics.

**Cost:** ~$0.00015 per request (gpt-4o-mini pricing)

#### Together API

**Model:** `mistralai/Mixtral-8x7B-Instruct-v0.1`

**Process:** Same structural analysis approach as OpenAI. Score blended with local heuristics.

## Output Schema

```json
{
  "is_ai": true,
  "score": 0.82,
  "confidence": 0.64,
  "label": "Likely AI",
  "provider": "local",
  "details": {
    "model": "roberta-base-openai-detector",
    "model_score": 0.88,
    "heuristic_score": 0.68,
    "chunks_analyzed": 5,
    "statistics": {
      "burstiness_cv": 0.312,
      "burstiness_score": 0.688,
      "vocabulary_ttr": 0.421,
      "vocab_score": 0.65,
      "sentence_uniformity": 0.733,
      "uniformity_score": 0.88,
      "top10_word_ratio": 0.218,
      "zipf_score": 0.5
    }
  }
}
```

In lightweight mode (model unavailable), the output includes a warning:
```json
{
  "label": "Possibly AI (heuristic only)",
  "details": {
    "model": "unavailable",
    "warning": "Local ML model not loaded. Results are heuristic-only and less reliable."
  }
}
```

## Confidence Calculation

```python
confidence = abs(score - 0.5) * 2
```

| Score | Confidence | Interpretation |
|-------|-----------|----------------|
| 0.9 | 0.8 | High confidence AI |
| 0.51 | 0.02 | Inconclusive |
| 0.1 | 0.8 | High confidence Human |

**Guidelines:**
- `> 0.7` -- High confidence
- `0.3-0.7` -- Moderate confidence
- `< 0.3` -- Low confidence (inconclusive)

## Known Limitations

### High False Positive Risk

**ESL Writers:** Non-native English often triggers AI detection due to simpler sentence structure and limited vocabulary.

**Formal Writing:** Academic templates and technical documentation naturally resemble AI output.

**Mitigation:** Use confidence scores (not binary labels). Always require human review for high-stakes decisions.

### Model Limitations

**Training Data Bias:** The local model was trained on GPT-2/early GPT-3 outputs. It may underperform on GPT-4, Claude, and newer models.

**Adversarial Attacks:** Minor edits, paraphrasing tools, and deliberate style changes can bypass detection. No detector is foolproof.

### Heuristic Limitations

Statistical heuristics are pattern-based and can be fooled by:
- Deliberately varying sentence lengths
- Using domain-specific jargon (lowers TTR artificially)
- Short texts (insufficient data for reliable statistics)

## Best Practices

### For Educators
1. Use as a screening tool only -- red flags, not verdicts
2. Review low-confidence cases manually
3. Consider student context (prior work, assignment type)

### For Administrators
1. Inform users that detection is probabilistic
2. Implement an appeals process with manual review
3. Track false positive/negative rates over time

## Ethical Considerations

**Academic Integrity:** Tools are assistive, not definitive. Human judgment is irreplaceable.

**Documented Biases:** Non-native speakers, neurodivergent writers, and certain dialects are disproportionately flagged.

**Privacy:** Local models preferred. External APIs are opt-in only with clear user consent.
