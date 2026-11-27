from app.services.embedding import chunk_text
from app.services.fingerprint import build_fingerprint, compare_fingerprints
from app.services.plagiarism import PlagiarismService
from tests.helpers import essay


def test_copied_passage_found_with_evidence():
    source = essay(1, 400)
    copied = " ".join(source.split()[100:180])
    student = essay(2, 200) + " " + copied + " " + essay(3, 120)
    res = compare_fingerprints(build_fingerprint(student), build_fingerprint(source))
    assert res["passages"], "expected at least one copied passage"
    top = res["passages"][0]
    assert top["words"] >= 75
    assert top["source_chunk"].split()[:5] == top["target_chunk"].split()[:5]
    # ~80 of ~400 words copied.
    assert 0.15 < res["coverage"] < 0.3


def test_unrelated_documents_score_low():
    a = "The committee reviewed the annual budget and approved new funding for rural schools."
    b = "Volcanic soils retain moisture well, which helps coffee plants survive long dry seasons."
    res = compare_fingerprints(build_fingerprint(a * 3), build_fingerprint(b * 3))
    assert res["coverage"] == 0.0


def test_coverage_is_directional():
    long_doc = essay(4, 600)
    short_doc = " ".join(long_doc.split()[:100])
    short_in_long = compare_fingerprints(build_fingerprint(short_doc), build_fingerprint(long_doc))
    long_in_short = compare_fingerprints(build_fingerprint(long_doc), build_fingerprint(short_doc))
    assert short_in_long["coverage"] == 1.0
    assert long_in_short["coverage"] < 0.2


def test_short_common_phrases_ignored():
    a = "in the end of the day we went home and slept for hours afterwards quietly"
    b = "they said that at the end of the day nothing really mattered to anyone"
    res = compare_fingerprints(build_fingerprint(a), build_fingerprint(b), k=5, min_match_words=8)
    assert res["passages"] == []


def test_service_compare_lightweight_and_identical_hash():
    svc = PlagiarismService(use_embeddings=False)
    text = essay(5, 300)
    a = svc.profile("a", text, "a.txt", content_hash="h1")
    b = svc.profile("b", text, "b.txt", content_hash="h1")
    res = svc.compare(a, b)
    assert res["similarity"] == 1.0 and res["semantic_similarity"] is None
    c = svc.profile("c", essay(6, 300), "c.txt")
    assert not svc.is_reportable(svc.compare(a, c))


def test_chunk_text_keeps_sentences_whole():
    text = "First sentence is here. Second one follows! Is this the third? " * 30
    chunks = chunk_text(text, target_words=40)
    assert len(chunks) > 1
    for ch in chunks:
        assert ch.text.endswith(("." , "!", "?"))
        assert text[ch.start:ch.end].strip() == ch.text
