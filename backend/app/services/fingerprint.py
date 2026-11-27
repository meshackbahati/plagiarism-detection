"""
Lexical fingerprinting for copy detection (no ML model needed).

Each document is split into overlapping word n-grams ("shingles"). Two
documents share a shingle when they contain the same run of k words, so
runs of shared shingles are copied passages. This catches verbatim and
lightly-edited copying precisely, works in LIGHTWEIGHT_MODE, and gives
exact evidence (the copied text on both sides) instead of only a score.

The score is *coverage*: the share of document A's words that sit inside a
copied passage of at least `min_match_words` words found in document B.
Coverage is directional on purpose: a short essay fully copied into a long
report is 100% copied, while the report is only partly copied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

_WORD_RE = re.compile(r"\w+", re.UNICODE)
MAX_PASSAGES = 50
MAX_SNIPPET_CHARS = 700


@dataclass
class Fingerprint:
    text: str
    spans: List[Tuple[int, int]]  # char (start, end) of each word
    hashes: List[int]  # hash of the shingle starting at word i
    positions: Dict[int, List[int]] = field(default_factory=dict)  # hash -> word indexes

    @property
    def word_count(self) -> int:
        return len(self.spans)


def build_fingerprint(text: str, k: int = 5) -> Fingerprint:
    spans: List[Tuple[int, int]] = []
    words: List[str] = []
    for m in _WORD_RE.finditer(text or ""):
        spans.append((m.start(), m.end()))
        words.append(m.group().casefold())

    # hash() of a tuple of str is stable within one process, which is all we
    # need: fingerprints are rebuilt per run and never persisted.
    hashes = [hash(tuple(words[i:i + k])) for i in range(max(0, len(words) - k + 1))]
    positions: Dict[int, List[int]] = {}
    for i, h in enumerate(hashes):
        positions.setdefault(h, []).append(i)
    return Fingerprint(text=text or "", spans=spans, hashes=hashes, positions=positions)


def _snippet(fp: Fingerprint, start_word: int, end_word: int) -> str:
    start = fp.spans[start_word][0]
    end = fp.spans[min(end_word, len(fp.spans) - 1)][1]
    snippet = fp.text[start:end].replace("\n", " ")
    if len(snippet) > MAX_SNIPPET_CHARS:
        snippet = snippet[:MAX_SNIPPET_CHARS].rsplit(" ", 1)[0] + " …"
    return snippet


def compare_fingerprints(
    a: Fingerprint,
    b: Fingerprint,
    k: int = 5,
    min_match_words: int = 8,
) -> Dict:
    """
    Find passages of `a` that also appear in `b`.

    Returns {"coverage": float 0..1, "matched_words": int, "passages": [...]},
    each passage holding the source/target snippets and char offsets.
    """
    if not a.hashes or not b.positions:
        return {"coverage": 0.0, "matched_words": 0, "passages": []}

    b_positions = b.positions
    matched = [h in b_positions for h in a.hashes]

    # Group consecutive matching shingles in A into runs.
    runs: List[Tuple[int, int]] = []  # (first shingle idx, last shingle idx)
    i, n = 0, len(matched)
    while i < n:
        if not matched[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and matched[j + 1]:
            j += 1
        runs.append((i, j))
        i = j + 1

    passages = []
    covered = 0
    for first, last in runs:
        start_word, end_word = first, last + k - 1  # inclusive word range in A
        length = end_word - start_word + 1
        if length < min_match_words:
            continue
        covered += length

        # Locate the passage in B: the occurrence of the run's first shingle
        # that continues the longest, so repeated phrases map sensibly.
        best_b, best_len = b_positions[a.hashes[first]][0], 0
        for cand in b_positions[a.hashes[first]][:20]:
            run_len = 0
            while (
                first + run_len <= last
                and cand + run_len < len(b.hashes)
                and b.hashes[cand + run_len] == a.hashes[first + run_len]
            ):
                run_len += 1
            if run_len > best_len:
                best_b, best_len = cand, run_len
        b_end = min(best_b + length - 1, len(b.spans) - 1)

        passages.append({
            "type": "exact",
            "source_chunk": _snippet(a, start_word, end_word),
            "target_chunk": _snippet(b, best_b, b_end),
            "score": 1.0 if best_len == last - first + 1 else round(best_len / (last - first + 1), 4),
            "words": length,
            "source_span": [a.spans[start_word][0], a.spans[end_word][1]],
            "target_span": [b.spans[best_b][0], b.spans[b_end][1]],
        })

    coverage = covered / a.word_count if a.word_count else 0.0
    passages.sort(key=lambda p: p["words"], reverse=True)
    return {
        "coverage": round(min(1.0, coverage), 4),
        "matched_words": covered,
        "passages": passages[:MAX_PASSAGES],
    }
