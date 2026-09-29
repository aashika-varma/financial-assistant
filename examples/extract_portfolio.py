import argparse
from pathlib import Path
import json

from financial_assistant.features.portfolio_import.validation import (
    validate_and_resolve,
)

from financial_assistant.features.portfolio_import.service import (
    extract_portfolio,
)

from financial_assistant.storage.portfolio_repository import (
    save_portfolio_draft,
)


from financial_assistant.observability.logger import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)

    parser.add_argument("--save-draft", action="store_true")
    parser.add_argument("--user-id")


    args = parser.parse_args()

    if args.save_draft and not args.user_id:
        parser.error("--user-id is required with --save-draft")

    setup_logging()

    draft = extract_portfolio(args.file)

    review = validate_and_resolve(draft)

    print("\nVALIDATION AND INSTRUMENT MATCHING\n")
    print(json.dumps(review, indent=2, ensure_ascii=False))

    if args.save_draft:
        saved = save_portfolio_draft(
            user_id=args.user_id,
            source_file=args.file,
            review=review,
        )

        print("\nSAVED PORTFOLIO VERSIONS\n")
        print(json.dumps(saved, indent=2))

    print("\nEXTRACTED PORTFOLIO DRAFT\n")
    print(draft.model_dump_json(indent=2))


if __name__ == "__main__":
    main()