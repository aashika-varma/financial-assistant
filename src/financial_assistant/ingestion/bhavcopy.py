import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from datetime import date
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from financial_assistant.schemas.market import BhavcopyQuote


def load_bhavcopy_zip(
    path: Path,
    symbols: list[str],
    target_session: date,
) -> list[BhavcopyQuote]:
    """Read the target session's NSE CSV from a downloaded ZIP.

    Filters to the supplied symbols only (portfolio-scoped ingestion).
    For full-market ingestion use load_bhavcopy_zip_full.
    """
    expected_name = f"{target_session:%Y%m%d}_NSE.csv"

    with ZipFile(path) as archive:
        matches = [
            member
            for member in archive.infolist()
            if not member.is_dir()
            and Path(member.filename).name == expected_name
        ]

        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one {expected_name}; "
                f"found {len(matches)}"
            )

        member = matches[0]

        if member.file_size > 50 * 1024 * 1024:
            raise ValueError("CSV exceeds the 50 MB ingestion limit")

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / expected_name

            # Write only the selected CSV to a controlled local path.
            csv_path.write_bytes(archive.read(member))

            return load_bhavcopy(csv_path, symbols)


def load_bhavcopy_zip_full(
    path: Path,
    target_session: date,
) -> list[BhavcopyQuote]:
    """Read ALL NSE EQ rows from a downloaded ZIP (full-market ingestion)."""
    expected_name = f"{target_session:%Y%m%d}_NSE.csv"

    with ZipFile(path) as archive:
        matches = [
            member
            for member in archive.infolist()
            if not member.is_dir()
            and Path(member.filename).name == expected_name
        ]

        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one {expected_name}; "
                f"found {len(matches)}"
            )

        member = matches[0]

        if member.file_size > 50 * 1024 * 1024:
            raise ValueError("CSV exceeds the 50 MB ingestion limit")

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / expected_name
            csv_path.write_bytes(archive.read(member))
            return load_bhavcopy_full(csv_path)


def parse_trade_date(value: str):
    value = value.strip()

    for date_format in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    raise ValueError(f"Unsupported trading date: {value!r}")


def load_bhavcopy(
    path: Path,
    symbols: list[str],
) -> list[BhavcopyQuote]:
    """Load EQ quotes for a specific set of symbols (portfolio-scoped)."""
    requested = set(symbols)
    quotes_by_symbol = {}

    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        required = {
            "SYMBOL", "SERIES", "ISIN", "OPEN", "HIGH", "LOW",
            "CLOSE", "PREVCLOSE", "TOTTRDQTY", "TIMESTAMP",
        }
        headers = {name.strip() for name in reader.fieldnames or []}

        if missing := required - headers:
            raise ValueError(f"Missing CSV columns: {sorted(missing)}")

        for raw_row in reader:
            row = {
                key.strip(): (value or "").strip()
                for key, value in raw_row.items()
                if key is not None
            }

            symbol = row["SYMBOL"]

            if symbol not in requested or row["SERIES"] != "EQ":
                continue

            if symbol in quotes_by_symbol:
                raise ValueError(f"Duplicate EQ record for {symbol}")

            close = Decimal(row["CLOSE"])
            previous = Decimal(row["PREVCLOSE"])

            if previous <= 0:
                raise ValueError(f"Invalid previous close for {symbol}")

            change = (close - previous) / previous * Decimal("100")

            quotes_by_symbol[symbol] = BhavcopyQuote(
                exchange="NSE",
                series=row["SERIES"],
                isin=row["ISIN"],
                symbol=symbol,
                date=parse_trade_date(row["TIMESTAMP"]),
                open=Decimal(row["OPEN"]),
                high=Decimal(row["HIGH"]),
                low=Decimal(row["LOW"]),
                close=close,
                prev_close=previous,
                pct_change=change.quantize(Decimal("0.01")),
                volume=int(row["TOTTRDQTY"]),
            )

    if missing := requested - quotes_by_symbol.keys():
        raise ValueError(f"Missing EQ holdings: {sorted(missing)}")

    return [quotes_by_symbol[symbol] for symbol in symbols]


def load_bhavcopy_full(path: Path) -> list[BhavcopyQuote]:
    """Load ALL valid NSE EQ quotes from a bhavcopy CSV.

    Skips non-EQ series (futures, bonds, ETFs etc.) and any row where
    PREVCLOSE is zero or non-positive (these cannot produce a meaningful
    pct_change and indicate bad data).  All other rows are returned.
    Duplicate ISIN+SERIES combinations raise immediately.
    """
    quotes = []
    seen_isins: set[str] = set()

    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        required = {
            "SYMBOL", "SERIES", "ISIN", "OPEN", "HIGH", "LOW",
            "CLOSE", "PREVCLOSE", "TOTTRDQTY", "TIMESTAMP",
        }
        headers = {name.strip() for name in reader.fieldnames or []}

        if missing := required - headers:
            raise ValueError(f"Missing CSV columns: {sorted(missing)}")

        for raw_row in reader:
            row = {
                key.strip(): (value or "").strip()
                for key, value in raw_row.items()
                if key is not None
            }

            # Full-market ingestion: EQ series only, same as portfolio path.
            if row["SERIES"] != "EQ":
                continue

            isin = row["ISIN"]
            if isin in seen_isins:
                raise ValueError(
                    f"Duplicate EQ ISIN in bhavcopy: {isin}"
                )
            seen_isins.add(isin)

            try:
                close = Decimal(row["CLOSE"])
                previous = Decimal(row["PREVCLOSE"])
            except Exception:
                # Skip malformed numeric rows rather than aborting the run.
                continue

            if previous <= 0:
                # Cannot compute a meaningful percentage change; skip.
                continue

            change = (close - previous) / previous * Decimal("100")

            try:
                quote = BhavcopyQuote(
                    exchange="NSE",
                    series=row["SERIES"],
                    isin=isin,
                    symbol=row["SYMBOL"],
                    date=parse_trade_date(row["TIMESTAMP"]),
                    open=Decimal(row["OPEN"]),
                    high=Decimal(row["HIGH"]),
                    low=Decimal(row["LOW"]),
                    close=close,
                    prev_close=previous,
                    pct_change=change.quantize(Decimal("0.01")),
                    volume=int(row["TOTTRDQTY"]),
                )
            except Exception:
                # Pydantic validation failure on a single row: skip it.
                continue

            quotes.append(quote)

    if not quotes:
        raise ValueError("No valid EQ quotes found in bhavcopy CSV")

    return quotes
