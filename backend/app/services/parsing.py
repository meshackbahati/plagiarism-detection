from fastapi import UploadFile
from pdfminer.high_level import extract_text
import docx
import io
import os
import inspect
import tempfile

from app.services.ocr import OCRService


async def _read_file_bytes(file) -> bytes:
    read_method = getattr(file, "read", None)
    if read_method is None:
        if isinstance(file, (bytes, bytearray)):
            return bytes(file)
        raise ValueError("Unsupported input type for text extraction")

    result = read_method()
    if inspect.isawaitable(result):
        return await result
    return result


async def extract_text_from_file(file, filename: str | None = None) -> str:
    """
    Extracts text from a file, supporting .txt, .docx, .pdf, and image formats (.png, .jpg, .jpeg).
    Uses OCRService for image/scanned PDF text extraction.
    """
    content = await _read_file_bytes(file)
    resolved_filename = filename or getattr(file, "filename", None) or getattr(file, "name", "")
    filename = resolved_filename.lower()

    if filename.endswith(".docx"):
        doc = docx.Document(io.BytesIO(content))
        return " ".join([para.text for para in doc.paragraphs])

    elif filename.endswith(".pdf"):
        # Try standard extraction first (works for text-based PDFs)
        text = extract_text(io.BytesIO(content))
        if len(text.strip()) < 10:
            # Scanned PDF - fall back to OCR via OCRService
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                return OCRService.extract_text_from_scanned_pdf(tmp_path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        return text

    elif OCRService.is_image(filename):
        # Use OCRService for image text extraction
        with tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(filename)[1], delete=False
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            return OCRService.extract_text_from_image(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    elif filename.endswith(".txt"):
        return content.decode("utf-8")

    else:
        # For other file types, attempt to decode as utf-8
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return ""
