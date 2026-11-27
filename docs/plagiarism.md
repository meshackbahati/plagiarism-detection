# Plagiarism Detection Algorithm

## Overview

Every document is checked two ways, and the higher result wins:

| Signal | Finds | Needs a model? | Evidence shown |
|--------|-------|----------------|----------------|
| **Word-for-word** (lexical fingerprints) | Copy-paste and lightly edited copying | No: works in `LIGHTWEIGHT_MODE` | The exact copied passage on both sides |
| **Paraphrase** (semantic embeddings) | Rewording that keeps the meaning | Yes: `all-MiniLM-L6-v2` (~80MB) | The source chunk and its closest match |

`similarity = max(word_for_word, paraphrased)`. Both are **coverage**: the share of *this* document's words that match the other document. Coverage is directional. If a 300-word essay is copied entirely into a 3,000-word report, the essay scores 100% against the report and the report scores 10% against the essay.

Code: [`fingerprint.py`](../backend/app/services/fingerprint.py), [`plagiarism.py`](../backend/app/services/plagiarism.py), [`embedding.py`](../backend/app/services/embedding.py), [`batch_processing.py`](../backend/app/services/batch_processing.py).

## Algorithm Flow

```
Upload  ->  text extracted, SHA-256 of file stored (content_hash)
Worker  ->  1. Profile each document once:
               - word 5-gram fingerprints ("shingles")
               - sentence-aligned chunks (~80 words) -> embeddings (batch-encoded)
               - document vector = word-weighted mean of chunk vectors (pgvector)
            2. Fetch earlier documents to compare against (once per batch):
               - nearest neighbours by pgvector cosine (CROSS_BATCH_CANDIDATES per doc)
               - any earlier file with the same content_hash
               - the most recent MAX_CROSS_BATCH_DOCS documents (word-for-word check)
               - identical earlier uploads are collapsed to the first one
            3. Per document: AI check, compare against every other document in the
               batch and every candidate, store matches, commit, update progress
```

## 1. Word-for-word (lexical) matching

1. Text is split into words (`\w+`, Unicode-aware, case-folded).
2. Every run of `SHINGLE_SIZE` (default 5) consecutive words is hashed.
3. Shingles of document A that also occur in B are marked. Consecutive marked shingles form a **passage**.
4. Passages shorter than `MIN_MATCH_WORDS` (default 8) are ignored, so common phrases such as "at the end of the day" do not count.
5. **Coverage** = words inside reported passages ÷ words in A.
6. Each passage is located in B (picking the occurrence that continues longest), and both snippets are stored as evidence.

## 2. Paraphrase (semantic) matching

1. Text is split into whole sentences, grouped into chunks of ~80 words. Chunks never cut a word or sentence; sentences over 160 words are split on word boundaries.
2. Chunks are encoded in batches with `normalize_embeddings=True`, so a single matrix product gives every cosine similarity: `sims = A @ B.T`.
3. A chunk counts as paraphrased when its best match in B is ≥ `SEMANTIC_MATCH_THRESHOLD` (default 0.82).
4. **Paraphrase coverage** = words in matched chunks ÷ words in A.
5. Chunks already shown as exact copies are not listed twice.

## 3. What gets stored

A `comparisons` row (doc_a → doc_b) is saved when `similarity ≥ MIN_REPORTED_SIMILARITY` (default 5%) or at least one word-for-word passage exists. Columns: `similarity`, `lexical_similarity`, `semantic_similarity` (null without a model), `cross_batch`, and `matches` (up to 60 passages). Identical files (same SHA-256) short-circuit to 100%.

Re-running a batch first deletes its old comparisons, so results never duplicate.

## Tuning

| Variable | Default | Effect |
|----------|---------|--------|
| `SHINGLE_SIZE` | `5` | Words per fingerprint. Lower = more sensitive, more noise |
| `MIN_MATCH_WORDS` | `8` | Shortest copied passage reported |
| `SEMANTIC_MATCH_THRESHOLD` | `0.82` | Cosine needed to call a chunk a paraphrase |
| `MIN_REPORTED_SIMILARITY` | `0.05` | Hide pairs below this overall score |
| `CROSS_BATCH_SCOPE` | `user` | `user` searches only the uploader's own earlier batches. `all` searches every account (a shared corpus) but shows another account's match as "Document from another account" with its text hidden |
| `CROSS_BATCH_CANDIDATES` | `20` | Nearest neighbours fetched per document from pgvector |
| `MAX_CROSS_BATCH_DOCS` | `500` | Recent earlier documents checked word-for-word |

## Limitations

- **Translation plagiarism** (copying from another language) is not detected.
- **Paraphrase detection needs the model.** `LIGHTWEIGHT_MODE` still catches copy-paste, but not rewording.
- **Shared boilerplate** (assignment questions, templates, references lists) counts as matching text. Review the passages, not just the percentage.
- **Cross-batch scope:** paraphrase checks against earlier batches only run for the pgvector nearest neighbours. Word-for-word checks run against the most recent `MAX_CROSS_BATCH_DOCS` documents.
- A high score is a reason to review a document, not proof of misconduct.

## Output Schema

`GET /api/v1/batches/{id}/results`, per document:

```json
{
  "document_id": "…",
  "filename": "submissions.zip/class/student.docx",
  "status": "completed",
  "error": null,
  "word_count": 412,
  "plagiarism_analysis": [
    {
      "document_id": "…",
      "similar_document": "source.pdf",
      "similarity": 0.375,
      "lexical_similarity": 0.375,
      "semantic_similarity": 0.31,
      "cross_batch": false,
      "matches": [
        {"type": "exact", "source_chunk": "…", "target_chunk": "…", "score": 1.0, "words": 150},
        {"type": "semantic", "source_chunk": "…", "target_chunk": "…", "score": 0.88, "words": 74}
      ]
    }
  ]
}
```
