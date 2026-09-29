import json
from pathlib import Path

from financial_assistant.ingestion.announcement_text import (
    extract_announcement_text,
)


def main() -> None:
    manifest_path = Path("data/announcements/tcs_manifest.json")
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    documents = []

    for announcement in manifest["announcements"]:
        document = extract_announcement_text(announcement)

        overrides = PAGE_REVIEW_OVERRIDES.get(
            document["document_sha256"],
            {},
        )

        for page in document["pages"]:
            reason = overrides.get(page["page_number"])

            if reason:
                page["text_status"] = "review_required"
                page["review_reason"] = reason

        if overrides and document["extraction_status"] != "failed":
            document["extraction_status"] = "review_needed"
        documents.append(document)

        print(
            f"\n{document['published_at']} | "
            f"{document['subject']} | "
            f"{document['extraction_status']}"
        )

        if document.get("extraction_error"):
            print(f"  Error: {document['extraction_error']}")

        for page in document["pages"]:
            preview = " ".join(page["text"].split())[:180]

            print(
                f"  Page {page['page_number']}: "
                f"{page['character_count']} characters | "
                f"{page['text_status']}"
            )
            print(f"    Preview: {preview or '[no text]'}")

    output = Path("data/announcements/tcs_extracted.json")
    temporary = output.with_suffix(".json.tmp")

    temporary.write_text(
        json.dumps(
            {
                "source_manifest": str(manifest_path),
                "documents": documents,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    temporary.replace(output)

    print(f"\nSaved extracted text: {output}")



# Temporary review overrides for this inspected batch.
# Page numbers are one-based.
PAGE_REVIEW_OVERRIDES = {
    # September 24 newspaper publication
    "4e29fe8f568e9416ab6e214b9d0361f005a8f9492fb75b455b57604a12aea5d5": {
        2: "Corrupted newspaper text; visual review and OCR needed",
        3: "Corrupted newspaper text; visual review and OCR needed",
        4: "Severely corrupted text; language-aware OCR needed",
    },
    # September 25 newspaper publication
    "f35b498e32c47f07467539ca9d89757c64b4ed88219dd642d1fded5433d94f3a": {
        2: "Only repeated office footer extracted; inspect page body",
        3: "Only repeated office footer extracted; inspect page body",
        4: "Only repeated office footer extracted; inspect page body",
    },
}


if __name__ == "__main__":
    main()