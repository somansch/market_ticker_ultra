"""The news about one instrument: headlines, each with its link.

From Yahoo Finance's feed of the instrument's symbol and - where the
settings ask for it - from Google News' search for its name. Asked for
when a card wants them, kept for half an hour; nothing of it is a sensor,
and nothing of it is written to the database.

Only the headline, where it is from, when, and the link: the article is
read where it was published.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import time
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError, ClientTimeout
from defusedxml import ElementTree

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from homeassistant.config_entries import ConfigEntry

from .const import CONF_NEWS_GOOGLE, SUBENTRY_INSTRUMENT
from .holdings import CONF_LOTS, clean_lots
from .coordinator import Instrument, MarketTickerUltraCoordinator
from .providers.http import HEADERS

_YAHOO = "https://feeds.finance.yahoo.com/rss/2.0/headline"
_GOOGLE = "https://news.google.com/rss/search"
_TIMEOUT = ClientTimeout(total=15)
# How long an answer is good for, in seconds.
_TTL = 1800
# How many headlines an instrument is given at most - and a portfolio.
NEWS_LIMIT = 20
GROUP_NEWS_LIMIT = 100


# The country whose edition is asked for in a language.
_COUNTRIES = {
    "de": "DE", "en": "US", "fr": "FR", "it": "IT", "es": "ES", "nl": "NL", "pt": "BR",
    "sv": "SE", "nb": "NO", "da": "DK", "fi": "FI", "pl": "PL", "ja": "JP",
    "cs": "CZ", "sk": "SK", "lt": "LT", "tr": "TR", "ru": "RU", "zh": "CN",
}
# Google News names an edition by country and language, and a few languages
# by a name of its own.
_GOOGLE_LANGUAGES = {"zh": ("zh-CN", "zh-Hans")}
# Where the language is the same in several countries, the one Home
# Assistant is in - if it is one of these.
_SAME_LANGUAGE = {
    "de": {"DE", "AT", "CH"},
    "en": {"US", "GB", "CA", "AU", "IN", "IE", "NZ", "SG"},
    "fr": {"FR", "CA", "BE", "CH"},
    "es": {"ES", "MX", "AR", "US"},
    "pt": {"BR", "PT"},
    "nl": {"NL", "BE"},
}


def _place(hass: Any, wanted: str | None) -> tuple[str, str]:
    """The language and the country the headlines are asked for in: the
    language of whoever looks at the card, else Home Assistant's own."""
    language = (wanted or hass.config.language or "en").replace("_", "-").split("-")[0].lower()
    if not language.isalpha() or len(language) > 3:
        language = "en"
    country = (hass.config.country or "").upper()
    if country not in _SAME_LANGUAGE.get(language, set()):
        country = _COUNTRIES.get(language, "US")
    return language, country


def _items(text: str, source: str) -> list[dict[str, Any]]:
    """The entries of a feed, each as a headline with its link."""
    try:
        root = ElementTree.fromstring(text)
    except Exception:  # noqa: BLE001 - whatever is wrong with it, it is no feed
        return []
    found: list[dict[str, Any]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or urlparse(link).scheme not in ("http", "https"):
            continue
        # Google names the publisher in a tag of its own - and once more
        # behind the headline, where it is not needed twice.
        named = (item.findtext("source") or "").strip()
        if named and title.endswith(f" - {named}"):
            title = title[: -len(named) - 3].rstrip()
        try:
            when = parsedate_to_datetime((item.findtext("pubDate") or "").strip())
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            when = None
        found.append(
            {
                "title": title,
                "url": link,
                "source": named or source,
                "published": when.astimezone(UTC).isoformat() if when else None,
            }
        )
    return found


async def _feed(hass: Any, url: str, params: dict[str, str], source: str) -> list[dict[str, Any]]:
    try:
        async with async_get_clientsession(hass).get(
            url, params=params, headers=HEADERS, timeout=_TIMEOUT
        ) as response:
            if response.status >= 400:
                return []
            return _items(await response.text(), source)
    except (TimeoutError, ClientError, UnicodeDecodeError):
        return []


async def _yahoo_symbol(coordinator: MarketTickerUltraCoordinator, instrument: Instrument) -> str | None:
    """What Yahoo calls the instrument: its symbol there, or that of the
    same thing where another source quotes it."""
    if instrument.source == "yahoo":
        return instrument.symbol
    # Whether or not Yahoo is switched on for quotes: this is not a quote.
    alternate = await coordinator._alternate_anywhere(instrument)  # noqa: SLF001
    if alternate and alternate[0] == "yahoo":
        return alternate[1]
    # Another source's instrument, known by its ISIN: what Yahoo calls it.
    if instrument.isin:
        listing = await coordinator.async_yahoo_listing(instrument.isin)
        if listing:
            return listing[0]
    return None


async def async_news(
    coordinator: MarketTickerUltraCoordinator, instrument: Instrument, name: str, wanted: str | None = None
) -> list[dict[str, Any]]:
    """The newest headlines about the instrument, newest first."""
    hass = coordinator.hass
    language, country = _place(hass, wanted)
    cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = coordinator.news
    key = (instrument.id, language)
    kept = cache.get(key)
    if kept and time.monotonic() - kept[0] < _TTL:
        return kept[1]

    found: list[dict[str, Any]] = []
    symbol = await _yahoo_symbol(coordinator, instrument)
    if symbol:
        found += await _feed(
            hass,
            _YAHOO,
            {"s": symbol, "region": country, "lang": f"{language}-{country}"},
            "Yahoo Finance",
        )
    if coordinator.options.get(CONF_NEWS_GOOGLE) and name:
        spoken, edition = _GOOGLE_LANGUAGES.get(language, (language, language))
        found += await _feed(
            hass,
            _GOOGLE,
            {"q": f'"{name}"', "hl": spoken, "gl": country, "ceid": f"{country}:{edition}"},
            "Google News",
        )

    # The same headline once, the newest first; one without a time last.
    seen: set[str] = set()
    news = []
    for item in sorted(found, key=lambda item: item["published"] or "", reverse=True):
        headline = item["title"].casefold()
        if headline in seen:
            continue
        seen.add(headline)
        news.append(item)
    news = news[:NEWS_LIMIT]
    cache[key] = (time.monotonic(), news)
    return news


async def async_group_news(
    coordinator: MarketTickerUltraCoordinator, entry: ConfigEntry, wanted: str | None = None
) -> list[dict[str, Any]]:
    """The newest headlines about what a portfolio holds, newest first -
    each with the instrument it is about."""
    held = [
        (subentry_id, subentry.title)
        for subentry_id, subentry in entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_INSTRUMENT and clean_lots(subentry.data.get(CONF_LOTS))
    ]
    instruments = [(coordinator.instrument(subentry_id), name) for subentry_id, name in held]
    asked = [(instrument, name) for instrument, name in instruments if instrument is not None]
    answers = await asyncio.gather(
        *(async_news(coordinator, instrument, name, wanted) for instrument, name in asked)
    )
    seen: set[str] = set()
    news: list[dict[str, Any]] = []
    merged = [
        {**item, "instrument": instrument.id, "name": name}
        for (instrument, name), items in zip(asked, answers, strict=True)
        for item in items
    ]
    for item in sorted(merged, key=lambda item: item["published"] or "", reverse=True):
        headline = item["title"].casefold()
        if headline in seen:
            continue
        seen.add(headline)
        news.append(item)
    return news[:GROUP_NEWS_LIMIT]
