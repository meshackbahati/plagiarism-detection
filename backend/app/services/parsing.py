"""
Text extraction for uploaded documents.

Supported: .pdf (pdfminer.six, OCR fallback for scanned pages), .docx
(paragraphs, tables, headers/footers), .txt/.md (encoding-aware), and
images (.png/.jpg/.jpeg/.tif/.tiff/.bmp via Tesseract).

Every extractor returns clean text that is safe to store in PostgreSQL
(no NUL bytes) and raises ExtractionError with a human-readable message
when a file cannot be read, so one bad file never breaks a whole upload.
"""

from __future__ import annotations

import asyncio
import inspect
import io
import logging
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field

from app.core.config import settings
from app.services.ocr import OCRError, OCRService

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md"}
PDF_EXTENSIONS = {".pdf"}
DOCX_EXTENSIONS = {".docx"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
DOCUMENT_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS | DOCX_EXTENSIONS | IMAGE_EXTENSIONS

# A PDF whose text layer has fewer meaningful characters than this per page
# is treated as scanned and sent to OCR.
MIN_CHARS_PER_PAGE = 25
# pdfminer emits "(cid:123)" for glyphs it cannot map to unicode (broken
# font encodings). If most of the output is that, OCR does a better job.
_CID_RE = re.compile(r"\(cid:\d+\)")


class ExtractionError(Exception):
    """Raised when a file's text cannot be extracted. Message is user-facing."""


@dataclass
class ExtractionResult:
    text: str
    method: str
    warnings: list[str] = field(default_factory=list)


def file_extension(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


# ── Normalisation ──────────────────────────────────────────────────────────

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n(\w)")
_SPACES_RE = re.compile(r"[ \t ]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """
    Clean extracted text:
    - NFKC folds ligatures (ﬁ -> fi) and full-width forms from PDFs.
    - Strips NUL/control characters (PostgreSQL TEXT rejects \\x00).
    - Re-joins words hyphenated across line breaks ("exam-\\nple").
    - Collapses runs of spaces and blank lines.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = _CONTROL_RE.sub("", text)
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    text = _SPACES_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def _meaningful_chars(text: str) -> int:
    return sum(1 for ch in _CID_RE.sub("", text) if ch.isalnum())


# ── Plain text ─────────────────────────────────────────────────────────────

def decode_text(content: bytes) -> str:
    """Decode bytes, honouring BOMs and falling back to cp1252/latin-1."""
    if content.startswith(b"\xef\xbb\xbf"):
        return content[3:].decode("utf-8", errors="replace")
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16", errors="replace")
    for encoding in ("utf-8", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1")


# ── DOCX ───────────────────────────────────────────────────────────────────

def _extract_docx(content: bytes) -> ExtractionResult:
    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(io.BytesIO(content))
    except (PackageNotFoundError, KeyError, ValueError) as exc:
        raise ExtractionError("This .docx file is damaged or is not a real Word document.") from exc
    except Exception as exc:  # zipfile.BadZipFile and friends
        raise ExtractionError(f"Could not open Word document: {exc}") from exc

    parts: list[str] = []

    def table_text(table) -> list[str]:
        rows = []
        for row in table.rows:
            cells = []
            seen = set()
            for cell in row.cells:
                # Merged cells repeat the same object; keep one copy.
                if id(cell._tc) in seen:
                    continue
                seen.add(id(cell._tc))
                cell_text = cell.text.strip()
                if cell_text:
                    cells.append(cell_text)
            if cells:
                rows.append(" | ".join(cells))
        return rows

    # Walk the body in document order so tables stay where they appear.
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para_text = Paragraph(child, document).text
            if para_text.strip():
                parts.append(para_text)
        elif tag == "tbl":
            parts.extend(table_text(Table(child, document)))

    # Headers and footers often hold the title/author; keep them, once.
    extras: list[str] = []
    for section in document.sections:
        for part in (section.header, section.footer):
            try:
                for para in part.paragraphs:
                    if para.text.strip() and para.text not in extras:
                        extras.append(para.text)
            except Exception:
                continue

    text = "\n".join(parts + extras)
    return ExtractionResult(text=text, method="python-docx")


# ── PDF ────────────────────────────────────────────────────────────────────

def _pdf_text_layer(content: bytes, max_pages: int) -> tuple[str, int]:
    """Return (text, page_count) using pdfminer. Raises ExtractionError."""
    from pdfminer.high_level import extract_text
    from pdfminer.layout import LAParams
    from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFSyntaxError
    from pdfminer.psparser import PSException

    try:
        page_count = sum(1 for _ in PDFPage.get_pages(io.BytesIO(content)))
    except PDFPasswordIncorrect as exc:
        raise ExtractionError("This PDF is password-protected. Remove the password and upload it again.") from exc
    except PDFEncryptionError as exc:
        raise ExtractionError("This PDF uses an encryption method that cannot be read.") from exc
    except (PDFSyntaxError, PSException) as exc:
        raise ExtractionError("This PDF is damaged or not a valid PDF file.") from exc
    except Exception as exc:
        raise ExtractionError(f"Could not read PDF: {exc}") from exc

    if page_count == 0:
        raise ExtractionError("This PDF has no pages.")

    try:
        text = extract_text(
            io.BytesIO(content),
            maxpages=max_pages,
            laparams=LAParams(line_margin=0.5, char_margin=2.0, word_margin=0.1),
        )
    except PDFPasswordIncorrect as exc:
        raise ExtractionError("This PDF is password-protected. Remove the password and upload it again.") from exc
    except Exception as exc:
        # The text layer is broken, but OCR may still work.
        logger.warning("pdfminer failed, falling back to OCR: %s", exc)
        text = ""
    return text or "", page_count


def _extract_pdf(content: bytes) -> ExtractionResult:
    max_pages = settings.MAX_PDF_PAGES
    text, page_count = _pdf_text_layer(content, max_pages)
    warnings: list[str] = []
    pages_read = min(page_count, max_pages)
    if page_count > max_pages:
        warnings.append(f"Only the first {max_pages} of {page_count} pages were analysed.")

    cid_hits = len(_CID_RE.findall(text))
    meaningful = _meaningful_chars(text)
    looks_scanned = meaningful < MIN_CHARS_PER_PAGE * max(1, pages_read) * 0.5
    looks_garbled = cid_hits > 20 and cid_hits * 5 > meaningful

    if not (looks_scanned or looks_garbled):
        return ExtractionResult(text=_CID_RE.sub("", text), method="pdfminer", warnings=warnings)

    # Scanned or garbled PDF: OCR it page by page.
    ocr_pages = min(pages_read, settings.MAX_OCR_PAGES)
    if pages_read > ocr_pages:
        warnings.append(f"Scanned PDF: only the first {ocr_pages} pages were OCR'd.")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        ocr_text = OCRService.extract_text_from_scanned_pdf(tmp_path, max_pages=ocr_pages)
    except OCRError as exc:
        if meaningful:
            warnings.append(f"OCR unavailable ({exc}); used the PDF text layer as-is.")
            return ExtractionResult(text=_CID_RE.sub("", text), method="pdfminer", warnings=warnings)
        raise ExtractionError(f"This PDF has no text layer and OCR failed: {exc}") from exc
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # Keep whichever source produced more real text.
    if _meaningful_chars(ocr_text) >= meaningful:
        return ExtractionResult(text=ocr_text, method="ocr", warnings=warnings)
    return ExtractionResult(text=_CID_RE.sub("", text), method="pdfminer", warnings=warnings)


# ── Images ─────────────────────────────────────────────────────────────────

def _extract_image(content: bytes, ext: str) -> ExtractionResult:
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        text = OCRService.extract_text_from_image(tmp_path)
    except OCRError as exc:
        raise ExtractionError(f"OCR failed: {exc}") from exc
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return ExtractionResult(text=text, method="ocr")


# ── Public API ─────────────────────────────────────────────────────────────

def extract_text_from_bytes(content: bytes, filename: str) -> ExtractionResult:
    """
    Synchronous extraction. CPU-heavy (pdfminer/OCR), so call it from a
    worker thread (see extract_text_from_file) when inside an event loop.
    """
    ext = file_extension(filename)
    if not content:
        raise ExtractionError("The file is empty.")

    if ext in PDF_EXTENSIONS or (not ext and content.startswith(b"%PDF-")):
        result = _extract_pdf(content)
    elif ext in DOCX_EXTENSIONS:
        result = _extract_docx(content)
    elif ext in IMAGE_EXTENSIONS:
        result = _extract_image(content, ext)
    elif ext == ".doc":
        raise ExtractionError("Old Word .doc files are not supported. Save it as .docx or PDF and upload again.")
    elif ext in TEXT_EXTENSIONS or not ext:
        result = ExtractionResult(text=decode_text(content), method="text")
    else:
        raise ExtractionError(f"Unsupported file type '{ext}'.")

    result.text = normalize_text(result.text)
    if not result.text:
        raise ExtractionError("No readable text was found in this file.")
    return result


async def _read_file_bytes(file) -> bytes:
    if isinstance(file, (bytes, bytearray)):
        return bytes(file)
    read_method = getattr(file, "read", None)
    if read_method is None:
        raise ValueError("Unsupported input type for text extraction")
    result = read_method()
    if inspect.isawaitable(result):
        return await result
    return result


async def extract_text_from_file(file, filename: str | None = None) -> str:
    """
    Backwards-compatible async helper: returns the text only and runs the
    blocking extraction in a thread so it never stalls the API event loop.
    Raises ExtractionError on failure.
    """
    content = await _read_file_bytes(file)
    resolved = filename or getattr(file, "filename", None) or getattr(file, "name", "") or ""
    result = await asyncio.to_thread(extract_text_from_bytes, content, resolved)
    return result.text
