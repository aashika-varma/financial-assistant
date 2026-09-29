import hashlib
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

from pypdf import PdfReader


MAX_BYTES = 25 * 1024 * 1024
ALLOWED_HOSTS = {
    "nsearchives.nseindia.com",
    "archives.nseindia.com",
}


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_announcement(
    announcement: dict,
    output_dir: Path,
) -> dict:
    """Download and validate one PDF; return metadata with its status."""
    result = dict(announcement)
    url = announcement.get("attachment_url")

    if not url:
        return {
            **result,
            "document_status": "missing_attachment",
        }

    try:
        parsed = urlsplit(url)

        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            raise ValueError("Expected a plain HTTPS NSE archive URL")

        request = Request(
            url,
            headers={
                "User-Agent": "FinancialAssistantResearch/0.1",
                "Accept": "application/pdf",
            },
        )

        # Redirects fail explicitly rather than changing hosts silently.
        opener = build_opener(NoRedirects())

        with opener.open(request, timeout=30) as response:
            content = response.read(MAX_BYTES + 1)

        if len(content) > MAX_BYTES:
            raise ValueError("Attachment exceeds the 25 MB limit")

        if not content.startswith(b"%PDF-"):
            raise ValueError("Response is not a PDF")

        reader = PdfReader(BytesIO(content))

        if reader.is_encrypted:
            raise ValueError("Encrypted attachment needs separate handling")

        page_count = len(reader.pages)
        if page_count == 0:
            raise ValueError("PDF has no pages")

        file_hash = hashlib.sha256(content).hexdigest()
        output_dir.mkdir(parents=True, exist_ok=True)

        destination = output_dir / f"{file_hash}.pdf"
        temporary = destination.with_suffix(".pdf.tmp")

        temporary.write_bytes(content)
        temporary.replace(destination)

        result.update({
            "document_status": "downloaded",
            "local_path": str(destination),
            "document_sha256": file_hash,
            "page_count": page_count,
            "size_bytes": len(content),
        })

    except Exception as error:
        result.update({
            "document_status": "download_failed",
            "download_error": f"{type(error).__name__}: {error}",
        })

    return result