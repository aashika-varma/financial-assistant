import hashlib
from pathlib import Path

from pypdf import PdfReader


def extract_announcement_text(announcement: dict) -> dict:
    """Extract page text while retaining announcement provenance."""
    result = dict(announcement)

    if announcement.get("document_status") != "downloaded":
        return {
            **result,
            "extraction_status": "not_attempted",
            "pages": [],
        }

    try:
        path = Path(announcement["local_path"])

        with path.open("rb") as file:
            actual_hash = hashlib.file_digest(file, "sha256").hexdigest()

        if actual_hash != announcement["document_sha256"]:
            raise ValueError("PDF hash does not match the manifest")

        reader = PdfReader(path)

        if reader.is_encrypted:
            raise ValueError("Encrypted PDF needs separate handling")

        pages = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text(extraction_mode="layout") or ""
            text = text.strip()

            # A diagnostic hint, not a guarantee of extraction quality.
            character_count = len("".join(text.split()))
            needs_review = character_count < 100

            pages.append({
                "page_number": page_number,
                "text": text,
                "character_count": character_count,
                "text_status": (
                    "low_text_review_needed"
                    if needs_review
                    else "text_extracted"
                ),
            })

        if not pages:
            raise ValueError("PDF contains no pages")

        result.update({
            "extraction_status": (
                "review_needed"
                if any(
                    page["text_status"] == "low_text_review_needed"
                    for page in pages
                )
                else "text_extracted"
            ),
            "extractor": "pypdf_layout",
            "pages": pages,
        })

    except Exception as error:
        result.update({
            "extraction_status": "failed",
            "extraction_error": f"{type(error).__name__}: {error}",
            "pages": [],
        })

    return result