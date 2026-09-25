"""Versioned, page-local fixed character windows. No normalization or trimming."""

import logging
from pathlib import Path
from pypdf import PdfReader, __version__

# Parser warnings can contain source fragments. Return application-owned errors only.
logging.getLogger("pypdf").setLevel(logging.CRITICAL)
PARSER_VERSION = f"pypdf-{__version__}/utf8-v1"
MAX_PAGES = 2000
MAX_CHARACTERS = 5_000_000
MAX_CHUNKS = 50_000


class ProcessingError(Exception):
    pass


def validate_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ProcessingError("TXT files must use UTF-8 encoding.") from None
    if "\x00" in text:
        raise ProcessingError("TXT contains unsupported null characters.")
    if not text.strip():
        raise ProcessingError("The document contains no text.")
    return text


def pages(path: Path, media_type: str):
    # Keep the legacy document-processing API useful for every released upload
    # format. Schema-v2 ingestion retains the richer block model; this adapter
    # only flattens those canonical blocks into the historical page contract.
    if media_type not in {"application/pdf", "text/plain"}:
        from app.ingestion_content.extractors.formats import (
            STRUCTURED_MEDIA_TYPES,
            extract_structured_document,
        )
        from app.ingestion_content.processing import IngestionStageError

        if media_type not in STRUCTURED_MEDIA_TYPES:
            raise ProcessingError("The document format is unsupported.")
        try:
            document, _ = extract_structured_document(path, media_type, path.name)
        except IngestionStageError as exc:
            raise ProcessingError(str(exc)) from None
        grouped: dict[int | None, list[str]] = {}
        for block in document.blocks:
            grouped.setdefault(block.page_number, []).append(block.text)
        values = [
            (page_number, "\n\n".join(blocks))
            for page_number, blocks in grouped.items()
            if any(value.strip() for value in blocks)
        ]
        if not values:
            raise ProcessingError("The document contains no text.")
        for completed, (page_number, value) in enumerate(values, 1):
            yield page_number, value, completed, len(values)
        return
    if media_type == "text/plain":
        value = validate_text(path.read_bytes())
        if len(value) > MAX_CHARACTERS:
            raise ProcessingError(
                "Document exceeds the 5,000,000 character processing limit."
            )
        yield None, value, 1, 1
        return
    try:
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise ProcessingError(
                "Encrypted PDFs are unsupported. Upload an unencrypted PDF."
            )
        count = len(reader.pages)
        if count == 0 or count > MAX_PAGES:
            raise ProcessingError("PDF must contain between 1 and 2,000 pages.")
        total = 0
        found = False
        for number, page in enumerate(reader.pages, 1):
            value = page.extract_text() or ""
            # Image-only pages cannot silently disappear from mixed documents.
            if not value.strip() and len(page.images):
                raise ProcessingError(
                    "Scanned PDF requires OCR, which is unsupported. Upload a text-based PDF."
                )
            if "\x00" in value:
                raise ProcessingError("PDF contains unsupported null characters.")
            total += len(value)
            if total > MAX_CHARACTERS:
                raise ProcessingError(
                    "Document exceeds the 5,000,000 character processing limit."
                )
            found = found or bool(value.strip())
            yield number, value, number, count
        if not found:
            raise ProcessingError(
                "PDF has no extractable text; scanned PDFs require OCR, which is unsupported."
            )
    except ProcessingError:
        raise
    except Exception:
        raise ProcessingError(
            "PDF could not be parsed. Upload a valid, unencrypted text-based PDF."
        ) from None


def windows(text: str, size: int, overlap: int):
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Invalid character chunk settings")
    if not text.strip():
        return
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        yield start, end, text[start:end]
        if end == len(text):
            break
        start += size - overlap
