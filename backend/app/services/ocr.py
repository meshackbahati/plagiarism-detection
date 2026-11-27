import logging
import os

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

# Rendering resolution for scanned PDFs. 300 DPI is Tesseract's sweet spot;
# 200 keeps memory reasonable on large scans with little accuracy loss.
OCR_DPI = int(os.getenv("OCR_DPI", "200"))
OCR_LANG = os.getenv("OCR_LANG", "eng")


class OCRError(Exception):
    """OCR could not run (Tesseract/Poppler missing or the input is unreadable)."""


class OCRService:
    """Optical Character Recognition via Tesseract (and Poppler for PDFs)."""

    @staticmethod
    def _tesseract():
        try:
            import pytesseract
        except ImportError as exc:  # pragma: no cover - dependency is in pyproject
            raise OCRError("pytesseract is not installed") from exc
        return pytesseract

    @staticmethod
    def _ocr_image(image) -> str:
        pytesseract = OCRService._tesseract()
        try:
            if image.mode not in ("L", "RGB"):
                image = image.convert("RGB")
            return pytesseract.image_to_string(image, lang=OCR_LANG)
        except pytesseract.TesseractNotFoundError as exc:
            raise OCRError("Tesseract is not installed on this machine") from exc
        except pytesseract.TesseractError as exc:
            # e.g. language data missing (set OCR_LANG / install tesseract-ocr-<lang>)
            raise OCRError(f"Tesseract failed: {str(exc.message if hasattr(exc, 'message') else exc).strip()[:200]}") from exc

    @staticmethod
    def extract_text_from_image(image_path: str) -> str:
        from PIL import Image, ImageOps, UnidentifiedImageError

        try:
            with Image.open(image_path) as image:
                # Respect phone-camera rotation and handle multi-page TIFFs.
                texts = []
                frame = 0
                while True:
                    try:
                        image.seek(frame)
                    except EOFError:
                        break
                    texts.append(OCRService._ocr_image(ImageOps.exif_transpose(image.copy())))
                    frame += 1
                    if frame >= 50:
                        break
                return "\n\n".join(texts)
        except UnidentifiedImageError as exc:
            raise OCRError("the file is not a readable image") from exc
        except Image.DecompressionBombError as exc:
            raise OCRError("the image is too large to process") from exc

    @staticmethod
    def extract_text_from_scanned_pdf(pdf_path: str, max_pages: int | None = None) -> str:
        """
        Render a PDF page by page and OCR each one. Rendering one page at a
        time keeps memory flat even for long scans.
        """
        try:
            from pdf2image import convert_from_path, pdfinfo_from_path
            from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError
        except ImportError as exc:  # pragma: no cover
            raise OCRError("pdf2image is not installed") from exc

        try:
            pages = int(pdfinfo_from_path(pdf_path).get("Pages", 0))
        except PDFInfoNotInstalledError as exc:
            raise OCRError("Poppler (pdftoppm) is not installed on this machine") from exc
        except (PDFPageCountError, Exception) as exc:
            raise OCRError(f"could not read the PDF pages ({exc})") from exc

        if max_pages:
            pages = min(pages, max_pages)

        texts = []
        for page_no in range(1, pages + 1):
            images = convert_from_path(pdf_path, dpi=OCR_DPI, first_page=page_no, last_page=page_no)
            for image in images:
                texts.append(OCRService._ocr_image(image))
                image.close()
        return "\n\n".join(texts)

    @staticmethod
    def is_image(filename: str) -> bool:
        return os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS
