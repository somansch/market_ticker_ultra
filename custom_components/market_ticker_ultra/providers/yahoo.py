"""Yahoo Finance, through the public endpoints its own website uses.

Not an official API: Yahoo may change or close these at any time, and its
terms reserve the data for personal use. What is asked here are the two
endpoints that answer without a cookie:

- "spark" quotes a batch of symbols in one request, and
- "search" finds instruments by name, symbol or ISIN.

The cookie-and-crumb endpoints (v7 quote, quoteSummary) are deliberately
not used for any of that. They are the ones that fail behind Europe's
consent wall and that break every few months.

One thing only they have: the day the next quarterly figures are due.
"earnings" asks them for it, and for nothing else - when they fail, that
one date is missing, and everything above goes on as before.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import re
import time
from typing import Any
from urllib.parse import quote as quote_plus

from aiohttp import ClientError, ClientSession, ClientTimeout

from ..const import STATE_CLOSED, STATE_OPEN, STATE_POST, STATE_PRE
from . import (
    RANGE_DAYS,
    Details,
    History,
    Listing,
    Provider,
    ProviderError,
    Quote,
    RateLimited,
    lead_in,
)

_LOGGER = logging.getLogger(__name__)

_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/spark"
_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"
_FUNDAMENTALS_URL = (
    "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/"
)

# The bar each range is drawn with: fine enough for a chart some hundred
# pixels wide, and no finer.
_INTERVALS = {
    "1d": "5m",
    "5d": "30m",
    "1mo": "1d",
    "3mo": "1d",
    "6mo": "1d",
    "1y": "1wk",
    "5y": "1wk",
    "max": "1mo",
}
# What is asked for to show each range: the next longer one in the same
# bars, so that the series has bars from before its period (see
# History.warmup). "max" has nothing before it.
_FETCH = {"1d": "5d", "5d": "1mo", "1mo": "3mo", "3mo": "6mo", "6mo": "1y", "1y": "2y", "5y": "10y", "max": "max"}
_TIMEOUT = ClientTimeout(total=20)
# The calendar's endpoint, and where its cookie and its crumb come from.
_COOKIE_URL = "https://fc.yahoo.com"
_CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
_SUMMARY_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
# How long a cookie and its crumb are used, in seconds.
_PASS_TTL = 6 * 3600
# A name of its own: the client library's default one is answered with 429.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MarketTickerUltra; +https://github.com/somansch/market_ticker_ultra)"
}
# What one request may carry. Yahoo answers more, but a batch this size
# keeps the address short and one bad symbol from costing too many others.
_BATCH = 20

_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
# What a symbol can look like: no blanks, and short.
_SYMBOL = re.compile(r"^[A-Za-z0-9^.=-]{1,20}$")

# Venues that quote in a hundredth of their currency. A sensor's unit is the
# currency itself, so the figures are brought to it.
_MINOR_UNITS = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}


def is_isin(text: str) -> bool:
    return bool(_ISIN.match(text.strip().upper()))


class YahooProvider(Provider):
    """Quotes and search from Yahoo Finance."""

    key = "yahoo"
    label = "Yahoo Finance"

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        # The cookie and the crumb the calendar is asked with, and when
        # they were fetched.
        self._pass: tuple[float, str, str] | None = None

    async def _get(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            async with self._session.get(
                url, params=params, headers=_HEADERS, timeout=_TIMEOUT
            ) as response:
                if response.status == 429:
                    raise RateLimited("Yahoo asked for a break (HTTP 429)")
                if response.status >= 400:
                    raise ProviderError(f"Yahoo answered HTTP {response.status}")
                data = await response.json(content_type=None)
        except TimeoutError as err:
            raise ProviderError("Yahoo did not answer in time") from err
        except ClientError as err:
            raise ProviderError(f"Yahoo could not be reached: {err}") from err
        except ValueError as err:
            raise ProviderError("Yahoo answered with something that is not JSON") from err
        if not isinstance(data, dict):
            raise ProviderError("Yahoo answered with something unexpected")
        return data

    # ------------------------------------------------------------- search

    async def _search_once(self, query: str) -> list[Listing]:
        data = await self._get(
            _SEARCH_URL, {"q": query, "quotesCount": "15", "newsCount": "0"}
        )
        found = []
        for item in data.get("quotes") or []:
            symbol = item.get("symbol")
            if not symbol or not item.get("isYahooFinance", True):
                continue
            found.append(
                Listing(
                    symbol=symbol,
                    name=item.get("longname") or item.get("shortname") or symbol,
                    exchange=item.get("exchDisp") or item.get("exchange") or "",
                    type=item.get("quoteType") or "",
                )
            )
        return found

    async def search(self, query: str) -> list[Listing]:
        """Instruments matching a name, a symbol or an ISIN.

        An ISIN is answered with one venue only - for a fund listed all over
        Europe often not the one that is wanted. Asking again with the name
        that came back brings the other venues of the same instrument.
        """
        query = query.strip()
        found = await self._search_once(query.upper() if is_isin(query) else query)
        if found and is_isin(query):
            try:
                more = await self._search_once(found[0].name)
            except ProviderError:
                more = []
            known = {listing.symbol for listing in found}
            first = found[0]
            found += [
                listing
                for listing in more
                if listing.symbol not in known and listing.type == first.type
            ]
        elif _SYMBOL.match(query) and query.upper() not in {
            listing.symbol.upper() for listing in found
        }:
            # A symbol typed exactly is not always among what the search
            # returns - "BZ=F" brought a fund, not Brent. If it quotes, it
            # exists, and comes first.
            try:
                quoted = await self.quotes([query.upper()])
            except ProviderError:
                quoted = {}
            for symbol, quote in quoted.items():
                found.insert(
                    0,
                    Listing(
                        symbol=symbol,
                        name=quote.name or symbol,
                        exchange=quote.exchange or "",
                        type=quote.type or "",
                    ),
                )
        return found

    # ------------------------------------------------------------- quotes

    async def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """The current quote of every symbol that Yahoo knows."""
        result: dict[str, Quote] = {}
        for start in range(0, len(symbols), _BATCH):
            batch = symbols[start : start + _BATCH]
            data = await self._get(
                _QUOTE_URL,
                {"symbols": ",".join(batch), "range": "1d", "interval": "1d"},
            )
            for item in (data.get("spark") or {}).get("result") or []:
                try:
                    meta = item["response"][0]["meta"]
                except (KeyError, IndexError, TypeError):
                    continue
                quote = _quote_from_meta(meta)
                if quote is not None:
                    result[item.get("symbol") or quote.symbol] = quote
        return result


    # ------------------------------------------------------------ history

    async def history(self, symbol: str, range_: str) -> History:
        """The price series of one symbol over one of RANGES."""
        interval = _INTERVALS[range_]
        data = await self._get(
            _CHART_URL + quote_plus(symbol),
            {"range": _FETCH[range_], "interval": interval, "includePrePost": "false"},
        )
        chart = data.get("chart") or {}
        result = (chart.get("result") or [None])[0]
        if not result:
            error = (chart.get("error") or {}).get("description")
            raise ProviderError(error or "Yahoo has no history for this instrument")

        meta = result.get("meta") or {}
        currency = meta.get("currency")
        factor = 1.0
        if currency in _MINOR_UNITS:
            currency = _MINOR_UNITS[currency]
            factor = 0.01
        bars = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        stamps = [int(t) for t in result.get("timestamp") or []]

        # More was asked for than the range shows. Where the range begins:
        # a day is the last day there are bars of, by the venue's own
        # calendar; a week the last five such days; the others so many days
        # back from now.
        offset = int(_number(meta.get("gmtoffset")) or 0)
        first = 0
        if stamps and range_ in ("1d", "5d"):
            days = [(t + offset) // 86400 for t in stamps]
            wanted = sorted(set(days))[-(1 if range_ == "1d" else 5) :]
            first = days.index(wanted[0])
        elif stamps and range_ in RANGE_DAYS:
            earliest = datetime.now(UTC).timestamp() - RANGE_DAYS[range_] * 86400
            first = next((i for i, t in enumerate(stamps) if t >= earliest), len(stamps) - 1)
        start, warmup = lead_in(first)
        timestamps = stamps[start:]

        def series(key: str) -> list[float | None]:
            values = bars.get(key) or []
            out: list[float | None] = []
            for index in range(start, len(stamps)):
                value = _number(values[index]) if index < len(values) else None
                out.append(None if value is None else round(value * factor, 6))
            return out

        raw_volume = bars.get("volume") or []
        volume: list[int | None] = []
        for index in range(start, len(stamps)):
            value = _number(raw_volume[index]) if index < len(raw_volume) else None
            volume.append(None if value is None else int(value))

        session = None
        regular = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
        if range_ == "1d" and regular.get("start") and regular.get("end"):
            session = (int(regular["start"]), int(regular["end"]))

        # The close before the first bar that came - which, with bars from
        # before the period in the series, is not the close before the
        # period. Only where there are none it is.
        previous = _number(meta.get("chartPreviousClose")) if not warmup else None
        return History(
            range=range_,
            interval=interval,
            currency=currency,
            previous_close=None if previous is None else round(previous * factor, 6),
            timestamps=timestamps,
            open=series("open"),
            high=series("high"),
            low=series("low"),
            close=series("close"),
            volume=volume,
            session=session,
            warmup=warmup,
        )

    # ----------------------------------------------------------- earnings

    async def listing_for_isin(self, isin: str) -> tuple[str, str] | None:
        """What Yahoo calls the instrument with this ISIN, and what kind of
        instrument it is - at whichever venue it names first: a company's
        calendar and its news are the same at all of them. None where
        Yahoo does not know the ISIN."""
        for listing in await self._search_once(isin.strip().upper()):
            return listing.symbol, (listing.type or "").upper()
        return None

    async def _crumb(self, fresh: bool = False) -> tuple[str, str] | None:
        """The cookie and the crumb Yahoo wants with a calendar request -
        kept for some hours - or None where it gives none."""
        now = time.monotonic()
        if not fresh and self._pass and now - self._pass[0] < _PASS_TTL:
            return self._pass[1], self._pass[2]
        try:
            async with self._session.get(
                _COOKIE_URL, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=False
            ) as response:
                cookie = "; ".join(
                    f"{morsel.key}={morsel.value}" for morsel in response.cookies.values()
                )
            if not cookie:
                return None
            async with self._session.get(
                _CRUMB_URL, headers={**_HEADERS, "Cookie": cookie}, timeout=_TIMEOUT
            ) as response:
                if response.status != 200:
                    return None
                crumb = (await response.text()).strip()
        except (TimeoutError, ClientError, UnicodeDecodeError):
            return None
        # A page instead of a crumb is no crumb.
        if not crumb or len(crumb) > 40 or any(sign in crumb for sign in " <>{}"):
            return None
        self._pass = (now, cookie, crumb)
        return cookie, crumb

    async def earnings(self, symbol: str) -> dict[str, Any]:
        """When the next quarterly figures are due: the day - or, where
        Yahoo names a span, its first and last day - and whether Yahoo only
        estimates it. Empty where there is no such day, or Yahoo does not
        say: never an error."""
        data: Any = None
        for fresh in (False, True):
            passed = await self._crumb(fresh)
            if passed is None:
                return {}
            cookie, crumb = passed
            try:
                async with self._session.get(
                    _SUMMARY_URL + quote_plus(symbol),
                    params={"modules": "calendarEvents", "crumb": crumb},
                    headers={**_HEADERS, "Cookie": cookie},
                    timeout=_TIMEOUT,
                ) as response:
                    # A crumb that has run out: once more with a new one.
                    if response.status in (401, 403) and not fresh:
                        continue
                    if response.status >= 400:
                        return {}
                    data = await response.json(content_type=None)
            except (TimeoutError, ClientError, ValueError):
                return {}
            break
        try:
            calendar = data["quoteSummary"]["result"][0]["calendarEvents"]["earnings"]
        except (KeyError, IndexError, TypeError):
            return {}
        today = datetime.now(UTC).date()
        days = []
        for entry in calendar.get("earningsDate") or []:
            raw = _number((entry or {}).get("raw"))
            if raw is None:
                continue
            day = datetime.fromtimestamp(raw, UTC).date()
            if day >= today:
                days.append(day)
        if not days:
            return {}
        days.sort()
        return {
            "earnings_date": days[0].isoformat(),
            "earnings_date_end": days[-1].isoformat() if days[-1] != days[0] else None,
            "earnings_estimate": calendar.get("isEarningsDateEstimate") is True,
        }

    # ------------------------------------------------------------ details

    async def details(self, symbol: str) -> Details:
        """Market capitalisation, price/earnings and earnings per share.

        From the one endpoint that gives them without a cookie. Its figures
        are those of the last close; a fund, an index, a future or a
        currency comes back empty, which is an answer and not an error.
        """
        now = int(datetime.now(UTC).timestamp())
        data = await self._get(
            _FUNDAMENTALS_URL + quote_plus(symbol),
            {
                "type": "trailingMarketCap,trailingPeRatio,trailingDilutedEPS",
                "period1": str(now - 86400 * 550),
                "period2": str(now),
            },
        )
        latest: dict[str, tuple[str | None, float | None]] = {}
        for item in (data.get("timeseries") or {}).get("result") or []:
            kind = ((item.get("meta") or {}).get("type") or [None])[0]
            values = [value for value in item.get(kind) or [] if value]
            if not kind or not values:
                continue
            last = values[-1]
            latest[kind] = (
                last.get("asOfDate"),
                _number((last.get("reportedValue") or {}).get("raw")),
            )

        def figure(kind: str) -> float | None:
            return latest.get(kind, (None, None))[1]

        return Details(
            market_cap=figure("trailingMarketCap"),
            pe=figure("trailingPeRatio"),
            eps=figure("trailingDilutedEPS"),
            as_of=latest.get("trailingMarketCap", (None, None))[0],
        )


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _market_state(meta: dict[str, Any], quote_time: float | None, now: float) -> str:
    """Open, closed, or before/after hours - from the day's trading periods.

    The periods are the venue's timetable, and a timetable does not know a
    holiday. "Open" therefore also asks for a price from this session.
    """
    periods = meta.get("currentTradingPeriod") or {}

    def inside(name: str) -> bool:
        period = periods.get(name) or {}
        start, end = period.get("start"), period.get("end")
        return bool(start and end and start <= now < end)

    regular = periods.get("regular") or {}
    if inside("regular"):
        if quote_time is None or quote_time >= (regular.get("start") or 0):
            return STATE_OPEN
        return STATE_CLOSED
    if inside("pre"):
        return STATE_PRE
    if inside("post"):
        return STATE_POST
    return STATE_CLOSED


def _quote_from_meta(meta: dict[str, Any]) -> Quote | None:
    price = _number(meta.get("regularMarketPrice"))
    symbol = meta.get("symbol")
    if price is None or not symbol:
        return None

    currency = meta.get("currency")
    factor = 1.0
    if currency in _MINOR_UNITS:
        currency = _MINOR_UNITS[currency]
        factor = 0.01

    def money(key: str) -> float | None:
        value = _number(meta.get(key))
        # Rounded, since a hundredth as a binary fraction leaves a tail
        # (108.49000000000001).
        return None if value is None else round(value * factor, 6)

    previous = money("chartPreviousClose")
    if previous is None:
        previous = money("previousClose")
    traded = _number(meta.get("regularMarketTime"))
    now = datetime.now(UTC).timestamp()
    volume = _number(meta.get("regularMarketVolume"))
    hint = meta.get("priceHint")
    return Quote(
        symbol=symbol,
        price=round(price * factor, 6),
        currency=currency,
        previous_close=previous,
        day_low=money("regularMarketDayLow"),
        day_high=money("regularMarketDayHigh"),
        year_low=money("fiftyTwoWeekLow"),
        year_high=money("fiftyTwoWeekHigh"),
        volume=int(volume) if volume is not None else None,
        market_state=_market_state(meta, traded, now),
        quote_time=datetime.fromtimestamp(traded, UTC) if traded else None,
        name=meta.get("longName") or meta.get("shortName"),
        exchange=meta.get("fullExchangeName") or meta.get("exchangeName"),
        type=meta.get("instrumentType"),
        precision=hint if isinstance(hint, int) and 0 <= hint <= 8 else 2,
    )
