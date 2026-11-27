import shutil

import pytest

from app.services.parsing import ExtractionError, extract_text_from_bytes, normalize_text
from tests.helpers import make_docx, make_image_pdf, make_pdf


def test_text_utf8_and_bom():
    assert extract_text_from_bytes("héllo wörld".encode("utf-8"), "a.txt").text == "héllo wörld"
    assert extract_text_from_bytes(b"\xef\xbb\xbfhello", "a.txt").text == "hello"
    assert extract_text_from_bytes("hello".encode("utf-16"), "a.txt").text == "hello"


def test_text_cp1252_fallback():
    assert extract_text_from_bytes("café – naïve".encode("cp1252"), "a.txt").text == "café – naïve"


def test_nul_bytes_removed():
    # PostgreSQL TEXT rejects \x00; it must never reach the database.
    assert "\x00" not in extract_text_from_bytes(b"abc\x00def ghi", "a.txt").text


def test_normalize_ligatures_and_hyphenation():
    assert normalize_text("ﬁnal exam-\nple   text") == "final example text"


def test_empty_file_rejected():
    with pytest.raises(ExtractionError):
        extract_text_from_bytes(b"", "a.txt")
    with pytest.raises(ExtractionError):
        extract_text_from_bytes(b"   \n  ", "a.txt")


def test_docx_paragraphs_and_tables():
    content = make_docx(["Intro paragraph here.", "Second paragraph."], [["Name", "Score"], ["Alice", "90"]])
    result = extract_text_from_bytes(content, "essay.docx")
    assert "Intro paragraph here." in result.text
    assert "Alice | 90" in result.text
    assert result.text.index("Second paragraph") < result.text.index("Alice")


def test_bad_docx():
    with pytest.raises(ExtractionError):
        extract_text_from_bytes(b"not a zip at all", "essay.docx")


def test_doc_legacy_rejected_with_help():
    with pytest.raises(ExtractionError, match="docx"):
        extract_text_from_bytes(b"\xd0\xcf\x11\xe0junk", "old.doc")


def test_pdf_text_layer():
    text = "The quick brown fox jumps over the lazy dog. " * 20
    result = extract_text_from_bytes(make_pdf(text, pages=2), "doc.pdf")
    assert result.method == "pdfminer"
    assert "quick brown fox" in result.text


def test_pdf_page_cap(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_PDF_PAGES", 2)
    result = extract_text_from_bytes(make_pdf("Lorem ipsum dolor sit amet consectetur " * 10, pages=5), "a.pdf")
    assert any("first 2 of 5" in w for w in result.warnings)


def test_corrupt_pdf():
    with pytest.raises(ExtractionError):
        extract_text_from_bytes(b"%PDF-1.4\n garbage garbage", "broken.pdf")


def test_encrypted_pdf_message():
    content = make_pdf("Secret text " * 30, encrypt="userpass")
    with pytest.raises(ExtractionError, match="password"):
        extract_text_from_bytes(content, "locked.pdf")


@pytest.mark.skipif(not shutil.which("tesseract") or not shutil.which("pdftoppm"), reason="needs tesseract + poppler")
def test_scanned_pdf_uses_ocr():
    content = make_image_pdf("Plagiarism detection test\nScanned documents need OCR")
    result = extract_text_from_bytes(content, "scan.pdf")
    assert result.method == "ocr"
    assert "Scanned" in result.text or "OCR" in result.text


def test_unsupported_extension():
    with pytest.raises(ExtractionError):
        extract_text_from_bytes(b"MZ....", "virus.exe")
