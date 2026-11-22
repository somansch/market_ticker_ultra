"""How a portfolio has done over a period, beside an index.

The time-weighted return: the period is cut at every bar of the price
series, each stretch's return is what the holdings gained in it - without
what was bought or sold in it, which is no gain - and the stretches are
chained. So a purchase does not look like a profit, and the figure can be
set beside an index, which nobody pays into either.

Everything is counted in the currency positions are added up in, at the
European Central Bank's reference rate of each day; where no rate of a day
is to be had, at the current one.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import BENCHMARKS, CONF_BENCHMARK, CONF_CURRENCY, SUBENTRY_INSTRUMENT
from .coordinator import Instrument, MarketTickerUltraCoordinator
from .holdings import CONF_LOTS, LOT_DATE, LOT_PRICE, LOT_QUANTITY, clean_lots, in_order
from .providers import History, ProviderError

# The periods a return can be asked for.
PERFORMANCE_RANGES = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "5y", "max")
# The periods drawn bar by bar within a day.
_INTRADAY = ("1d", "5d")
# How long an answer is good for, in seconds: a day's moves on.
_TTL = {"1d": 120, "5d": 300}
_TTL_LONG = 900


def _moment(stamp: int, by_minute: bool) -> str:
    """When a bar is of: its day - or, within a day, its minute. Written so
    that the moments sort as text, and a day sorts before its own minutes:
    a purchase dated a day counts from that day's first bar on."""
    seconds = stamp / 1000 if stamp > 100_000_000_000 else stamp
    when = datetime.fromtimestamp(seconds, UTC)
    return when.strftime("%Y-%m-%dT%H:%M") if by_minute else when.date().isoformat()


def _closes(history: History, by_minute: bool = False) -> list[tuple[str, float]]:
    """A series as (moment, close), oldest first - the lead-in included: it
    says what an instrument cost before the period began."""
    return [
        (_moment(stamp, by_minute), close)
        for stamp, close in zip(history.timestamps, history.close, strict=False)
        if close is not None
    ]


def _shown_days(history: History, by_minute: bool = False) -> list[str]:
    """The moments of the period itself - and the one before it, which the
    period's return is measured from."""
    start = max(0, history.warmup - 1)
    return [_moment(stamp, by_minute) for stamp in history.timestamps[start:]]


class _Series:
    """A series read day by day: the last close on or before a day."""

    def __init__(self, points: list[tuple[str, float]]) -> None:
        self._points = points
        self._at = 0
        self._last: float | None = None

    def on(self, day: str) -> float | None:
        while self._at < len(self._points) and self._points[self._at][0] <= day:
            self._last = self._points[self._at][1]
            self._at += 1
        return self._last


def _moves(lots: Any) -> list[tuple[str | None, float, float]]:
    """The purchases and sales as (day, units, price), in their order - a
    sale never more than what is held, as in holdings.py."""
    held = 0.0
    moves = []
    for lot in in_order(clean_lots(lots)):
        amount = lot[LOT_QUANTITY]
        if amount < 0:
            amount = -min(-amount, held)
        held += amount
        if amount:
            moves.append((lot[LOT_DATE], amount, lot[LOT_PRICE]))
    return moves


def time_weighted(
    days: list[str],
    positions: list[tuple[list[tuple[str | None, float, float]], _Series, _Series | float]],
) -> tuple[list[str], list[float]]:
    """The chained return day by day, in percent, from the first day on
    which anything is held - with the days it covers.

    A position: its purchases and sales, its prices, and its currency's
    rate - a series, or one figure for every day.
    """
    shown: list[str] = []
    series: list[float] = []
    growth = 1.0
    before: float | None = None
    last_day: str | None = None
    for day in days:
        value = flow = 0.0
        for moves, prices, rates in positions:
            price = prices.on(day)
            rate = rates.on(day) if isinstance(rates, _Series) else rates
            if price is None or rate is None:
                continue
            held = sum(units for when, units, _paid in moves if when is None or when <= day)
            value += held * price * rate
            # What came in or went out since the day before: no gain.
            if last_day is not None:
                flow += sum(
                    units * paid * rate
                    for when, units, paid in moves
                    if when is not None and last_day < when <= day
                )
        last_day = day
        if before is None:
            if value > 0:
                before = value
                shown.append(day)
                series.append(0.0)
            continue
        # With nothing held the day before - everything was sold - there is
        # nothing to measure a return on: the chain stands still until the
        # next purchase, and goes on from there.
        if before > 0:
            growth *= (value - flow) / before
        before = value
        shown.append(day)
        series.append((growth - 1) * 100)
    return shown, series


async def async_performance(
    coordinator: MarketTickerUltraCoordinator, entry: ConfigEntry, range_: str
) -> dict[str, Any]:
    """The portfolio's return over the range, day by day, and its index's."""
    cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = coordinator.performances
    key = (entry.entry_id, range_)
    kept = cache.get(key)
    if kept and time.monotonic() - kept[0] < _TTL.get(range_, _TTL_LONG):
        return kept[1]
    by_minute = range_ in _INTRADAY

    base = coordinator.base_currency
    members = [
        (subentry_id, subentry)
        for subentry_id, subentry in entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_INSTRUMENT and clean_lots(subentry.data.get(CONF_LOTS))
    ]

    async def history_of(instrument: Instrument) -> History | None:
        try:
            return await coordinator.async_history(instrument, range_)
        except ProviderError:
            return None

    instruments = [coordinator.instrument(subentry_id) for subentry_id, _ in members]
    histories = await asyncio.gather(
        *(history_of(instrument) for instrument in instruments if instrument is not None)
    )
    by_id = {
        instrument.id: history
        for instrument, history in zip([i for i in instruments if i is not None], histories, strict=True)
    }

    # Each currency's rate, day by day, where the reference rates go back.
    currencies: dict[str, _Series | float | None] = {}

    async def rate_of(currency: str | None) -> _Series | float | None:
        code = (currency or base).upper()
        if code == base.upper():
            return 1.0
        if code not in currencies:
            now = coordinator.rates.convert(1.0, code, base)
            try:
                past = await coordinator.providers["ecb"].history(f"{code}/{base}", range_)
                points = _closes(past)
                currencies[code] = _Series(points) if points else now
            except (ProviderError, KeyError):
                currencies[code] = now
        return currencies[code]

    positions = []
    left_out: list[str] = []
    days: set[str] = set()
    # The moment before its period, of each position: where its return is
    # measured from.
    starts: list[str] = []
    for subentry_id, subentry in members:
        history = by_id.get(subentry_id)
        currency = (history.currency if history else None) or subentry.data.get(CONF_CURRENCY)
        rates = await rate_of(currency)
        if history is None or rates is None or not _closes(history):
            left_out.append(subentry.title)
            continue
        moments = _shown_days(history, by_minute)
        days.update(moments)
        if history.warmup and moments:
            starts.append(moments[0])
        positions.append(
            (_moves(subentry.data.get(CONF_LOTS)), _Series(_closes(history, by_minute)), rates)
        )

    # The index it is set beside, where the group names one.
    symbol = str(entry.options.get(CONF_BENCHMARK) or "").strip().upper()
    index: History | None = None
    if symbol:
        index = await history_of(Instrument(id="", source="yahoo", symbol=symbol, type="INDEX", isin=None))
        if index is not None:
            days.update(_shown_days(index, by_minute))

    # From the latest of those moments on: exchanges close at different
    # hours, and starting earlier would count more than the period for
    # those that close late.
    begin = max(starts) if starts else ""
    timeline = sorted(day for day in days if day >= begin)
    shown, series = time_weighted(timeline, positions) if positions else ([], [])
    compared: list[float | None] | None = None
    if index is not None and shown:
        closes = _Series(_closes(index, by_minute))
        first = closes.on(shown[0])
        compared = []
        for day in shown:
            close = closes.on(day)
            # An index that has no figure yet when the period begins is
            # measured from its first one.
            if not first and close is not None:
                first = close
            compared.append(None if not first or close is None else (close / first - 1) * 100)

    result = {
        "range": range_,
        "currency": base,
        "days": shown,
        "portfolio": [round(value, 3) for value in series],
        "benchmark": None if compared is None else [None if v is None else round(v, 3) for v in compared],
        "benchmark_symbol": symbol or None,
        "benchmark_name": BENCHMARKS.get(symbol, symbol) if symbol else None,
        "return": round(series[-1], 2) if series else None,
        "benchmark_return": (
            round(compared[-1], 2) if compared and compared[-1] is not None else None
        ),
        "left_out": left_out,
    }
    cache[key] = (time.monotonic(), result)
    return result
