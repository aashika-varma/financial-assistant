from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class MarketQuote(BaseModel):
    """One stock's end-of-day market observation."""

    symbol: str = Field(min_length=1)
    date: date

    open: Decimal = Field(gt=0, allow_inf_nan=False)
    high: Decimal = Field(gt=0, allow_inf_nan=False)
    low: Decimal = Field(gt=0, allow_inf_nan=False)
    close: Decimal = Field(gt=0, allow_inf_nan=False)
    prev_close: Decimal = Field(gt=0, allow_inf_nan=False)

    pct_change: Decimal = Field(allow_inf_nan=False)
    volume: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def validate_price_range(self) -> "MarketQuote":
        if self.low > self.high:
            raise ValueError("low cannot exceed high")

        if not self.low <= self.open <= self.high:
            raise ValueError("open must fall between low and high")

        if not self.low <= self.close <= self.high:
            raise ValueError("close must fall between low and high")

        return self


class BhavcopyQuote(MarketQuote):
    """A market quote with security identifiers from the CSV."""

    exchange: str = Field(default="NSE", pattern=r"^NSE$")
    series: str = Field(default="EQ", pattern=r"^EQ$")
    isin: str = Field(
        pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$"
    )