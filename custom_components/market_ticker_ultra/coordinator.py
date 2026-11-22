"""One poll for every instrument of the entry, across all its sources."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ALL_SOURCES,
    CLOSED_SCAN_INTERVAL,
    CONF_ALERT_ABOVE,
    CONF_ALERT_BELOW,
    CONF_ALERT_NOTIFY,
    CONF_ALERT_PERSISTENT,
    CONF_ALERT_MESSAGE,
    CONF_ALERT_SERVICES,
    CONF_ALERT_SPEAKERS,
    CONF_ALERT_SPOKEN,
    CONF_ALERT_TITLE,
    CONF_ALERT_TTS,
    EVENT_ALERT,
    CONF_BASE_CURRENCY,
    CONF_CURRENCY,
    CONF_ISIN,
    CONF_SCAN_INTERVAL,
    CONF_SOURCE,
    CONF_SOURCES,
    CONF_SYMBOL,
    CONF_TYPE,
    DEFAULT_ALERT_PERSISTENT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_BACKOFF,
    SOURCE_YAHOO,
    STATE_CLOSED,
    SUBENTRY_INSTRUMENT,
)
from .fx import ReferenceRates
from .localized import decimal_comma, text as local_text
from .groups import group_entries, is_portfolio, settings_options
from .holdings import CONF_LOTS, Holding, Ledger, holding_from_lots, ledger_from_lots, position_at
from .providers import History, Provider, ProviderError, Quote, RateLimited
from .providers.boerse_frankfurt import BoerseFrankfurtProvider
from .providers.ecb import EcbProvider, split_pair
from .providers.goldapi import GoldApiProvider
from .providers.kraken import KrakenProvider
from .providers.yahoo import YahooProvider

# How long a price series is good for before it is asked for again, in
# seconds, by the bar it is drawn with: a five-minute bar is stale after a
# few minutes, a monthly one not within the day.
_HISTORY_TTL = {
    "5m": 120,
    "15m": 300,
    "30m": 600,
    "1h": 900,
    "4h": 1800,
    "1d": 1800,
    "1wk": 6 * 3600,
    "1mo": 12 * 3600,
}
# Company figures are those of the last close.
_DETAILS_TTL = 6 * 3600
# The series the usual day's volume is taken from.
_VOLUME_RANGE = "3mo"
# After this many polls in a row without an answer a source gets a repair.
_FAILURES_FOR_ISSUE = 3

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Instrument:
    """One instrument of the entry: where it is asked for, and as what."""

    id: str
    source: str
    symbol: str
    type: str | None
    isin: str | None


@dataclass
class MarketData:
    """The quotes of the last poll that brought any, by instrument."""

    quotes: dict[str, Quote] = field(default_factory=dict)
    # Which source each quote really came from - not always the instrument's
    # own, when that one did not answer and another could stand in.
    sources: dict[str, str] = field(default_factory=dict)
    # When a source last answered, and what went wrong since - None while
    # the quotes are those of the latest poll.
    fetched_at: datetime | None = None
    error: str | None = None


class MarketTickerUltraCoordinator(DataUpdateCoordinator[MarketData]):
    """Asks every source for its instruments at once.

    One for the whole integration: the instruments of every group are asked
    for in one poll, and what a source allows is shared by all of them.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        # Minutes to wait after a source asked for a break; 0 while none has.
        self._backoff = 0
        # One entry after the other at start: the first asks for all.
        self._first = asyncio.Lock()
        # The portfolios the settings' entry has set sums up for - id and
        # name; see __init__.py, which sets it up again when they change.
        self.summed: list[tuple[str, str]] = []
        # What performance.py has worked out, by group and range, each with
        # the time it is from.
        self.performances: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
        # The news about an instrument, kept a while (see news.py).
        self.news: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
        # Yahoo's symbol and kind of an instrument known by its ISIN only
        # (see async_yahoo_listing).
        self._yahoo_listings: dict[str, tuple[str, str] | None] = {}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=None,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL),
        )
        self.update_interval = timedelta(minutes=self._interval)
        session = async_get_clientsession(hass)
        self.kraken = KrakenProvider(session)
        self.providers: dict[str, Provider] = {
            provider.key: provider
            for provider in (
                YahooProvider(session),
                EcbProvider(session),
                self.kraken,
                GoldApiProvider(session),
                BoerseFrankfurtProvider(session),
            )
        }
        self.rates = ReferenceRates(session)
        # Where the logos users uploaded are served, by subentry - filled
        # at setup, see __init__.py.
        self.own_logos: dict[str, str] = {}
        # Polls in a row each source has not answered.
        self._failures: dict[str, int] = {}
        # What the card asked for before, each with the time it was fetched
        # - several cards and several open pages share one request - and one
        # lock so that two of them asking at the same moment make it one.
        self._histories: dict[tuple[str, str, str], tuple[float, History]] = {}
        self._details: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
        self._fetch_lock = asyncio.Lock()
        # Which price alerts are on, by instrument and side - None until
        # the first poll has said where every price stands: an alert that is
        # on at start is not news.
        self._alerts: dict[tuple[str, str], bool] | None = None

    @property
    def options(self) -> dict[str, Any]:
        """The settings - of the entry that holds them."""
        return settings_options(self.hass)

    @property
    def _interval(self) -> int:
        return int(self.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    def settings_changed(self) -> None:
        """Take the interval over, and ask again with what is set now."""
        self._set_interval(any_open=True)
        # Where the news come from may be what has changed.
        self.news.clear()
        self.hass.async_create_task(self.async_request_refresh())

    async def async_ensure_quotes(self) -> None:
        """Ask the sources unless every instrument has a quote already: the
        first entry to be set up asks for all, the others find theirs there.
        An instrument just added has none yet, and is asked for."""
        async with self._first:
            wanted = {instrument.id for instrument in self.instruments}
            if self.data is None or not wanted <= set(self.data.quotes):
                await self.async_refresh()

    def members(self) -> dict[str, tuple[ConfigEntry, ConfigSubentry]]:
        """Every instrument of every group, by its id, with its group."""
        return {
            subentry_id: (entry, subentry)
            for entry in group_entries(self.hass)
            for subentry_id, subentry in entry.subentries.items()
            if subentry.subentry_type == SUBENTRY_INSTRUMENT
        }

    def member(self, instrument_id: str) -> ConfigSubentry | None:
        found = self.members().get(instrument_id)
        return found[1] if found else None

    @property
    def enabled(self) -> frozenset[str]:
        """The sources that may be asked. An entry from before the choice
        existed asks all of them."""
        chosen = self.options.get(CONF_SOURCES)
        if chosen is None:
            return frozenset(ALL_SOURCES)
        return frozenset(chosen) & frozenset(ALL_SOURCES)

    # ----------------------------------------------------- the instruments

    @property
    def instruments(self) -> list[Instrument]:
        found = []
        for subentry_id, (_entry, subentry) in self.members().items():
            data = subentry.data
            found.append(
                Instrument(
                    id=subentry_id,
                    source=data.get(CONF_SOURCE) or SOURCE_YAHOO,
                    symbol=data[CONF_SYMBOL],
                    type=data.get(CONF_TYPE),
                    isin=data.get(CONF_ISIN),
                )
            )
        return found

    def instrument(self, instrument_id: str) -> Instrument | None:
        return next((i for i in self.instruments if i.id == instrument_id), None)

    @property
    def base_currency(self) -> str:
        """The currency positions are added up in: the one chosen, or the
        instance's own."""
        chosen = str(self.options.get(CONF_BASE_CURRENCY) or "").strip().upper()
        return chosen or self.hass.config.currency

    def _counted(self, group: str | None = None) -> dict[str, Any]:
        """The instruments whose purchases are added up - those of a
        portfolio, never those of a watchlist - of one group or of all. A
        group is named by its entry's id."""
        return {
            subentry_id: subentry
            for subentry_id, (entry, subentry) in self.members().items()
            if is_portfolio(entry) and (group is None or entry.entry_id == group)
        }

    def holdings(self, group: str | None = None) -> dict[str, Holding]:
        """What is held, by instrument - of one group, or of all."""
        held: dict[str, Holding] = {}
        for subentry_id, subentry in self._counted(group).items():
            holding = holding_from_lots(subentry.data.get(CONF_LOTS))
            if holding is not None:
                held[subentry_id] = holding
        return held

    def ledgers(self, group: str | None = None) -> dict[str, Ledger]:
        """What was realised and paid in fees and taxes, by instrument -
        of those that have any of it."""
        found: dict[str, Ledger] = {}
        for subentry_id, subentry in self._counted(group).items():
            ledger = ledger_from_lots(subentry.data.get(CONF_LOTS))
            if not ledger.empty:
                found[subentry_id] = ledger
        return found

    def totals(self, group: str | None = None) -> dict[str, Any] | None:
        """Every position added up in the base currency - of one group, or
        of all. None where nothing is held or nothing has a quote yet.

        A position in a currency the reference rates do not list is left
        out, and named, rather than added at a made-up rate.
        """
        quotes = self.data.quotes if self.data else {}
        base = self.base_currency
        value = cost = day = 0.0
        counted = 0
        left_out: list[str] = []
        # What was realised and paid, in the base currency too. The currency
        # is the instrument's: the one its quote names, or the one stored.
        realized = fees = taxes = 0.0
        for instrument_id, ledger in self.ledgers(group).items():
            quote = quotes.get(instrument_id)
            subentry = self.member(instrument_id)
            currency = (quote.currency if quote else None) or (
                subentry.data.get(CONF_CURRENCY) if subentry else None
            )
            realized += self.rates.convert(ledger.realized, currency, base) or 0.0
            fees += self.rates.convert(ledger.fees, currency, base) or 0.0
            taxes += self.rates.convert(ledger.taxes, currency, base) or 0.0
        for instrument_id, holding in self.holdings(group).items():
            quote = quotes.get(instrument_id)
            if quote is None:
                continue
            position = position_at(holding, quote)
            in_base = self.rates.convert(position.value, quote.currency, base)
            if in_base is None:
                left_out.append(quote.symbol)
                continue
            value += in_base
            cost += self.rates.convert(position.cost, quote.currency, base) or 0.0
            day += self.rates.convert(position.day_change or 0.0, quote.currency, base) or 0.0
            counted += 1
        if not counted:
            return None
        gain = value - cost
        return {
            "currency": base,
            "value": value,
            "cost": cost,
            "gain": gain,
            "gain_percent": gain / cost * 100 if cost else None,
            "day_change": day,
            "realized": realized,
            "fees": fees,
            "taxes": taxes,
            "positions": counted,
            "not_converted": left_out,
            "rates_date": self.rates.date,
        }

    # ------------------------------------------------- standing in for one

    async def _alternate(self, instrument: Instrument) -> tuple[str, str] | None:
        """Another source that quotes the same thing, and its symbol there -
        if that source is switched on."""
        alternate = await self._alternate_anywhere(instrument)
        return alternate if alternate and alternate[0] in self.enabled else None

    async def _alternate_anywhere(self, instrument: Instrument) -> tuple[str, str] | None:
        """Only where the two really are the same instrument: a coin in a
        currency, a currency pair, a share at Xetra or Frankfurt known by
        its ISIN. A spot metal and its future are not.
        """
        kind = (instrument.type or "").upper()
        symbol = instrument.symbol
        if instrument.source == "yahoo":
            if kind == "CRYPTOCURRENCY" and "-" in symbol:
                base, _, quote = symbol.partition("-")
                try:
                    found = await self.kraken.symbol_for(base, quote)
                except ProviderError:
                    return None
                return ("kraken", found) if found else None
            if kind == "CURRENCY":
                pair = split_pair(symbol)
                return ("ecb", f"{pair[0]}/{pair[1]}") if pair else None
            if instrument.isin and symbol.endswith(".DE"):
                return ("boerse_frankfurt", f"XETR:{instrument.isin}")
            if instrument.isin and symbol.endswith(".F"):
                return ("boerse_frankfurt", f"XFRA:{instrument.isin}")
            return None
        if instrument.source == "ecb":
            pair = split_pair(symbol)
            return ("yahoo", f"{pair[0]}{pair[1]}=X") if pair else None
        if instrument.source == "kraken":
            try:
                pair = (await self.kraken.pairs()).get(symbol)
            except ProviderError:
                return None
            return ("yahoo", f"{pair['base']}-{pair['quote']}") if pair else None
        return None

    # ------------------------------------------------------------ the poll

    async def _async_update_data(self) -> MarketData:
        instruments = self.instruments
        if not instruments:
            return MarketData(fetched_at=dt_util.utcnow())
        if self.holdings() or self.ledgers() or any(i.source == "goldapi" for i in instruments):
            # For sums and spot metals in the base currency; kept for
            # hours, and never in the way of the quotes.
            await self.rates.async_refresh()

        # An instrument whose source is switched off is not asked for
        # there; it is quoted by the source that can stand in, if one is on,
        # and keeps its last quote otherwise.
        enabled = self.enabled
        by_source: dict[str, list[Instrument]] = {}
        for instrument in instruments:
            if instrument.source in enabled:
                by_source.setdefault(instrument.source, []).append(instrument)

        quotes: dict[str, Quote] = {}
        sources: dict[str, str] = {}
        errors: list[str] = []
        limited = False

        async def ask(source: str, wanted: dict[str, str]) -> dict[str, Quote]:
            """Quotes by instrument for {instrument id: symbol} at a source."""
            nonlocal limited
            provider = self.providers.get(source)
            if provider is None:
                return {}
            try:
                answered = await provider.quotes(list(dict.fromkeys(wanted.values())))
            except ProviderError as err:
                limited = limited or isinstance(err, RateLimited)
                self._note(source, str(err))
                errors.append(str(err))
                return {}
            self._note(source, None)
            return {key: answered[symbol] for key, symbol in wanted.items() if symbol in answered}

        groups = list(by_source.items())
        results = await asyncio.gather(
            *(ask(source, {i.id: i.symbol for i in group}) for source, group in groups)
        )
        for (source, _group), answered in zip(groups, results, strict=True):
            for key, quote in answered.items():
                quotes[key] = quote
                sources[key] = source

        # What its own source did not answer for, from one that can stand in.
        stand_ins: dict[str, dict[str, str]] = {}
        for instrument in instruments:
            if instrument.id in quotes:
                continue
            alternate = await self._alternate(instrument)
            if alternate:
                stand_ins.setdefault(alternate[0], {})[instrument.id] = alternate[1]
        for source, wanted in stand_ins.items():
            for key, quote in (await ask(source, wanted)).items():
                quotes[key] = quote
                sources[key] = source

        base = self.base_currency
        for key, quote in list(quotes.items()):
            if sources[key] == "goldapi" and quote.currency != base:
                # A spot metal is quoted in dollars; shown in the currency
                # everything is added up in, where a rate for it exists.
                price = self.rates.convert(quote.price, quote.currency, base)
                if price is not None:
                    quotes[key] = replace(quote, price=round(price, 2), currency=base)

        if limited:
            # Twice as long each time, so that a source that wants a break
            # gets one instead of being asked every few minutes.
            self._backoff = min(MAX_BACKOFF, max(self._interval, self._backoff) * 2)
        else:
            self._backoff = 0

        failure = "; ".join(dict.fromkeys(errors)) or None
        previous = self.data
        if not quotes:
            self._set_interval(any_open=True)
            if previous is None or not previous.quotes:
                raise UpdateFailed(failure or "No source answered")
            # The last quotes stay, each with the time it is from, rather
            # than every sensor going unavailable over one missed poll.
            return replace(previous, error=failure or "No source answered")

        if previous is not None:
            # An instrument nobody answered for this time keeps its last
            # quote too.
            wanted_ids = {i.id for i in instruments}
            for key, quote in previous.quotes.items():
                if key in wanted_ids and key not in quotes:
                    quotes[key] = quote
                    sources[key] = previous.sources.get(key, "")

        self._set_interval(
            any_open=any(q.market_state != STATE_CLOSED for q in quotes.values())
        )
        self._check_alerts(quotes)
        return MarketData(
            quotes=quotes, sources=sources, fetched_at=dt_util.utcnow(), error=failure
        )

    # ---------------------------------------------------------- the alerts

    def alert_limits(self, instrument_id: str) -> dict[str, float]:
        """The limits set for an instrument: "below", "above", or neither."""
        subentry = self.member(instrument_id)
        limits: dict[str, float] = {}
        if subentry is None:
            return limits
        for side, key in (("below", CONF_ALERT_BELOW), ("above", CONF_ALERT_ABOVE)):
            try:
                limit = float(subentry.data[key])
            except (KeyError, TypeError, ValueError):
                continue
            if limit > 0:
                limits[side] = limit
        return limits

    def alert_on(self, instrument_id: str, side: str, quote: Quote | None = None) -> bool | None:
        """Whether an alert is on at the current price of the instrument -
        None where there is no such limit or no price."""
        limit = self.alert_limits(instrument_id).get(side)
        if quote is None and self.data:
            quote = self.data.quotes.get(instrument_id)
        if limit is None or quote is None:
            return None
        return quote.price <= limit if side == "below" else quote.price >= limit

    def _check_alerts(self, quotes: dict[str, Quote]) -> None:
        """Tell whoever is to be told about every alert that has just come
        on. Once: it is armed again only after the price has left the limit.
        """
        now: dict[tuple[str, str], bool] = {}
        for instrument in self.instruments:
            for side in self.alert_limits(instrument.id):
                state = self.alert_on(instrument.id, side, quotes.get(instrument.id))
                if state is not None:
                    now[(instrument.id, side)] = state
        before, self._alerts = self._alerts, now
        if before is None:
            return
        comma = decimal_comma(self.hass)
        for (instrument_id, side), state in now.items():
            if not state or before.get((instrument_id, side)):
                continue
            subentry = self.member(instrument_id)
            quote = quotes.get(instrument_id)
            if subentry is None or quote is None:
                continue
            limit = self.alert_limits(instrument_id)[side]
            # An index stands in points: no currency.
            unit = f" {quote.currency}" if quote.currency and quote.type != "INDEX" else ""
            # Written the way the language writes a number.
            def figure(value: float, digits: int = quote.precision) -> str:
                text = f"{value:.{digits}f}"
                return text.replace(".", ",") if comma else text

            where = local_text(self.hass, f"direction_{side}")
            change = quote.change_percent
            title, message, spoken = self.alert_texts(
                {
                    "name": subentry.title,
                    "symbol": subentry.data.get(CONF_SYMBOL) or "",
                    "price": f"{figure(quote.price)}{unit}",
                    "limit": f"{figure(limit)}{unit}",
                    "currency": quote.currency if unit else "",
                    "direction": where,
                    "change": "" if change is None else f"{'+' if change > 0 else ''}{figure(change, 2)} %",
                }
            )
            self.tell_alert(
                title,
                message,
                f"{DOMAIN}_{instrument_id}_{side}",
                {
                    "instrument": instrument_id,
                    "name": subentry.title,
                    "symbol": subentry.data.get(CONF_SYMBOL),
                    "side": side,
                    "price": quote.price,
                    "limit": limit,
                    "currency": quote.currency if unit else None,
                },
                spoken,
            )

    def alert_texts(self, values: dict[str, str]) -> tuple[str, str, str]:
        """An alert's title, its message and what is spoken: the settings'
        own words, or the defaults in Home Assistant's language, with the
        variables filled in. A variable that is not one stays as written."""
        class _Kept(dict[str, str]):
            def __missing__(self, key: str) -> str:
                return "{" + key + "}"

        def text(key: str) -> str:
            template = str(self.options.get(key) or "").strip() or local_text(self.hass, key)
            try:
                return template.format_map(_Kept(values))
            except (ValueError, IndexError, KeyError, AttributeError):
                # Braces that are no variable: said as they are written.
                return template

        return text(CONF_ALERT_TITLE), text(CONF_ALERT_MESSAGE), text(CONF_ALERT_SPOKEN)

    def tell_alert(
        self,
        title: str,
        message: str,
        note_id: str,
        data: dict[str, Any] | None = None,
        spoken: str | None = None,
    ) -> None:
        """Tell everybody the settings name: Home Assistant's own note, the
        notify entities, the notify services by their name, the speakers -
        and, always, an event for whatever automation listens for it."""
        hass = self.hass
        options = self.options
        hass.bus.async_fire(EVENT_ALERT, {**(data or {}), "title": title, "message": message})
        if bool(options.get(CONF_ALERT_PERSISTENT, DEFAULT_ALERT_PERSISTENT)):
            persistent_notification.async_create(hass, message, title, note_id)

        def call(domain: str, service: str, payload: dict[str, Any]) -> None:
            async def run() -> None:
                # One that fails - a speaker switched off, a service gone -
                # is no reason for the others not to be told.
                try:
                    await hass.services.async_call(domain, service, payload, blocking=True)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("Price alert: %s.%s could not be told: %s", domain, service, err)

            hass.async_create_task(run())

        targets = list(options.get(CONF_ALERT_NOTIFY) or [])
        if targets:
            call("notify", "send_message", {"entity_id": targets, "message": message, "title": title})
        for name in options.get(CONF_ALERT_SERVICES) or []:
            service = str(name).strip().removeprefix("notify.")
            if service and hass.services.has_service("notify", service):
                call("notify", service, {"message": message, "title": title})
            elif service:
                _LOGGER.warning("Price alert: there is no notify service %s", service)
        speakers = list(options.get(CONF_ALERT_SPEAKERS) or [])
        if speakers:
            voice = options.get(CONF_ALERT_TTS) or next(iter(hass.states.async_entity_ids("tts")), None)
            if voice:
                call(
                    "tts",
                    "speak",
                    {
                        "entity_id": voice,
                        "media_player_entity_id": speakers,
                        "message": spoken or f"{title}. {message}",
                    },
                )
            else:
                _LOGGER.warning("Price alert: no text-to-speech voice to announce it with")

    def _note(self, source: str, error: str | None) -> None:
        """Count a source's polls without an answer, and say so in a repair
        once they add up - taken back with its next answer."""
        issue_id = f"source_failing_{source}"
        if error is None:
            if self._failures.pop(source, 0) >= _FAILURES_FOR_ISSUE:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        count = self._failures.get(source, 0) + 1
        self._failures[source] = count
        if count == _FAILURES_FOR_ISSUE:
            provider = self.providers.get(source)
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="source_failing",
                translation_placeholders={
                    "source": provider.label if provider else source,
                    "count": str(count),
                    "reason": error,
                },
            )

    def clear_issues(self) -> None:
        """Take every repair of this run back - at unload."""
        for source in self.providers:
            ir.async_delete_issue(self.hass, DOMAIN, f"source_failing_{source}")

    def _set_interval(self, any_open: bool) -> None:
        minutes = self._interval
        if not any_open:
            minutes = max(minutes, CLOSED_SCAN_INTERVAL)
        if self._backoff:
            minutes = max(minutes, self._backoff)
        self.update_interval = timedelta(minutes=minutes)

    # ------------------------------------------------ what the card asks

    async def _history_from_sources(self, instrument: Instrument, range_: str) -> History:
        """Ask the instrument's own source, then the one that can stand in."""
        provider = self.providers.get(instrument.source)
        if provider is None:
            raise ProviderError("Unknown source")
        try:
            if instrument.source not in self.enabled:
                raise ProviderError(f"{provider.label} is switched off")
            return await provider.history(instrument.symbol, range_)
        except ProviderError:
            alternate = await self._alternate(instrument)
            if not alternate:
                raise
            return await self.providers[alternate[0]].history(alternate[1], range_)

    async def async_history(self, instrument: Instrument, range_: str) -> History:
        """A price series, from the cache while it is fresh.

        A series that could not be refreshed is answered with the one from
        before, if there is one: an old chart says more than none.
        """
        key = (instrument.source, instrument.symbol, range_)
        async with self._fetch_lock:
            cached = self._histories.get(key)
            now = time.monotonic()
            if cached and now - cached[0] < _HISTORY_TTL.get(cached[1].interval, 600):
                return cached[1]
            try:
                history = await self._history_from_sources(instrument, range_)
            except ProviderError:
                if cached:
                    return cached[1]
                raise
            self._histories[key] = (now, history)
            return history

    async def async_yahoo_listing(self, isin: str) -> tuple[str, str] | None:
        """Yahoo's symbol of the instrument with this ISIN and its kind,
        looked up once - an answer is kept, also the answer that there is
        none; a failed request is asked again the next time."""
        if isin not in self._yahoo_listings:
            yahoo = self.providers.get("yahoo")
            if yahoo is None:
                return None
            try:
                self._yahoo_listings[isin] = await yahoo.listing_for_isin(isin)
            except ProviderError:
                return None
        return self._yahoo_listings[isin]

    async def async_details(self, instrument: Instrument) -> dict[str, Any]:
        """Company figures plus the usual day's volume of one instrument."""
        key = (instrument.source, instrument.symbol)
        cached = self._details.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < _DETAILS_TTL:
            return cached[1]
        provider = self.providers.get(instrument.source)
        if provider is None:
            raise ProviderError("Unknown source")
        try:
            if instrument.source not in self.enabled:
                raise ProviderError(f"{provider.label} is switched off")
            details = await provider.details(instrument.symbol)
        except ProviderError:
            if cached:
                return cached[1]
            raise
        average = None
        try:
            usual = await self.async_history(instrument, _VOLUME_RANGE)
            volumes = [v for v in usual.volume[usual.warmup :] if v]
            if volumes:
                average = int(sum(volumes) / len(volumes))
        except ProviderError:
            pass
        # When the next quarterly figures are due, from Yahoo's calendar: of
        # its own shares by their symbol, of another source's by their ISIN.
        # Only where there is such a day: a fund has none.
        due: dict[str, Any] = {}
        yahoo = self.providers.get("yahoo")
        if yahoo is not None and "yahoo" in self.enabled:
            share: str | None = None
            if instrument.source == "yahoo":
                if (instrument.type or "").upper() in ("", "EQUITY"):
                    share = instrument.symbol
            elif instrument.isin:
                listing = await self.async_yahoo_listing(instrument.isin)
                if listing and listing[1] == "EQUITY":
                    share = listing[0]
            if share:
                due = await yahoo.earnings(share)
        result = {
            "market_cap": details.market_cap,
            "pe": details.pe,
            "eps": details.eps,
            "average_volume": average,
            "as_of": details.as_of,
            "earnings_date": due.get("earnings_date"),
            "earnings_date_end": due.get("earnings_date_end"),
            "earnings_estimate": bool(due.get("earnings_estimate")),
        }
        self._details[key] = (now, result)
        return result
