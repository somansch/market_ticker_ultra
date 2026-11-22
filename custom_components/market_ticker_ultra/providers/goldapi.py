"""Spot prices of precious metals and copper, from gold-api.com.

Free, no key, and its terms allow use by programs. It gives one figure per
metal - the price in US dollars right now - and nothing else: no close of
the day before, so no change of the day, and no history without a key. For
those, the metal's future at Yahoo ("GC=F") is the instrument to add.
"""

from __future__ import annotations

from datetime import UTC, datetime

from aiohttp import ClientSession

from ..const import STATE_OPEN
from . import Listing, Provider, ProviderError, Quote
from .http import get_json, number

_BASE = "https://api.gold-api.com/price/"

# What the source offers, and the words - English and German - a search
# finds each by.
METALS: dict[str, tuple[str, tuple[str, ...]]] = {
    "XAU": ("Gold (spot)", ("gold", "xau")),
    "XAG": ("Silver (spot)", ("silver", "silber", "xag")),
    "XPT": ("Platinum (spot)", ("platinum", "platin", "xpt")),
    "XPD": ("Palladium (spot)", ("palladium", "xpd")),
    "HG": ("Copper (spot)", ("copper", "kupfer", "hg")),
}


class GoldApiProvider(Provider):
    """Spot metal prices in US dollars."""

    key = "goldapi"
    label = "gold-api.com"

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def search(self, query: str) -> list[Listing]:
        word = (query or "").strip().lower()
        return [
            Listing(symbol=symbol, name=name, exchange=self.label, type="COMMODITY", source=self.key)
            for symbol, (name, words) in METALS.items()
            if word in words
        ]

    async def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        result: dict[str, Quote] = {}
        failure: ProviderError | None = None
        for symbol in symbols:
            if symbol not in METALS:
                continue
            try:
                data = await get_json(self._session, self.label, _BASE + symbol)
            except ProviderError as err:
                failure = err
                continue
            price = number(data.get("price")) if isinstance(data, dict) else None
            if price is None:
                continue
            updated = None
            try:
                updated = datetime.fromisoformat(str(data.get("updatedAt")).replace("Z", "+00:00"))
            except ValueError:
                updated = datetime.now(UTC)
            result[symbol] = Quote(
                symbol=symbol,
                price=round(price, 4),
                currency=str(data.get("currency") or "USD"),
                previous_close=None,
                day_low=None,
                day_high=None,
                year_low=None,
                year_high=None,
                volume=None,
                market_state=STATE_OPEN,
                quote_time=updated,
                name=METALS[symbol][0],
                exchange=self.label,
                type="COMMODITY",
                precision=2,
            )
        if not result and failure is not None:
            raise failure
        return result
