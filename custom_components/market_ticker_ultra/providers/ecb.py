"""Currency pairs at the European Central Bank's reference rates.

Through Frankfurter, which publishes them: free, no key, made to be asked by
programs. One fixing per working day, around 16:00 Central European Time -
the rate banks and contracts refer to, not a live market rate. A pair is
"EUR/USD": what one euro costs in dollars.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import re
import time

from aiohttp import ClientSession

from ..const import STATE_CLOSED
from . import RANGE_DAYS, History, Listing, Provider, ProviderError, Quote, lead_in
from .http import get_json, number

_BASE = "https://api.frankfurter.dev/v1/"
# The fixing changes once a day; the last days are asked for again at most
# this often, however short the poll.
_TTL = 1800
_PAIR = re.compile(r"^\s*([A-Za-z]{3})\s*[/\-\s]?\s*([A-Za-z]{3})\s*(=[Xx])?\s*$")
# The first day the reference rates exist for.
_FIRST = date(1999, 1, 4)
# How many points a long series is thinned to.
_MAX_POINTS = 400


def split_pair(symbol: str) -> tuple[str, str] | None:
    match = _PAIR.match(symbol or "")
    return (match.group(1).upper(), match.group(2).upper()) if match else None


class EcbProvider(Provider):
    """Reference rates as instruments."""

    key = "ecb"
    label = "ECB reference rate"

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        # The last fixings, oldest first: (day, {currency: per euro}).
        self._days: list[tuple[str, dict[str, float]]] = []
        self._fetched = 0.0

    async def _recent(self) -> list[tuple[str, dict[str, float]]]:
        now = time.monotonic()
        if self._days and now - self._fetched < _TTL:
            return self._days
        start = (datetime.now(UTC).date() - timedelta(days=10)).isoformat()
        try:
            data = await get_json(self._session, self.label, f"{_BASE}{start}..", {"base": "EUR"})
        except ProviderError:
            if self._days:
                return self._days
            raise
        rates = data.get("rates") if isinstance(data, dict) else None
        if not isinstance(rates, dict) or not rates:
            raise ProviderError(f"{self.label} answered without rates")
        days = []
        for day in sorted(rates):
            row = {"EUR": 1.0}
            for code, value in (rates[day] or {}).items():
                rate = number(value)
                if rate:
                    row[str(code).upper()] = rate
            days.append((day, row))
        self._days = days
        self._fetched = now
        return days

    @staticmethod
    def _cross(row: dict[str, float], base: str, quote: str) -> float | None:
        if base not in row or quote not in row:
            return None
        return row[quote] / row[base]

    async def search(self, query: str) -> list[Listing]:
        pair = split_pair(query)
        if pair is None or pair[0] == pair[1]:
            return []
        days = await self._recent()
        if self._cross(days[-1][1], *pair) is None:
            return []
        symbol = f"{pair[0]}/{pair[1]}"
        return [Listing(symbol=symbol, name=symbol, exchange=self.label, type="CURRENCY", source=self.key)]

    async def quotes(self, symbols: list[str]) -> dict[str, Quote]:
        days = await self._recent()
        today_day, today = days[-1]
        before = days[-2][1] if len(days) > 1 else None
        # The fixing is published around 16:00 CET; that is the moment the
        # rate is from.
        fixed = datetime.fromisoformat(today_day).replace(hour=15, tzinfo=UTC)
        result: dict[str, Quote] = {}
        for symbol in symbols:
            pair = split_pair(symbol)
            price = self._cross(today, *pair) if pair else None
            if price is None:
                continue
            previous = self._cross(before, *pair) if before else None
            result[symbol] = Quote(
                symbol=symbol,
                price=round(price, 6),
                currency=pair[1],
                previous_close=None if previous is None else round(previous, 6),
                day_low=None,
                day_high=None,
                year_low=None,
                year_high=None,
                volume=None,
                market_state=STATE_CLOSED,
                quote_time=fixed,
                name=symbol,
                exchange=self.label,
                type="CURRENCY",
                precision=4,
            )
        return result

    async def history(self, symbol: str, range_: str) -> History:
        pair = split_pair(symbol)
        if pair is None:
            raise ProviderError("Not a currency pair")
        today = datetime.now(UTC).date()
        # A day and a week of a daily fixing are a handful of points: the
        # last ten days give a line worth drawing.
        days_back = max(RANGE_DAYS.get(range_, 0), 14)
        shown_from = _FIRST if range_ == "max" else today - timedelta(days=days_back)
        # Three months more, as the lead-in the averages are worked out from.
        start = _FIRST if range_ == "max" else max(_FIRST, shown_from - timedelta(days=95))
        symbols = ",".join(code for code in pair if code != "EUR")
        params = {"base": "EUR"}
        if symbols:
            params["symbols"] = symbols
        data = await get_json(self._session, self.label, f"{_BASE}{start.isoformat()}..", params)
        rates = data.get("rates") if isinstance(data, dict) else None
        if not isinstance(rates, dict) or not rates:
            raise ProviderError(f"{self.label} has no history for this pair")
        points: list[tuple[int, float]] = []
        for day in sorted(rates):
            row = {"EUR": 1.0}
            for code, value in (rates[day] or {}).items():
                rate = number(value)
                if rate:
                    row[str(code).upper()] = rate
            price = self._cross(row, *pair)
            if price is None:
                continue
            stamp = int(datetime.fromisoformat(day).replace(hour=15, tzinfo=UTC).timestamp())
            points.append((stamp, round(price, 6)))
        if not points:
            raise ProviderError(f"{self.label} has no history for this pair")
        step = max(1, len(points) // _MAX_POINTS)
        warmup = 0
        if step > 1:
            # Thinned from the end, so that the last fixing stays.
            points = points[::-1][::step][::-1]
        elif range_ != "max":
            begins = datetime(shown_from.year, shown_from.month, shown_from.day, tzinfo=UTC).timestamp()
            first = next((i for i, (stamp, _) in enumerate(points) if stamp >= begins), len(points) - 1)
            cut, warmup = lead_in(first)
            points = points[cut:]
        closes = [price for _, price in points]
        return History(
            range=range_,
            interval="1d" if step == 1 else f"{step}d",
            currency=pair[1],
            previous_close=None,
            timestamps=[stamp for stamp, _ in points],
            open=list(closes),
            high=list(closes),
            low=list(closes),
            close=closes,
            volume=[None] * len(points),
            session=None,
            warmup=warmup,
        )
