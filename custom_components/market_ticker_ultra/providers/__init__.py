"""The sources quotes come from, behind one shape.

A source searches for instruments, quotes a batch of them, hands out a
price series and - where it knows any - a few figures about the company.
Everything above this package works on Listing, Quote, History and Details
alone, so that a source can be added or replaced without the sensors, the
card or the stored instruments noticing.

An instrument is a source and the symbol that source knows it by.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# The ranges a price series can be asked for, the same at every source.
RANGES = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "5y", "max")
# How far back each reaches, in days - for the sources that are asked by
# date rather than by range. "max" is as far as a source goes.
RANGE_DAYS = {"1d": 1, "5d": 5, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "5y": 1827}
# How many bars from before its period a series may bring along. They are
# not drawn: they are what a moving average or an RSI at the chart's left
# edge is worked out from.
WARMUP_BARS = 60


def lead_in(first_shown: int) -> tuple[int, int]:
    """Where a series is cut and how many of its bars are lead-in, given
    the index of the first bar of its period: (start, warmup)."""
    start = max(0, first_shown - WARMUP_BARS)
    return start, first_shown - start


class ProviderError(Exception):
    """A source could not be reached or answered with something unusable."""


class RateLimited(ProviderError):
    """A source asked for a break (HTTP 429)."""


@dataclass(frozen=True, slots=True)
class Listing:
    """One instrument at one trading venue, as a search finds it."""

    symbol: str
    name: str
    exchange: str
    type: str
    source: str = "yahoo"


@dataclass(frozen=True, slots=True)
class Quote:
    """What a source says about one instrument right now."""

    symbol: str
    price: float
    currency: str | None
    previous_close: float | None
    day_low: float | None
    day_high: float | None
    year_low: float | None
    year_high: float | None
    volume: int | None
    market_state: str
    quote_time: datetime | None
    name: str | None
    exchange: str | None
    type: str | None
    precision: int

    @property
    def change(self) -> float | None:
        if self.previous_close is None:
            return None
        return self.price - self.previous_close

    @property
    def change_percent(self) -> float | None:
        if not self.previous_close:
            return None
        return (self.price - self.previous_close) / self.previous_close * 100


@dataclass(frozen=True, slots=True)
class History:
    """A price series of one instrument, bar by bar.

    The lists are of one length; a bar a venue did not trade in has None in
    place of its figures.
    """

    range: str
    interval: str
    currency: str | None
    previous_close: float | None
    timestamps: list[int]
    open: list[float | None]
    high: list[float | None]
    low: list[float | None]
    close: list[float | None]
    volume: list[int | None]
    # The regular session of the day, as (start, end) - for a day's range.
    session: tuple[int, int] | None
    # How many bars at the front lie before the period: there to work
    # averages out from, not to be drawn.
    warmup: int = 0


@dataclass(frozen=True, slots=True)
class Details:
    """What a source knows about the company behind a share. Every figure
    can be missing: a fund, an index, a future or a currency has none."""

    market_cap: float | None
    pe: float | None
    eps: float | None
    as_of: str | None


class Provider:
    """What every source offers. A source leaves out what it does not have:
    no search finds nothing, no details are empty ones."""

    key = ""
    # What the source is called where a person reads it.
    label = ""

    async def search(self, query: str) -> list[Listing]:
        return []

    async def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        raise NotImplementedError

    async def history(self, symbol: str, range_: str) -> History:
        raise ProviderError(f"{self.label} has no price history")

    async def details(self, symbol: str) -> Details:
        return Details(market_cap=None, pe=None, eps=None, as_of=None)
