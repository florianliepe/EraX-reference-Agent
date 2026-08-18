from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import fitz
from docx import Document
from openpyxl import load_workbook
from PIL import Image
from pptx import Presentation


SUPPORTED = {".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".pdf", ".png", ".jpg", ".jpeg"}
OOXML_SIGNATURE = b"PK"
PDF_SIGNATURE = b"%PDF"
IMAGE_SIGNATURES = (b"\x89PNG", b"\xff\xd8\xff")
CLASSIFICATION_ORDER = {"public": 0, "internal": 1, "confidential": 2, "strict": 3}


@dataclass
class Chunk:
    text: str
    location: str | None = None


def validate_signature(path: Path) -> None:
    head = path.read_bytes()[:8]
    suffix = path.suffix.lower()
    if suffix in {".pptx", ".docx", ".xlsx"} and not head.startswith(OOXML_SIGNATURE):
        raise ValueError("File content does not match its OOXML extension")
    if suffix == ".pdf" and not head.startswith(PDF_SIGNATURE):
        raise ValueError("File content does not match PDF extension")
    if suffix in {".png", ".jpg", ".jpeg"} and not any(head.startswith(sig) for sig in IMAGE_SIGNATURES):
        raise ValueError("File content does not match image extension")


def parse_docx(path: Path) -> list[Chunk]:
    document = Document(path)
    return [Chunk(p.text.strip(), f"paragraph {i + 1}") for i, p in enumerate(document.paragraphs) if p.text.strip()]


def parse_pptx(path: Path) -> list[Chunk]:
    deck = Presentation(path)
    chunks: list[Chunk] = []
    for index, slide in enumerate(deck.slides, 1):
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                chunks.append(Chunk(shape.text.strip(), f"slide {index}"))
    return chunks


def parse_xlsx(path: Path) -> list[Chunk]:
    book = load_workbook(path, read_only=True, data_only=True)
    chunks: list[Chunk] = []
    for sheet in book.worksheets:
        for row_index, row in enumerate(sheet.iter_rows(values_only=True), 1):
            text = " | ".join(str(value).strip() for value in row if value not in (None, ""))
            if text:
                chunks.append(Chunk(text, f"{sheet.title}!{row_index}"))
    return chunks


def parse_pdf(path: Path) -> list[Chunk]:
    document = fitz.open(path)
    return [Chunk(page.get_text("text").strip(), f"page {i + 1}") for i, page in enumerate(document) if page.get_text("text").strip()]


def parse_image(path: Path) -> list[Chunk]:
    try:
        import pytesseract
        text = pytesseract.image_to_string(Image.open(path)).strip()
    except Exception as exc:
        raise ValueError("OCR unavailable or image contains no readable text") from exc
    return [Chunk(text, "OCR")] if text else []


PARSERS: dict[str, Callable[[Path], list[Chunk]]] = {
    ".docx": parse_docx,
    ".pptx": parse_pptx,
    ".xlsx": parse_xlsx,
    ".pdf": parse_pdf,
    ".png": parse_image,
    ".jpg": parse_image,
    ".jpeg": parse_image,
}


def parse_file(path: Path) -> list[Chunk]:
    if path.suffix.lower() in {".doc", ".xls", ".ppt"}:
        raise ValueError("Legacy Office format requires LibreOffice conversion to OOXML")
    validate_signature(path)
    chunks = PARSERS[path.suffix.lower()](path)
    return [Chunk(re.sub(r"\s+", " ", chunk.text).strip(), chunk.location) for chunk in chunks if chunk.text.strip()]


def detect_classification(chunks: list[Chunk]) -> str:
    detected = "public"
    patterns = {
        "strict": r"\b(strictly confidential|strict)\b",
        "confidential": r"\bconfidential\b",
        "internal": r"\b(internal use only|internal)\b",
        "public": r"\bpublic\b",
    }
    joined = " ".join(chunk.text for chunk in chunks).lower()
    for label, pattern in patterns.items():
        if re.search(pattern, joined) and CLASSIFICATION_ORDER[label] > CLASSIFICATION_ORDER[detected]:
            detected = label
    return detected

