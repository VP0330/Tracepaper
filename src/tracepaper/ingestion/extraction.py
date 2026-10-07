"""Document extraction with text-layer and OCR provenance."""

import csv
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path


@dataclass(frozen=True)
class ExtractedPage:
    page: int
    text: str
    extraction_method: str
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    ocr_confidence: float | None = None


class DocumentExtractor:
    """Extract text from generated corpus documents."""

    def extract(self, path: str | Path) -> list[ExtractedPage]:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf(file_path)
        if suffix == ".csv":
            return [ExtractedPage(1, self._extract_csv(file_path), "text_layer")]
        if suffix == ".eml":
            return [ExtractedPage(1, self._extract_email(file_path), "text_layer")]
        raise ValueError(f"Unsupported document type: {suffix}")

    def _extract_pdf(self, path: Path) -> list[ExtractedPage]:
        try:
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                pages = [
                    ExtractedPage(index, page.extract_text() or "", "text_layer")
                    for index, page in enumerate(pdf.pages, 1)
                ]
            if any(page.text.strip() for page in pages):
                return pages
        except Exception:
            pass

        # Early Phase 2 fixtures used a text-backed .pdf placeholder. Keep those
        # fixtures ingestible while real PDFs continue through pdfplumber/OCR.
        try:
            import fitz
            import pytesseract
            from PIL import Image

            document = fitz.open(path)
            ocr_pages = []
            for index, page in enumerate(document, 1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
                text = pytesseract.image_to_string(image).strip()
                confidences = [float(value) for value in data["conf"] if float(value) >= 0]
                confidence = sum(confidences) / len(confidences) / 100 if confidences else 0.0
                ocr_pages.append(ExtractedPage(index, text, "ocr", ocr_confidence=confidence))
            if ocr_pages:
                return ocr_pages
        except Exception:
            pass

        raw = path.read_text(encoding="utf-8", errors="replace")
        if raw.startswith("PDF_TEXTLAYER\n"):
            return [ExtractedPage(1, raw.split("\n", 1)[1], "text_layer")]
        return [ExtractedPage(1, raw, "ocr", ocr_confidence=0.0)]

    @staticmethod
    def _extract_csv(path: Path) -> str:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            rows = csv.reader(handle)
            return "\n".join(" | ".join(row) for row in rows)

    @staticmethod
    def _extract_email(path: Path) -> str:
        with path.open("rb") as handle:
            message = BytesParser(policy=policy.default).parse(handle)
        body = message.get_body(preferencelist=("plain", "html"))
        body_text = body.get_content() if body else ""
        headers = "\n".join(
            f"{name}: {message.get(name, '')}" for name in ("From", "To", "Subject", "Date")
        )
        return f"{headers}\n\n{body_text}".strip()
