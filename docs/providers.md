# Provider Comparison Guide

## Overview

The system supports multiple AI detection approaches. This document compares them to help you choose the right configuration for your use case.

## Quick Comparison

| Feature | Statistical Heuristics | Local Model | OpenAI API | Together API |
|---------|----------------------|------------|------------|--------------|
| **Privacy** | Full | Full | Data sent externally | Data sent externally |
| **Cost** | Free | Free | ~$0.00015/request | ~$0.001/request |
| **Speed** | Instant | Fast (local) | Network-dependent | Network-dependent |
| **RAM Required** | None | ~500MB | None | None |
| **Accuracy** | Basic (~70%) | Good (~85%) | Good (~90%) | Good (~88%) |
| **Setup** | Zero config | Zero config | API key required | API key required |
| **Reliability** | Always available | Model-dependent | API-dependent | API-dependent |

## Detection Approaches

### Statistical Heuristics (Built-In, Always Available)

**Not a provider** -- this runs alongside every detection method as a baseline signal.

**Signals analyzed:**
- Burstiness (sentence length variance)
- Vocabulary diversity (type-token ratio)
- Sentence length uniformity
- Word frequency distribution (Zipf's law)

**Characteristics:**
- Zero dependencies, runs on any machine
- No model download required
- Works in `LIGHTWEIGHT_MODE=true`
- Less accurate than ML models alone
- Blended with other signals: 30% weight for local detection, 25% for external APIs

### Local Model (Recommended Default)

**Model:** `roberta-base-openai-detector` (~500MB)

**How it works:**
- Chunks text into 512-character segments (max 20)
- Classifies each chunk as "Real" (human) or "Fake" (AI)
- Averages chunk scores, blends with heuristics (70% model / 30% heuristic)
- Model auto-unloads after idle timeout to free memory

**Pros:**
- Full privacy -- text never leaves your server
- No API costs, no rate limits
- Works offline

**Cons:**
- ~500MB RAM required
- Trained on GPT-2/early GPT-3 outputs (may underperform on newer models)
- First request triggers model download/loading

**Best for:** Privacy-sensitive environments, high-volume processing, offline systems

**Configuration:**
```bash
# Default -- no configuration needed
LIGHTWEIGHT_MODE=false
```

### OpenAI API

**Model:** `gpt-4o-mini`

**How it works:**
- Sends text with a structural analysis prompt
- Model evaluates uniformity, predictability, and formality
- Score blended 75% API + 25% local heuristics

**Pros:**
- Higher accuracy on modern AI text
- Minimal local resources
- Always benefits from model improvements

**Cons:**
- Text sent to OpenAI servers
- API costs per request
- Requires internet and API key

**Estimated costs (gpt-4o-mini):**
- 100 docs/day: ~$0.45/month
- 1,000 docs/day: ~$4.50/month
- 10,000 docs/day: ~$45/month

**Configuration:**
```bash
OPENAI_API_KEY=sk-your-key-here
```

### Together API

**Model:** `mistralai/Mixtral-8x7B-Instruct-v0.1`

**How it works:** Same structural analysis approach as OpenAI, using Mixtral via Together's platform.

**Pros:**
- Open-source model (transparent architecture)
- Lower cost than OpenAI
- Good accuracy

**Cons:**
- Text sent to Together AI servers
- Requires internet and API key
- Less established provider

**Configuration:**
```bash
TOGETHER_API_KEY=your-together-key-here
```

## Choosing a Configuration

### Decision Guide

```
Is privacy required?
  YES → Local Model (default)
  NO  → Is budget constrained?
         YES → Together API
         NO  → OpenAI API (highest accuracy)

Is the machine low-resource (<4GB RAM)?
  YES → LIGHTWEIGHT_MODE=true + external API key
  NO  → Default (local model + heuristics)
```

### Recommended Configurations

#### Low-Resource Machine (VPS, Raspberry Pi, etc.)
```bash
LIGHTWEIGHT_MODE=true
OPENAI_API_KEY=sk-your-key   # Optional: for ML-based detection
```
- No ML models loaded (~580MB saved)
- Statistical heuristics handle local detection
- External API available for higher accuracy when needed

#### Privacy-First (Air-Gapped, GDPR, FERPA)
```bash
LIGHTWEIGHT_MODE=false
# No API keys configured
```
- Full local processing
- No data leaves the server
- ML model + heuristics combined

#### Maximum Accuracy
```bash
LIGHTWEIGHT_MODE=false
OPENAI_API_KEY=sk-your-key
```
- Local model for initial screening
- OpenAI available for uncertain cases
- Heuristics as additional signal layer

#### High-Volume / Cost-Constrained
```bash
LIGHTWEIGHT_MODE=false
TOGETHER_API_KEY=your-key
```
- Local model handles most documents
- Together API for edge cases
- Lower API costs than OpenAI

## Model Lifecycle Management

The local ML models are managed by a shared `ModelManager` singleton:

| Setting | Default | Description |
|---------|---------|-------------|
| `LIGHTWEIGHT_MODE` | `false` | Skip loading all local models |
| `MODEL_UNLOAD_TIMEOUT` | `300` | Seconds idle before auto-unload |

**Memory usage:**
- Embedding model (sentence-transformers): ~80MB
- AI classifier (roberta): ~500MB
- Total when both loaded: ~580MB

**Auto-unload behavior:**
- After `MODEL_UNLOAD_TIMEOUT` seconds without a detection request, models are unloaded from memory
- `gc.collect()` runs to release RAM
- Models reload automatically on next request
- Set to `0` to disable auto-unload (models stay in memory permanently)

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Local model fails to load | Falls back to heuristics-only with warning in response |
| API key missing | Returns explicit error: "OPENAI_API_KEY is not set" |
| API rate limited | Returns error with retry suggestion |
| Text too short (< 10 words) | Returns 400 error: insufficient text |
| `LIGHTWEIGHT_MODE=true` + no API key | Heuristics-only detection (less reliable) |
