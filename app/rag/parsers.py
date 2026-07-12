from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
import mimetypes


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    mime_type: str | None
    ocr_used: bool = False
    warnings: list[str] = field(default_factory=list)


def extract_document_text(path: Path, force_ocr: bool = False) -> ExtractionResult:
    mime_type, _ = mimetypes.guess_type(path.name)
    suffix = path.suffix.lower()
    warnings: list[str] = []

    if force_ocr:
        text = _extract_with_ocr(path, warnings)
        return ExtractionResult(text=text, mime_type=mime_type, ocr_used=True, warnings=warnings)

    if suffix in {".txt", ".md", ".csv", ".tsv"}:
        return ExtractionResult(text=path.read_text(encoding="utf-8", errors="ignore"), mime_type=mime_type)

    if suffix == ".pdf":
        text = _extract_pdf_text(path, warnings)
        if _looks_like_scanned_document(text):
            text = _extract_with_ocr(path, warnings)
            return ExtractionResult(text=text, mime_type=mime_type, ocr_used=True, warnings=warnings)
        return ExtractionResult(text=text, mime_type=mime_type, warnings=warnings)

    if suffix == ".docx":
        return ExtractionResult(text=_extract_docx_text(path, warnings), mime_type=mime_type, warnings=warnings)

    if suffix == ".xlsx":
        return ExtractionResult(text=_extract_xlsx_text(path, warnings), mime_type=mime_type, warnings=warnings)

    if suffix == ".pptx":
        return ExtractionResult(text=_extract_pptx_text(path, warnings), mime_type=mime_type, warnings=warnings)

    warnings.append(f"No parser configured for {suffix}; attempted utf-8 text fallback.")
    return ExtractionResult(text=path.read_text(encoding="utf-8", errors="ignore"), mime_type=mime_type, warnings=warnings)


def _extract_pdf_text(path: Path, warnings: list[str]) -> str:
    try:
        import fitz  # type: ignore
    except ImportError:
        warnings.append("PyMuPDF is not installed; attempted utf-8 text fallback for PDF.")
        return path.read_text(encoding="utf-8", errors="ignore")

    pages: list[str] = []
    with fitz.open(path) as document:
        for page in document:
            pages.append(page.get_text("text"))
    return "\n\n".join(pages)


def _extract_docx_text(path: Path, warnings: list[str]) -> str:
    try:
        import docx  # type: ignore
    except ImportError:
        warnings.append("python-docx is not installed; attempted utf-8 text fallback for DOCX.")
        return path.read_text(encoding="utf-8", errors="ignore")

    document = docx.Document(path)
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(paragraphs)


def _extract_xlsx_text(path: Path, warnings: list[str]) -> str:
    try:
        import openpyxl  # type: ignore
    except ImportError:
        warnings.append("openpyxl is not installed; attempted utf-8 text fallback for XLSX.")
        return path.read_text(encoding="utf-8", errors="ignore")

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows: list[str] = []
    for worksheet in workbook.worksheets:
        rows.append(f"Sheet: {worksheet.title}")
        for row in worksheet.iter_rows(values_only=True):
            values = [str(value) for value in row if value is not None and str(value).strip()]
            if values:
                rows.append(" | ".join(values))
    workbook.close()
    return "\n".join(rows)


def _extract_pptx_text(path: Path, warnings: list[str]) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            slide_names = sorted(
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
            slides: list[str] = []
            namespace = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
            for index, slide_name in enumerate(slide_names, start=1):
                root = ET.fromstring(archive.read(slide_name))
                texts = [
                    node.text.strip()
                    for node in root.findall(".//a:t", namespace)
                    if node.text and node.text.strip()
                ]
                if texts:
                    slides.append(f"Slide {index}: " + " ".join(texts))
            return "\n".join(slides)
    except (zipfile.BadZipFile, ET.ParseError):
        warnings.append("Unable to parse PPTX; attempted utf-8 text fallback.")
        return path.read_text(encoding="utf-8", errors="ignore")


def _extract_with_ocr(path: Path, warnings: list[str]) -> str:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError:
        warnings.append("OCR dependencies are not installed; returning empty OCR result.")
        return ""

    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        return pytesseract.image_to_string(Image.open(path))

    warnings.append("OCR for PDFs requires a PDF-to-image renderer in the worker image.")
    return ""


def _looks_like_scanned_document(text: str) -> bool:
    return len(text.strip()) < 100
