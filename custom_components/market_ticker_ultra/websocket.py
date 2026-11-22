"""What the dashboard card asks the integration.

Quotes it reads from the sensors, live. Here is the rest: which instruments
there are, the price series behind a chart, the few figures about a company,
and the version of the card file itself.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .bundle import CARD_VERSION_DATA
from .const import (
    CONF_ALERT_ABOVE,
    CONF_ALERT_BELOW,
    CONF_COLOR,
    CONF_CURRENCY,
    CONF_EXCHANGE,
    CONF_ISIN,
    CONF_LOGOS,
    CONF_NAME,
    CONF_SOURCE,
    CONF_SYMBOL,
    CONF_TRADINGVIEW,
    CONF_TYPE,
    DEFAULT_LOGOS,
    DOMAIN,
    SOURCE_YAHOO,
    SUBENTRY_INSTRUMENT,
)
from .coordinator import MarketTickerUltraCoordinator
from .groups import groups_of, is_portfolio
from .holdings import CONF_LOTS, holding_from_lots, ledger_from_lots
from .logos import ATTRIBUTION, logo_url
from .news import async_group_news, async_news
from .performance import PERFORMANCE_RANGES, async_performance
from .providers import RANGES, ProviderError
from .tradingview import clean_own_symbol, found_symbol, tradingview_symbol


def _coordinator(hass: HomeAssistant) -> MarketTickerUltraCoordinator | None:
    """The one coordinator - there while any entry is loaded."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data
    return None


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/instruments"})
@callback
def websocket_instruments(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Every instrument, in the order it was added, with its sensor and logo."""
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_error(msg["id"], "not_loaded", "Market Ticker Ultra is not set up")
        return

    logos = bool(coordinator.options.get(CONF_LOGOS, DEFAULT_LOGOS))
    registry = er.async_get(hass)
    instruments = []
    for entry, subentry in coordinator.members().values():
        # Only loaded groups: an instrument of one that is not has no sensor.
        if entry.state is not ConfigEntryState.LOADED:
            continue
        data = subentry.data
        symbol = data[CONF_SYMBOL]
        quote = (
            coordinator.data.quotes.get(subentry.subentry_id) if coordinator.data else None
        )
        source = data.get(CONF_SOURCE) or SOURCE_YAHOO
        kind = (quote.type if quote else None) or data.get(CONF_TYPE)
        # Only a portfolio's purchases are a position; a watchlist has none.
        lots = data.get(CONF_LOTS) if is_portfolio(entry) else None
        holding = holding_from_lots(lots)
        ledger = ledger_from_lots(lots)
        currency = (quote.currency if quote else None) or data.get(CONF_CURRENCY)
        limits = coordinator.alert_limits(subentry.subentry_id)
        instruments.append(
            {
                "id": subentry.subentry_id,
                "entity_id": registry.async_get_entity_id(
                    "sensor", DOMAIN, f"{subentry.subentry_id}_price"
                ),
                "name": subentry.title,
                # The group it is in: that group's entry id - which is
                # also where the card runs its dialogs for it.
                "group": entry.entry_id,
                # Its own colour among a portfolio's shares, where it has one.
                "color": data.get(CONF_COLOR) or None,
                # Its price alerts, in its own currency.
                "alert_below": limits.get("below"),
                "alert_above": limits.get("above"),
                # One unit of its currency in the base currency, at the
                # reference rate - what the card adds positions up with.
                "base_rate": coordinator.rates.convert(1.0, currency, coordinator.base_currency),
                # What sales realised and what was paid in fees and taxes,
                # in its currency - there with nothing held too.
                "ledger": (
                    None
                    if ledger.empty
                    else {"realized": ledger.realized, "fees": ledger.fees, "taxes": ledger.taxes}
                ),
                "symbol": symbol,
                "isin": data.get(CONF_ISIN),
                "type": kind,
                "currency": (quote.currency if quote else None) or data.get(CONF_CURRENCY),
                "exchange": (quote.exchange if quote else None) or data.get(CONF_EXCHANGE),
                # The decimals the instrument is quoted in.
                "precision": quote.precision if quote else None,
                # What is held and what it cost, in the instrument's
                # currency. What it is worth the card works out itself, with
                # the price it shows.
                "position": (
                    {"quantity": holding.quantity, "cost": holding.cost}
                    if holding is not None
                    else None
                ),
                # An uploaded logo comes before the logo source's, and is
                # there with the source switched off too.
                "logo": coordinator.own_logos.get(subentry.subentry_id)
                or (
                    logo_url(source, symbol, kind, data.get(CONF_ISIN), data.get(CONF_NAME))
                    if logos
                    else None
                ),
                # What TradingView calls the instrument, for the card's link
                # to it: the user's own word for it first, else what can be
                # worked out - from the exchange the instrument was added
                # at, not the one a stand-in source may be quoting -, else
                # what was looked up for it.
                "tradingview": clean_own_symbol(data.get(CONF_TRADINGVIEW))
                or tradingview_symbol(
                    source,
                    symbol,
                    data.get(CONF_EXCHANGE) or (quote.exchange if quote else None),
                    data.get(CONF_TYPE) or kind,
                    (quote.currency if quote else None) or data.get(CONF_CURRENCY),
                )
                or found_symbol(data),
                # Whether the logo is the user's own - the source's line is
                # owed for its logos only.
                "logo_own": subentry.subentry_id in coordinator.own_logos,
            }
        )
    connection.send_result(
        msg["id"],
        {
            "instruments": instruments,
            "groups": [
                {"id": group.id, "name": group.name, "kind": group.kind}
                for group in groups_of(hass)
            ],
            "base_currency": coordinator.base_currency,
            "logo_attribution": ATTRIBUTION if logos else None,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/history",
        vol.Required("instrument"): str,
        vol.Required("range"): vol.In(list(RANGES)),
    }
)
@websocket_api.async_response
async def websocket_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The price series of one instrument over one range."""
    coordinator = _coordinator(hass)
    instrument = coordinator.instrument(msg["instrument"]) if coordinator else None
    if instrument is None:
        connection.send_error(msg["id"], "not_found", "No such instrument")
        return
    try:
        history = await coordinator.async_history(instrument, msg["range"])
    except ProviderError as err:
        connection.send_error(msg["id"], "source_failed", str(err))
        return
    result = asdict(history)
    session = result.pop("session")
    result["session"] = {"start": session[0], "end": session[1]} if session else None
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/details", vol.Required("instrument"): str}
)
@websocket_api.async_response
async def websocket_details(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Market capitalisation, price/earnings, earnings per share and the
    usual day's volume of one instrument - each None where there is none."""
    coordinator = _coordinator(hass)
    instrument = coordinator.instrument(msg["instrument"]) if coordinator else None
    if instrument is None:
        connection.send_error(msg["id"], "not_found", "No such instrument")
        return
    try:
        details = await coordinator.async_details(instrument)
    except ProviderError as err:
        connection.send_error(msg["id"], "source_failed", str(err))
        return
    connection.send_result(msg["id"], details)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/performance",
        vol.Required("group"): str,
        vol.Required("range"): vol.In(list(PERFORMANCE_RANGES)),
    }
)
@websocket_api.async_response
async def websocket_performance(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """A portfolio's time-weighted return over a range, day by day, and
    that of the index it is compared with."""
    coordinator = _coordinator(hass)
    entry = hass.config_entries.async_get_entry(msg["group"])
    if coordinator is None or entry is None or entry.domain != DOMAIN or not is_portfolio(entry):
        connection.send_error(msg["id"], "not_found", "No such portfolio")
        return
    connection.send_result(msg["id"], await async_performance(coordinator, entry, msg["range"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/news",
        # Of one instrument - or of everything a portfolio holds.
        vol.Exclusive("instrument", "of"): str,
        vol.Exclusive("group", "of"): str,
        # The language of whoever is looking: the headlines come in it.
        vol.Optional("language"): str,
    }
)
@websocket_api.async_response
async def websocket_news(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The newest headlines about one instrument - or about what a
    portfolio holds -, each with its link."""
    coordinator = _coordinator(hass)
    if "group" in msg:
        entry = hass.config_entries.async_get_entry(msg["group"])
        if coordinator is None or entry is None or entry.domain != DOMAIN or not is_portfolio(entry):
            connection.send_error(msg["id"], "not_found", "No such portfolio")
            return
        connection.send_result(
            msg["id"], {"news": await async_group_news(coordinator, entry, msg.get("language"))}
        )
        return
    instrument = coordinator.instrument(msg.get("instrument", "")) if coordinator else None
    if instrument is None:
        connection.send_error(msg["id"], "not_found", "No such instrument")
        return
    subentry = coordinator.member(instrument.id)
    name = subentry.title if subentry else ""
    connection.send_result(msg["id"], {"news": await async_news(coordinator, instrument, name, msg.get("language"))})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/card_version"})
@callback
def websocket_card_version(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The version the card is served under right now - what the loader in
    an open page asks after Home Assistant has restarted, to fetch a newer
    card into that page without anyone reloading it."""
    connection.send_result(msg["id"], {"version": hass.data.get(CARD_VERSION_DATA) or 0})


@callback
def async_register(hass: HomeAssistant) -> None:
    """Make the four commands known."""
    websocket_api.async_register_command(hass, websocket_instruments)
    websocket_api.async_register_command(hass, websocket_history)
    websocket_api.async_register_command(hass, websocket_performance)
    websocket_api.async_register_command(hass, websocket_details)
    websocket_api.async_register_command(hass, websocket_news)
    websocket_api.async_register_command(hass, websocket_card_version)
