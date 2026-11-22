"""One way to ask a source for JSON, with one set of things that can go wrong."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from . import ProviderError, RateLimited

_TIMEOUT = ClientTimeout(total=20)
# A name of its own: the client library's default one is turned away by some
# sources.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MarketTickerUltra; +https://github.com/somansch/market_ticker_ultra)"
}


async def get_json(
    session: ClientSession, label: str, url: str, params: dict[str, str] | None = None
) -> Any:
    """The JSON a source answers with - or ProviderError saying why not."""
    try:
        async with session.get(
            url, params=params, headers=HEADERS, timeout=_TIMEOUT
        ) as response:
            if response.status == 429:
                raise RateLimited(f"{label} asked for a break (HTTP 429)")
            if response.status >= 400:
                raise ProviderError(f"{label} answered HTTP {response.status}")
            return await response.json(content_type=None)
    except TimeoutError as err:
        raise ProviderError(f"{label} did not answer in time") from err
    except ClientError as err:
        raise ProviderError(f"{label} could not be reached: {err}") from err
    except ValueError as err:
        raise ProviderError(f"{label} answered with something that is not JSON") from err


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
