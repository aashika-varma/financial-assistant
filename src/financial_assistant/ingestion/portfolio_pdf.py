from pathlib import Path

from pypdf import PdfReader


def read_portfolio_pdf(path: Path) -> list[str]:
    """Extract text while preserving page boundaries."""
    reader = PdfReader(path)

    if reader.is_encrypted:
        raise ValueError("This version requires an unlocked PDF")

    pages = []

    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text(extraction_mode="layout") or ""

        if not text.strip():
            raise ValueError(
                f"Page {number} has no extractable text. "
                "OCR or visual extraction is required."
            )

        pages.append(text)

    if not pages:
        raise ValueError("The PDF contains no pages")

    return pages