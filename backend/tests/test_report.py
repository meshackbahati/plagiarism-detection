import uuid
from types import SimpleNamespace

from app.services.report import ReportService


def _doc(name, **kw):
    base = dict(id=uuid.uuid4(), filename=name, status="completed", error=None, word_count=120,
                ai_score=0.42, is_ai_generated=False, ai_label="Likely Human", ai_provider="local")
    base.update(kw)
    return SimpleNamespace(**base)


def _comp(sim, cross=False):
    return SimpleNamespace(similarity=sim, lexical_similarity=sim, semantic_similarity=None, cross_batch=cross,
                           matches=[{"type": "exact", "source_chunk": "copied <text> & more", "target_chunk": "x", "score": 1.0}])


def test_pdf_handles_special_characters_and_long_names():
    batch = SimpleNamespace(id=uuid.uuid4(), name="R&D <final>", status="completed", analysis_type="both")
    a = _doc("Smith & Jones <draft> " + "x" * 200 + ".pdf")
    b = _doc("broken.pdf", status="failed", error="This PDF is password-protected.")
    pdf = ReportService.generate_pdf_report(batch, [a, b], {a.id: [(_comp(0.6), "other & co.docx")], b.id: []})
    assert pdf.startswith(b"%PDF")


def test_csv_blocks_formula_injection():
    batch = SimpleNamespace(id=uuid.uuid4(), name="b", status="completed", analysis_type="plagiarism")
    d = _doc("=HYPERLINK(\"http://evil\").txt")
    csv_text = ReportService.generate_csv_report(batch, [d], {d.id: [(_comp(0.3, cross=True), "+cmd.txt")]})
    assert "'=HYPERLINK" in csv_text and "'+cmd.txt" in csv_text
    assert "AI Score" not in csv_text.splitlines()[0]
