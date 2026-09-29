import argparse
import json
from pathlib import Path

from financial_assistant.storage.rss_repository import save_rss_snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()

    result = save_rss_snapshot(args.file)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()