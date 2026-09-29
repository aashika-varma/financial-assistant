import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from psycopg.types.json import Jsonb
from psycopg.rows import dict_row

from financial_assistant.storage.database import get_connection


def save_portfolio_draft(
    user_id: str,
    source_file: Path,
    review: dict,
) -> list[dict]:
    """Save validated holdings as account-specific draft versions."""
    if not user_id.strip():
        raise ValueError("user_id is required")

    if review.get("status") != "ready_for_review" or review.get("errors"):
        raise ValueError("Resolve validation errors before saving")

    holdings = review.get("holdings", [])
    if not holdings:
        raise ValueError("Cannot save an empty portfolio")

    holdings_date = date.fromisoformat(review["holdings_as_of"])

    with source_file.open("rb") as file:
        file_hash = hashlib.file_digest(file, "sha256").hexdigest()

    accounts = {}
    seen = set()

    for holding in holdings:
        account_ref = holding["account_reference"]
        instrument_id = holding["instrument_id"]
        quantity = Decimal(holding["quantity"])

        if not account_ref.strip():
            raise ValueError("Missing account reference")

        if not quantity.is_finite() or quantity <= 0:
            raise ValueError("Invalid holding quantity")

        identity = (account_ref, instrument_id)
        if identity in seen:
            raise ValueError("Duplicate instrument within an account")
        seen.add(identity)

        accounts.setdefault(account_ref, []).append(holding)

    saved_versions = []

    # Commit all accounts together, or roll back the whole import.
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for account_ref, account_holdings in accounts.items():
                cursor.execute(
                    """
                    INSERT INTO portfolio_accounts (
                        user_id, account_reference
                    )
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, account_reference)
                    DO UPDATE SET
                        account_reference = EXCLUDED.account_reference
                    RETURNING account_id
                    """,
                    (user_id, account_ref),
                )
                account_id = cursor.fetchone()[0]

                cursor.execute(
                    """
                    INSERT INTO portfolio_versions (
                        account_id,
                        holdings_as_of,
                        source_file,
                        source_sha256,
                        warnings,
                        evidence_verification
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (account_id, source_sha256)
                    DO NOTHING
                    RETURNING portfolio_version_id, status
                    """,
                    (
                        account_id,
                        holdings_date,
                        source_file.name,
                        file_hash,
                        Jsonb(review.get("warnings", [])),
                        review.get(
                            "evidence_verification",
                            "not_performed",
                        ),
                    ),
                )
                version = cursor.fetchone()
                created = version is not None

                if created:
                    version_id, status = version

                    cursor.executemany(
                        """
                        INSERT INTO portfolio_version_holdings (
                            portfolio_version_id,
                            instrument_id,
                            quantity,
                            source_page,
                            extracted_evidence
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        [
                            (
                                version_id,
                                holding["instrument_id"],
                                Decimal(holding["quantity"]),
                                holding["source_page"],
                                holding["extracted_evidence"],
                            )
                            for holding in account_holdings
                        ],
                    )
                else:
                    cursor.execute(
                        """
                        SELECT portfolio_version_id, status
                        FROM portfolio_versions
                        WHERE account_id = %s
                          AND source_sha256 = %s
                        """,
                        (account_id, file_hash),
                    )
                    version_id, status = cursor.fetchone()

                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM portfolio_version_holdings
                    WHERE portfolio_version_id = %s
                    """,
                    (version_id,),
                )
                holding_count = cursor.fetchone()[0]

                saved_versions.append({
                    "account_reference": account_ref,
                    "portfolio_version_id": version_id,
                    "status": status,
                    "created": created,
                    "holding_count": holding_count,
                })

    return saved_versions


def get_portfolio_version(user_id: str, version_id: int) -> dict:
    """Load a saved version belonging to the supplied user."""
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    v.portfolio_version_id,
                    a.account_reference,
                    v.holdings_as_of,
                    v.status,
                    v.source_file,
                    v.warnings,
                    v.evidence_verification
                FROM portfolio_versions AS v
                JOIN portfolio_accounts AS a
                    ON a.account_id = v.account_id
                WHERE v.portfolio_version_id = %s
                  AND a.user_id = %s
                """,
                (version_id, user_id),
            )
            version = cursor.fetchone()

            if version is None:
                raise ValueError("Portfolio version not found for this user")

            cursor.execute(
                """
                SELECT
                    i.instrument_id,
                    i.symbol,
                    i.isin,
                    h.quantity,
                    h.source_page,
                    h.extracted_evidence
                FROM portfolio_version_holdings AS h
                JOIN instruments AS i
                    ON i.instrument_id = h.instrument_id
                WHERE h.portfolio_version_id = %s
                ORDER BY i.symbol
                """,
                (version_id,),
            )
            version["holdings"] = cursor.fetchall()

    return version


def confirm_portfolio_version(user_id: str, version_id: int) -> str:
    """Confirm an existing draft without changing its holdings."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT v.status
                FROM portfolio_versions AS v
                JOIN portfolio_accounts AS a
                    ON a.account_id = v.account_id
                WHERE v.portfolio_version_id = %s
                  AND a.user_id = %s
                FOR UPDATE OF v
                """,
                (version_id, user_id),
            )
            row = cursor.fetchone()

            if row is None:
                raise ValueError("Portfolio version not found for this user")

            status = row[0]

            if status == "confirmed":
                return "already_confirmed"

            if status != "draft":
                raise ValueError(f"Cannot confirm a {status} version")

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM portfolio_version_holdings
                WHERE portfolio_version_id = %s
                """,
                (version_id,),
            )

            if cursor.fetchone()[0] == 0:
                raise ValueError("Cannot confirm an empty portfolio")

            cursor.execute(
                """
                UPDATE portfolio_versions
                SET status = 'confirmed',
                    confirmed_at = NOW()
                WHERE portfolio_version_id = %s
                """,
                (version_id,),
            )

    return "confirmed"



def get_confirmed_portfolio(
    user_id: str,
    trading_date: date,
) -> list[dict]:
    """Load the latest applicable confirmed version for each account."""
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (v.account_id)
                    v.account_id,
                    v.portfolio_version_id
                FROM portfolio_versions AS v
                JOIN portfolio_accounts AS a
                    ON a.account_id = v.account_id
                WHERE a.user_id = %s
                  AND v.status = 'confirmed'
                  AND v.holdings_as_of <= %s
                ORDER BY
                    v.account_id,
                    v.holdings_as_of DESC,
                    v.confirmed_at DESC,
                    v.portfolio_version_id DESC
                """,
                (user_id, trading_date),
            )
            versions = cursor.fetchall()

            cursor.execute(
                """
                SELECT account_id, account_reference
                FROM portfolio_accounts
                WHERE user_id = %s
                """,
                (user_id,),
            )
            accounts = cursor.fetchall()

    if not accounts:
        raise ValueError("No portfolio accounts found for this user")

    covered = {version["account_id"] for version in versions}
    missing = [
        account["account_reference"]
        for account in accounts
        if account["account_id"] not in covered
    ]

    if missing:
        raise ValueError(
            f"No confirmed portfolio on or before {trading_date} "
            f"for accounts: {missing}"
        )

    return [
        get_portfolio_version(
            user_id,
            version["portfolio_version_id"],
        )
        for version in versions
    ]