from pydantic import BaseModel, ConfigDict, Field


class ExtractedHolding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    security_name: str
    isin: str | None
    quantity: str | None = Field(
        description=(
            "Closing total holding quantity as a decimal string "
            "without commas; null if unclear."
        )
    )
    source_page: int
    evidence: str = Field(
        description="Short verbatim excerpt supporting this holding."
    )


class ExtractedAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_reference: str | None
    holdings: list[ExtractedHolding]


class PortfolioImportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    holdings_as_of: str | None = Field(
        description="Explicit holdings date in YYYY-MM-DD format."
    )
    accounts: list[ExtractedAccount]
    warnings: list[str]