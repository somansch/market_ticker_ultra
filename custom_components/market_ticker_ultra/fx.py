"""Reference rates, to add positions in different currencies up to one sum.

From Frankfurter, which publishes the European Central Bank's daily
reference rates: free, no key, made to be asked by programs. One fixing per
working day - which is the right rate for "what is my portfolio worth in
euros", and not a live market rate.
"""

from __future__ import annotations

import logging
import time

from aiohttp import ClientError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

_URL = "https://api.frankfurter.dev/v1/latest"
_TIMEOUT = ClientTimeout(total=20)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MarketTickerUltra; +https://github.com/somansch/market_ticker_ultra)"
}
# The rates change once a day; asking a few times a day catches the fixing
# without anybody waiting for it.
_TTL = 4 * 3600
# After a failed request, not again right away.
_RETRY = 600


class ReferenceRates:
    """Euro reference rates, fetched when they are needed and kept."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._rates: dict[str, float] = {}
        self._date: str | None = None
        self._fetched = 0.0
        self._tried = 0.0

    @property
    def date(self) -> str | None:
        """The day the rates are from."""
        return self._date

    async def async_refresh(self) -> None:
        """Fetch the rates if the ones kept are old. Never raises: without
        an answer the rates from before stay, however old."""
        now = time.monotonic()
        if self._rates and now - self._fetched < _TTL:
            return
        if self._tried and now - self._tried < _RETRY:
            return
        self._tried = now
        try:
            async with self._session.get(
                _URL, params={"base": "EUR"}, headers=_HEADERS, timeout=_TIMEOUT
            ) as response:
                if response.status >= 400:
                    _LOGGER.debug("Frankfurter answered HTTP %s", response.status)
                    return
                data = await response.json(content_type=None)
        except (TimeoutError, ClientError, ValueError) as err:
            _LOGGER.debug("Reference rates not refreshed: %s", err)
            return
        rates = data.get("rates") if isinstance(data, dict) else None
        if not isinstance(rates, dict) or not rates:
            return
        self._rates = {"EUR": 1.0}
        for code, rate in rates.items():
            try:
                self._rates[str(code).upper()] = float(rate)
            except (TypeError, ValueError):
                continue
        self._date = data.get("date")
        self._fetched = now

    def convert(self, amount: float, source: str | None, target: str | None) -> float | None:
        """An amount in another currency - None where a rate is missing."""
        if not source or not target:
            return None
        source, target = source.upper(), target.upper()
        if source == target:
            return amount
        from_rate = self._rates.get(source)
        to_rate = self._rates.get(target)
        if not from_rate or not to_rate:
            return None
        return amount / from_rate * to_rate
