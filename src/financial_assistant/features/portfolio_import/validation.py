import re
from datetime import date
from decimal import Decimal, InvalidOperation

from psycopg.rows import dict_row

from financial_assistant.schemas.portfolio_import import PortfolioImportDraft
from financial_assistant.storage.database import get_connection


def validate_and_resolve(draft: PortfolioImportDraft) -> dict:
    errors = []
    candidates = []

    try:
        holdings_date = date.fromisoformat(draft.holdings_as_of or "")
    except ValueError:
        holdings_date = None
        errors.append("Missing or invalid holdings-as-of date")

    if not draft.accounts:
        errors.append("No accounts were extracted")

    seen_accounts = set()

    for account in draft.accounts:
        account_ref = (account.account_reference or "").strip()

        if not account_ref:
            errors.append("An account is missing its reference")
            continue

        if account_ref in seen_accounts:
            errors.append(f"Duplicate account: {account_ref}")
            continue

        seen_accounts.add(account_ref)
        seen_isins = set()

        if not account.holdings:
            errors.append(
                f"{account_ref}: empty holdings require manual review"
            )

        for holding in account.holdings:
            isin = (holding.isin or "").strip().upper()

            if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
                errors.append(
                    f"{account_ref}: invalid ISIN for "
                    f"{holding.security_name}"
                )
                continue

            if isin in seen_isins:
                errors.append(f"{account_ref}: duplicate ISIN {isin}")
                continue

            seen_isins.add(isin)

            try:
                quantity = Decimal(holding.quantity or "")
            except (InvalidOperation, ValueError):
                errors.append(f"{account_ref}: invalid quantity for {isin}")
                continue

            if not quantity.is_finite() or quantity <= 0:
                errors.append(
                    f"{account_ref}: quantity must be positive for {isin}"
                )
                continue

            candidates.append({
                "account_reference": account_ref,
                "isin": isin,
                "quantity": quantity,
                "security_name": holding.security_name,
                "source_page": holding.source_page,
                "extracted_evidence": holding.evidence,
            })

    isins = sorted({item["isin"] for item in candidates})
    instruments = {}

    if isins:
        with get_connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT instrument_id, isin, symbol, exchange, series
                    FROM instruments
                    WHERE isin = ANY(%s)
                      AND exchange = 'NSE'
                      AND series = 'EQ'
                    """,
                    (isins,),
                )

                for row in cursor.fetchall():
                    instruments.setdefault(row["isin"], []).append(row)

    resolved = []

    for item in candidates:
        matches = instruments.get(item["isin"], [])

        if len(matches) != 1:
            errors.append(
                f"{item['account_reference']}: {item['isin']} has "
                f"{len(matches)} matching NSE EQ instruments"
            )
            continue

        if item["quantity"] != item["quantity"].to_integral_value():
            errors.append(
                f"{item['account_reference']}: fractional equity quantity "
                f"for {item['isin']} requires review in this MVP"
            )
            continue

        resolved.append({
            **item,
            **matches[0],
            "quantity": str(item["quantity"]),
        })

    return {
        "status": "needs_correction" if errors else "ready_for_review",
        "holdings_as_of": (
            holdings_date.isoformat() if holdings_date else None
        ),
        "holdings": resolved,
        "errors": errors,
        "warnings": draft.warnings,
        "evidence_verification": "not_performed",
    }