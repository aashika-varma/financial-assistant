import argparse
import json

from financial_assistant.storage.portfolio_repository import (
    confirm_portfolio_version,
    get_portfolio_version,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--version-id", type=int, required=True)
    args = parser.parse_args()

    version = get_portfolio_version(
        args.user_id,
        args.version_id,
    )

    print("\nSAVED PORTFOLIO VERSION\n")
    print(json.dumps(version, indent=2, default=str))

    if version["status"] != "draft":
        print(f"\nVersion is already {version['status']}. No change made.")
        return

    expected = f"CONFIRM {args.version_id}"
    answer = input(
        f"\nReview the holdings, date, and warnings above. "
        f"Type '{expected}' to confirm, or press Enter to leave as draft: "
    )

    if answer.strip() != expected:
        print("Left as draft.")
        return

    status = confirm_portfolio_version(
        args.user_id,
        args.version_id,
    )
    print(f"Portfolio version {args.version_id}: {status}")


if __name__ == "__main__":
    main()