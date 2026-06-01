# Plagiarism Detection Algorithm

## Overview

The plagiarism detection system uses **semantic similarity analysis** at the chunk level, powered by Sentence-BERT embeddings and cosine similarity scoring. Documents are compared both within the same batch and across all previously uploaded batches using pgvector.

## Algorithm Flow

```
                    Batch Processing Pipeline
                    ========================

Phase 1: Pre-compute Embeddings (once per document)
────────────────────────────────────────────────────
Document A        Document B        Document C
    ↓                 ↓                 ↓
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Chunking │     │ Chunking │     │ Chunking │   500 chars, 50 overlap
└────┬────┘     └────┬────┘     └────┬────┘
     ↓               ↓               ↓
┌─────────┐     ┌─────────┐     ┌─────────┐
│ SBERT    │     │ SBERT    │     │ SBERT    │   Encode each chunk
│ Encode   │     │ Encode   │     │ Encode   │
└────┬────┘     └────┬────┘     └────┬────┘
     ↓               ↓               ↓
 [Cache A]       [Cache B]       [Cache C]      Stored in memory
     ↓               ↓               ↓
 doc.embedding = mean(all chunks)                Stored in DB (pgvector)


Phase 2: Pairwise Comparison (using cached embeddings)
──────────────────────────────────────────────────────
     A vs B          A vs C          B vs C
        ↓               ↓               ↓
  Vectorized cosine similarity (numpy matrix multiply)
        ↓               ↓               ↓
  Matches > 0.75    Matches > 0.75    Matches > 0.75
        ↓               ↓               ↓
  Store Comparison  Store Comparison  Store Comparison


Phase 3: Cross-Batch Search (pgvector)
───────────────────────────────────────
  For each document:
    SELECT * FROM documents
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> doc.embedding
    LIMIT 500

  → Store cross-batch matches with "cross_batch: true" flag
```

## Step-by-Step

### 1. Text Chunking

**Implementation:** `EmbeddingService.chunk_text()`

```python
chunk_size = 500  # characters
overlap = 50      # characters
```

500 chars is approximately 3-5 sentences, providing a balance between context preservation and localized match detection.

### 2. Embedding Generation (Cached)

**Model:** `sentence-transformers/all-MiniLM-L6-v2`

| Spec | Value |
|------|-------|
| Dimensions | 384 |
| Max Sequence | 256 tokens (~512 chars) |
| Memory | ~80MB |

**Key optimization:** Each document is encoded **exactly once** during Phase 1. The chunks and their embeddings are cached in `PlagiarismService._embedding_cache` and reused for all pairwise comparisons. This eliminates the previous O(N*M) re-encoding where every comparison re-ran the sentence-transformer model.

**Document-level embedding:** The chunk embeddings are averaged into a single 384-dimensional vector stored on `Document.embedding` in PostgreSQL. This enables cross-batch similarity search via pgvector.

### 3. Pairwise Comparison (Vectorized)

**Previous approach** (removed): For each chunk in doc A, iterate through every chunk in doc B using a Python loop. O(N*M) Python-level comparisons.

**Current approach:** Doc B's embeddings are stacked into a numpy matrix. Each chunk in A is compared against ALL chunks in B via a single matrix-vector multiply:

```python
matrix_b = np.array(embeddings_b)   # (M, dim)
normed_b = matrix_b / norms_b       # Normalize once

for chunk_a in embeddings_a:
    normed_a = chunk_a / norm_a
    similarities = normed_b @ normed_a  # (M,) -- all at once
    best_idx = np.argmax(similarities)
```

This reduces Python-level iterations from N*M to N, with the inner loop handled by optimized BLAS routines.

### 4. Match Detection

**Threshold:** 0.75 cosine similarity

For each chunk in Document A, the best matching chunk in Document B is identified. If the cosine similarity exceeds 0.75, it's recorded as a match with the source text, target text, and score.

### 5. Overall Score Calculation

```python
overall_score = sum(matched_chunk_scores) / total_chunks_in_A
```

| Score Range | Interpretation |
|------------|----------------|
| 0.8-1.0 | Very high plagiarism (80%+ of document matches) |
| 0.5-0.8 | Significant plagiarism |
| 0.2-0.5 | Moderate overlap |
| < 0.2 | Low/no plagiarism |

### 6. Cross-Batch Plagiarism Detection

After within-batch comparisons, each document is searched against **all previously analyzed documents** using pgvector's cosine distance operator:

```sql
SELECT d.id, d.filename, d.batch_id,
       1 - (d.embedding <=> :embedding::vector) AS similarity
FROM documents d
WHERE d.embedding IS NOT NULL
  AND d.status = 'completed'
  AND d.batch_id != :current_batch
ORDER BY d.embedding <=> :embedding::vector
LIMIT :max_docs
```

- Controlled by `MAX_CROSS_BATCH_DOCS` env var (default: 500)
- Cross-batch matches are stored in the `Comparison` table with a `cross_batch: true` flag in the matches JSON
- Uses the document-level embedding (averaged from chunk embeddings) for fast approximate search

## Performance Characteristics

### Memory

| Component | Memory |
|-----------|--------|
| Embedding model (all-MiniLM-L6-v2) | ~80MB |
| Embedding cache (per document) | ~1.5KB per chunk (384 floats * 4 bytes) |
| Typical 10-doc batch | ~150KB cache |

The embedding cache is cleared after each batch via `PlagiarismService.clear_cache()`.

### Models

The embedding model is managed by the shared `ModelManager`:
- **Lazy-loaded** on first use (not at import time)
- **Auto-unloaded** after `MODEL_UNLOAD_TIMEOUT` seconds of inactivity
- **Skipped entirely** in `LIGHTWEIGHT_MODE=true` (plagiarism detection disabled)

### Scalability

| Batch Size | Comparisons | Approx Time |
|-----------|-------------|-------------|
| 5 docs | 10 pairs | Fast |
| 20 docs | 190 pairs | Moderate |
| 50 docs | 1,225 pairs | Slow |

For very large batches, the Celery worker processes one batch at a time (`--concurrency=1`) to prevent memory exhaustion. The worker restarts after every 5 tasks (`worker_max_tasks_per_child=5`) to prevent memory leaks.

## Limitations

### False Positives
- Common technical jargon and standard academic phrasing
- Domain-specific vocabulary (legal, medical)

### False Negatives
- Synonym substitution (SBERT catches most but not all)
- Structural plagiarism (copying idea structure without copying text)
- Cross-lingual plagiarism (requires multilingual models)

### Comparison Scope
- Within-batch: all document pairs compared
- Cross-batch: document-level embedding search (less granular than chunk-level)
- Does NOT search the internet or external databases

## Output Schema

Within-batch comparison stored in `Comparison` table:
```python
{
    "doc_a": "uuid",
    "doc_b": "uuid",
    "similarity": 0.78,
    "matches": [
        {
            "source_chunk": "The quick brown fox...",
            "target_chunk": "A fast brown fox...",
            "score": 0.82,
            "source_index": 3,
            "target_index": 7
        }
    ]
}
```

Cross-batch comparison:
```python
{
    "doc_a": "uuid",
    "doc_b": "uuid-from-another-batch",
    "similarity": 0.65,
    "matches": [
        {
            "cross_batch": true,
            "source_filename": "essay_final.pdf"
        }
    ]
}
```
