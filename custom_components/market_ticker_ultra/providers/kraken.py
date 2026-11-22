"""Coins from Kraken's public market data.

An official, documented API that needs no key for prices: the pairs a coin
trades in, their ticker and their candles. A symbol is Kraken's own name for
a pair without its slash, "XBTEUR"; a person reads "BTC/EUR".
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
import time
from typing import Any

from aiohttp import ClientSession

from ..const import STATE_OPEN
from . import RANGE_DAYS, History, Listing, Provider, ProviderError, Quote, lead_in
from .http import get_json, number

_BASE = "https://api.kraken.com/0/public/"
# The list of pairs changes when Kraken lists a coin; a day is fresh enough.
_PAIRS_TTL = 24 * 3600
# Kraken's own names for two coins the rest of the world calls otherwise.
_ALIASES = {"XBT": "BTC", "XDG": "DOGE"}
# The currencies a coin is offered in here, in this order.
_FIAT = ("EUR", "USD", "CHF", "GBP")
# Bases that are currencies, not coins.
_NOT_COINS = frozenset({"EUR", "USD", "CHF", "GBP", "AUD", "CAD", "JPY"})
_QUERY = re.compile(r"^\s*([A-Za-z0-9]{2,10})\s*(?:[/\-\s]\s*([A-Za-z]{3,4}))?\s*$")
# The candle each range is drawn with, in minutes. Kraken hands out the last
# 720 candles of a size and no more, which is what bounds the long ranges.
_CANDLES = {"1d": 5, "5d": 30, "1mo": 240, "3mo": 1440, "6mo": 1440, "1y": 10080, "5y": 10080, "max": 10080}
_INTERVAL_NAMES = {5: "5m", 30: "30m", 240: "4h", 1440: "1d", 10080: "1wk"}


def _common(code: str) -> str:
    """A currency or coin code the way it is usually written."""
    code = code.upper()
    # Kraken's old four-letter names: "XXBT", "ZEUR".
    if len(code) == 4 and code[0] in "XZ":
        code = code[1:]
    return _ALIASES.get(code, code)


class KrakenProvider(Provider):
    """Coin prices from Kraken."""

    key = "kraken"
    label = "Kraken"

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        # Every pair by its symbol: Kraken's key for it, base and quote as
        # commonly written, and the decimals it is quoted in.
        self._pairs: dict[str, dict[str, Any]] = {}
        self._fetched = 0.0

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        data = await get_json(self._session, self.label, _BASE + path, params)
        if not isinstance(data, dict):
            raise ProviderError(f"{self.label} answered with something unexpected")
        if data.get("error"):
            raise ProviderError(f"{self.label}: {', '.join(map(str, data['error']))}")
        return data.get("result") or {}

    async def pairs(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        if self._pairs and now - self._fetched < _PAIRS_TTL:
            return self._pairs
        try:
            listed = await self._get("AssetPairs")
        except ProviderError:
            if self._pairs:
                return self._pairs
            raise
        pairs: dict[str, dict[str, Any]] = {}
        for key, item in listed.items():
            symbol = item.get("altname")
            if not symbol or item.get("status") not in (None, "online"):
                continue
            pairs[symbol] = {
                "key": key,
                "base": _common(item.get("base") or ""),
                "quote": _common(item.get("quote") or ""),
                "decimals": item.get("pair_decimals"),
            }
        if not pairs:
            raise ProviderError(f"{self.label} listed no pairs")
        self._pairs = pairs
        self._fetched = now
        return pairs

    async def symbol_for(self, base: str, quote: str) -> str | None:
        """Kraken's symbol for a coin in a currency, if it trades it."""
        base, quote = base.upper(), quote.upper()
        for symbol, pair in (await self.pairs()).items():
            if pair["base"] == base and pair["quote"] == quote:
                return symbol
        return None

    @staticmethod
    def _name(pair: dict[str, Any]) -> str:
        return f"{pair['base']}/{pair['quote']}"

    async def search(self, query: str) -> list[Listing]:
        match = _QUERY.match(query or "")
        if not match:
            return []
        base = _ALIASES.get(match.group(1).upper(), match.group(1).upper())
        wanted = match.group(2).upper() if match.group(2) else None
        # "BTCEUR" in one word.
        glued = None
        if wanted is None and len(base) > 5:
            for fiat in _FIAT:
                if base.endswith(fiat):
                    glued = (_ALIASES.get(base[: -len(fiat)], base[: -len(fiat)]), fiat)
        found = []
        for symbol, pair in (await self.pairs()).items():
            if pair["quote"] not in _FIAT:
                continue
            if pair["base"] in _NOT_COINS:
                # Kraken trades currencies against each other too; those
                # are the reference rate's, not a coin.
                continue
            if glued:
                if (pair["base"], pair["quote"]) != glued:
                    continue
            elif pair["base"] != base or (wanted and pair["quote"] != wanted):
                continue
            found.append(
                Listing(symbol=symbol, name=self._name(pair), exchange=self.label, type="CRYPTOCURRENCY", source=self.key)
            )
        found.sort(key=lambda listing: _FIAT.index(listing.name.split("/")[1]))
        return found

    async def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        pairs = await self.pairs()
        known = {symbol: pairs[symbol] for symbol in symbols if symbol in pairs}
        if not known:
            return {}
        ticker = await self._get("Ticker", {"pair": ",".join(known)})
        now = datetime.now(UTC)
        result: dict[str, Quote] = {}
        for symbol, pair in known.items():
            row = ticker.get(pair["key"]) or ticker.get(symbol)
            if not row:
                continue
            price = number((row.get("c") or [None])[0])
            if price is None:
                continue
            volume = number((row.get("v") or [None, None])[1])
            decimals = pair["decimals"]
            result[symbol] = Quote(
                symbol=symbol,
                price=price,
                currency=pair["quote"],
                # A coin has no close. Kraken's "o" is the price the day
                # began with at midnight UTC, which is what the change of
                # the day is measured from.
                previous_close=number(row.get("o")),
                day_low=number((row.get("l") or [None])[0]),
                day_high=number((row.get("h") or [None])[0]),
                year_low=None,
                year_high=None,
                volume=None if volume is None else int(volume),
                market_state=STATE_OPEN,
                quote_time=now,
                name=self._name(pair),
                exchange=self.label,
                type="CRYPTOCURRENCY",
                precision=decimals if isinstance(decimals, int) and 0 <= decimals <= 8 else 2,
            )
        return result

    async def history(self, symbol: str, range_: str) -> History:
        pairs = await self.pairs()
        pair = pairs.get(symbol)
        if pair is None:
            raise ProviderError(f"{self.label} does not list this pair")
        minutes = _CANDLES[range_]
        data = await self._get("OHLC", {"pair": symbol, "interval": str(minutes)})
        rows = next((value for key, value in data.items() if key != "last"), None)
        if not rows:
            raise ProviderError(f"{self.label} has no history for this pair")
        rows = [row for row in rows if len(row) >= 7]
        days = RANGE_DAYS.get(range_)
        earliest = time.time() - days * 86400 if days else 0
        # Kraken hands out its last 720 candles whatever is asked: the ones
        # from before the period are the series' lead-in.
        first = next((i for i, row in enumerate(rows) if row[0] >= earliest), len(rows))
        start, warmup = lead_in(first) if days else (0, 0)
        timestamps: list[int] = []
        series: dict[str, list[float | None]] = {"open": [], "high": [], "low": [], "close": []}
        volume: list[int | None] = []
        for row in rows[start:]:
            timestamps.append(int(row[0]))
            for index, name in enumerate(("open", "high", "low", "close"), start=1):
                series[name].append(number(row[index]))
            traded = number(row[6])
            volume.append(None if traded is None else int(traded))
        if not timestamps:
            raise ProviderError(f"{self.label} has no history for this pair")
        return History(
            range=range_,
            interval=_INTERVAL_NAMES[minutes],
            currency=pair["quote"],
            previous_close=None,
            timestamps=timestamps,
            open=series["open"],
            high=series["high"],
            low=series["low"],
            close=series["close"],
            volume=volume,
            session=None,
            warmup=warmup,
        )

