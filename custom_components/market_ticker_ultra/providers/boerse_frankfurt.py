"""Xetra and the Frankfurt floor, from Deutsche Börse's own website.

The interface behind live.deutsche-boerse.com: not a documented API, but
the exchange's own data, in euros, found by ISIN. Its terms allow the free
use of its price data as long as it is not sold on. A symbol is the venue
and the ISIN, "XETR:DE0007236101".
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import time
from zoneinfo import ZoneInfo

from aiohttp import ClientSession

from ..const import STATE_CLOSED, STATE_OPEN
from . import RANGE_DAYS, History, Listing, Provider, ProviderError, Quote, lead_in
from .http import get_json, number

_BASE = "https://api.live.deutsche-boerse.com/v1/"
_BERLIN = ZoneInfo("Europe/Berlin")
_VENUES = {"XETR": "Xetra", "XFRA": "Frankfurt"}
# The exchange's words for what an instrument is.
_TYPES = {"aktie": "EQUITY", "etp": "ETF", "etf": "ETF", "fonds": "MUTUALFUND", "index": "INDEX", "anleihe": "BOND"}
# The bar each range is drawn with, as the interface names it. It has no
# bar finer than a quarter of an hour.
_BARS = {"1d": "15", "5d": "60", "1mo": "1D", "3mo": "1D", "6mo": "1D", "1y": "1W", "5y": "1W", "max": "1M"}
_INTERVAL_NAMES = {"15": "15m", "60": "1h", "1D": "1d", "1W": "1wk", "1M": "1mo"}
# Between two instruments of one poll: each is a request of its own.
_PAUSE = 0.2


def _split(symbol: str) -> tuple[str, str] | None:
    mic, _, isin = (symbol or "").partition(":")
    return (mic, isin) if mic in _VENUES and isin else None


class BoerseFrankfurtProvider(Provider):
    """Quotes from Xetra and the Frankfurt floor."""

    key = "boerse_frankfurt"
    label = "Börse Frankfurt"

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def search(self, query: str) -> list[Listing]:
        data = await get_json(
            self._session, self.label, _BASE + "tradingview/search", {"query": query.strip(), "limit": "10"}
        )
        found = []
        for item in data if isinstance(data, list) else []:
            symbol = item.get("symbol")
            if not symbol or _split(symbol) is None:
                continue
            found.append(
                Listing(
                    symbol=symbol,
                    name=item.get("description") or symbol,
                    exchange=item.get("exchange") or _VENUES[_split(symbol)[0]],
                    type=_TYPES.get(str(item.get("type") or "").lower(), ""),
                    source=self.key,
                )
            )
        return found

    async def _quote(self, symbol: str) -> Quote | None:
        mic, isin = _split(symbol)
        data = await get_json(
            self._session, self.label, _BASE + "data/price_information/single", {"isin": isin, "mic": mic}
        )
        price = number(data.get("lastPrice")) if isinstance(data, dict) else None
        if not price:
            return None
        traded = None
        try:
            traded = datetime.fromisoformat(str(data.get("timestampLastPrice")))
        except ValueError:
            pass
        currency = data.get("currency")
        if isinstance(currency, dict):
            currency = currency.get("originalValue")
        pieces = number(data.get("turnoverInPieces"))
        return Quote(
            symbol=symbol,
            price=price,
            currency=currency or "EUR",
            previous_close=number(data.get("closingPricePrevTradingDay")),
            day_low=number(data.get("dayLow")),
            day_high=number(data.get("dayHigh")),
            year_low=number(data.get("weeks52Low")),
            year_high=number(data.get("weeks52High")),
            volume=None if pieces is None else int(pieces),
            market_state=_state(data, traded),
            quote_time=traded,
            name=None,
            exchange=_VENUES[mic],
            type=None,
            precision=2 if price >= 1 else 4,
        )

    async def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        result: dict[str, Quote] = {}
        failure: ProviderError | None = None
        for index, symbol in enumerate(symbols):
            if _split(symbol) is None:
                continue
            if index:
                await asyncio.sleep(_PAUSE)
            try:
                quote = await self._quote(symbol)
            except ProviderError as err:
                failure = err
                continue
            if quote is not None:
                result[symbol] = quote
        if not result and failure is not None:
            raise failure
        return result

    async def history(self, symbol: str, range_: str) -> History:
        if _split(symbol) is None:
            raise ProviderError("Not a Börse Frankfurt instrument")
        bar = _BARS[range_]
        now = int(time.time())
        days = RANGE_DAYS.get(range_)
        # More than the period: a day reaches back over a long weekend, so
        # that Monday morning still has Friday to show, and every range
        # brings bars from before it along (see History.warmup).
        shown_from = now - days * 86400 if days else 0
        extra = {"1d": 6, "5d": 12}.get(range_, 95 if bar == "1D" else 460)
        start = shown_from - extra * 86400 if days else 0
        data = await get_json(
            self._session,
            self.label,
            _BASE + "tradingview/history",
            {"symbol": symbol, "resolution": bar, "from": str(start), "to": str(now)},
        )
        if not isinstance(data, dict) or data.get("s") != "ok" or not data.get("t"):
            raise ProviderError(f"{self.label} has no history for this instrument")
        timestamps = [int(t) for t in data["t"]]
        if range_ in ("1d", "5d"):
            # The last day there was trading on - or the last five: trading
            # days, not days of the calendar, which would make a week of
            # three days after a weekend.
            dates = [datetime.fromtimestamp(t, _BERLIN).date() for t in timestamps]
            wanted = sorted(set(dates))[-(1 if range_ == "1d" else 5) :]
            first = dates.index(wanted[0])
        else:
            first = next((i for i, t in enumerate(timestamps) if t >= shown_from), len(timestamps) - 1)
        cut, warmup = lead_in(first) if days else (0, 0)
        keep = range(cut, len(timestamps))

        def series(key: str) -> list[float | None]:
            values = data.get(key) or []
            return [number(values[i]) if i < len(values) else None for i in keep]

        raw_volume = data.get("v") or []
        volume: list[int | None] = []
        for i in keep:
            traded = number(raw_volume[i]) if i < len(raw_volume) else None
            volume.append(None if traded is None else int(traded))
        return History(
            range=range_,
            interval=_INTERVAL_NAMES[bar],
            currency="EUR",
            previous_close=None,
            timestamps=[timestamps[i] for i in keep],
            open=series("o"),
            high=series("h"),
            low=series("l"),
            close=series("c"),
            volume=volume,
            session=None,
            warmup=warmup,
        )


def _state(data: dict, traded: datetime | None) -> str:
    """Open between the venue's trading hours, on a day it has traded."""
    now = datetime.now(_BERLIN)
    try:
        opens = datetime.strptime(str(data.get("tradingTimeStart")), "%H:%M:%S").time()
        closes = datetime.strptime(str(data.get("tradingTimeEnd")), "%H:%M:%S").time()
    except ValueError:
        return STATE_CLOSED
    if not opens <= now.time() < closes:
        return STATE_CLOSED
    if traded is None or traded.astimezone(_BERLIN).date() != now.date():
        return STATE_CLOSED
    return STATE_OPEN
