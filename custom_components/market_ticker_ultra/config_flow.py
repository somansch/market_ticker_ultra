"""Setting up Market Ticker Ultra, and adding instruments to it."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import voluptuous as vol

from types import MappingProxyType

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    DateSelector,
    EntitySelector,
    EntitySelectorConfig,
    FileSelector,
    FileSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    Selector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
from homeassistant.util import dt as dt_util

from .const import (
    ALL_SOURCES,
    BENCHMARKS,
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
    CONF_NEWS_GOOGLE,
    CONF_BASE_CURRENCY,
    CONF_BENCHMARK,
    CONF_COLOR,
    THEME_COLORS,
    CONF_CURRENCY,
    CONF_EXCHANGE,
    CONF_GROUP,
    CONF_ISIN,
    CONF_KIND,
    CONF_LISTING,
    CONF_LOGO_FILE,
    CONF_LOGOS,
    CONF_NAME,
    CONF_QUERY,
    CONF_SCAN_INTERVAL,
    CONF_SOURCE,
    CONF_SOURCES,
    CONF_SYMBOL,
    CONF_TRADINGVIEW,
    CONF_TRADINGVIEW_FOUND,
    CONF_TYPE,
    DEFAULT_ALERT_PERSISTENT,
    DEFAULT_LOGOS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    KIND_PORTFOLIO,
    KIND_WATCHLIST,
    KIND_SETTINGS,
    KINDS,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SETTINGS_UNIQUE_ID,
    SOURCE_YAHOO,
    SUBENTRY_INSTRUMENT,
)
from .localized import decimal_comma, text as local_text
from .groups import (
    async_new_group,
    group_entries,
    is_group,
    is_portfolio,
    settings_entry,
    settings_options,
    settings_title,
)
from .holdings import (
    CONF_LOTS,
    LOT_DATE,
    LOT_FEES,
    LOT_PRICE,
    LOT_QUANTITY,
    LOT_TAXES,
    clean_lots,
    holding_from_lots,
    ledger_from_lots,
)
from .logos import OWN_LOGO_TYPES, remove_own_logo, store_own_logo
from .providers import Listing, Provider, ProviderError, Quote
from .tradingview import (
    clean_own_symbol,
    found_symbol,
    frankfurt_isin,
    lookup_frankfurt,
    tradingview_symbol,
)
from .providers.boerse_frankfurt import BoerseFrankfurtProvider
from .providers.ecb import EcbProvider
from .providers.goldapi import GoldApiProvider
from .providers.kraken import KrakenProvider
from .providers.yahoo import YahooProvider, is_isin

# How many venues the choice offers at most, and how many of one source.
_MAX_LISTINGS = 20
_PER_SOURCE = 12

_CURRENCY = re.compile(r"^[A-Z]{3}$")

CONF_ADD_ANOTHER = "add_another"
CONF_REMOVE = "remove"
CONF_FILE = "file"
CONF_REMOVE_LOGO = "remove_logo"
# Where a purchase on a watchlist takes the instrument, and where the sale
# of the last of a position leaves it.
CONF_TARGET = "target"
CONF_AFTER_SALE = "after_sale"
_NEW = "new"
_KEEP = "keep"
_DELETE = "delete"
# Ticked in the settings: a test message to everybody an alert tells. Not
# kept - it is a button, not a setting.
CONF_ALERT_TEST = "alert_test"
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class UiColorSelector(Selector[dict[str, Any]]):
    """Home Assistant's colour picker: its own colours with their swatches,
    and whatever colour is typed into its search. The frontend has this
    selector; the Python side has no class for it yet, so here is one."""

    selector_type = "ui_color"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})

    def __call__(self, data: Any) -> str:
        return str(vol.Schema(str)(data)).strip()

_QUANTITY = NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=0, step="any"))
_PRICE = NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=0, step="any"))


def _settings_schema(
    interval: int,
    logos: bool,
    base_currency: str,
    sources: list[str],
    alerts: tuple[list[str], bool, bool] | None = None,
    more: dict[str, Any] | None = None,
) -> vol.Schema:
    """The settings' form. `alerts` - who is told about a price alert, and
    whether Home Assistant notes it itself - is there afterwards only: at
    first set-up there is no instrument yet to have one."""
    told: dict[Any, Any] = {}
    if alerts is not None:
        told = {
            vol.Optional(CONF_ALERT_NOTIFY, default=alerts[0]): EntitySelector(
                EntitySelectorConfig(domain="notify", multiple=True)
            ),
            vol.Required(CONF_ALERT_PERSISTENT, default=alerts[1]): BooleanSelector(),
            # Mail and the messengers: notify services, chosen among those
            # there are - or written, for one that is set up later.
            vol.Optional(
                CONF_ALERT_SERVICES, default=list((more or {}).get(CONF_ALERT_SERVICES) or [])
            ): SelectSelector(
                SelectSelectorConfig(
                    options=list((more or {}).get("services") or []),
                    multiple=True,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_ALERT_SPEAKERS, default=list((more or {}).get(CONF_ALERT_SPEAKERS) or [])
            ): EntitySelector(EntitySelectorConfig(domain="media_player", multiple=True)),
            vol.Optional(
                CONF_ALERT_TTS,
                description={"suggested_value": (more or {}).get(CONF_ALERT_TTS)},
            ): EntitySelector(EntitySelectorConfig(domain="tts")),
            vol.Required(CONF_ALERT_TEST, default=False): BooleanSelector(),
            vol.Required(CONF_NEWS_GOOGLE, default=alerts[2]): BooleanSelector(),
        }
    return vol.Schema(
        {
            **_settings_fields(interval, logos, base_currency, sources),
            **told,
        }
    )


def _settings_fields(
    interval: int, logos: bool, base_currency: str, sources: list[str]
) -> dict[Any, Any]:
    return dict(
        {
            vol.Required(CONF_SCAN_INTERVAL, default=interval): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=MAX_SCAN_INTERVAL,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            vol.Required(CONF_LOGOS, default=logos): BooleanSelector(),
            vol.Required(CONF_BASE_CURRENCY, default=base_currency): TextSelector(),
            vol.Required(CONF_SOURCES, default=sources): SelectSelector(
                SelectSelectorConfig(
                    options=list(ALL_SOURCES),
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                    translation_key="sources",
                )
            ),
        }
    )


def _settings(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_ALERT_NOTIFY: list(user_input.get(CONF_ALERT_NOTIFY) or []),
        CONF_ALERT_PERSISTENT: bool(user_input.get(CONF_ALERT_PERSISTENT, DEFAULT_ALERT_PERSISTENT)),
        CONF_ALERT_SERVICES: [
            str(name).strip() for name in user_input.get(CONF_ALERT_SERVICES) or [] if str(name).strip()
        ],
        CONF_ALERT_SPEAKERS: list(user_input.get(CONF_ALERT_SPEAKERS) or []),
        CONF_ALERT_TTS: user_input.get(CONF_ALERT_TTS) or None,
        CONF_NEWS_GOOGLE: bool(user_input.get(CONF_NEWS_GOOGLE, False)),
        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
        CONF_LOGOS: bool(user_input[CONF_LOGOS]),
        CONF_BASE_CURRENCY: str(user_input[CONF_BASE_CURRENCY]).strip().upper(),
        # In the order they are listed in, whatever order they were ticked in.
        CONF_SOURCES: [
            source for source in ALL_SOURCES if source in (user_input.get(CONF_SOURCES) or [])
        ],
    }


def _notify_services(hass: HomeAssistant) -> list[str]:
    """The notify services there are, by their full name - without the two
    that are not somebody to tell: the entities' own, and Home Assistant's
    note, which has its own switch."""
    names = hass.services.async_services().get("notify", {})
    return sorted(
        f"notify.{name}" for name in names if name not in ("send_message", "persistent_notification")
    )


async def _async_test_alert(hass: HomeAssistant) -> None:
    """A test message to everybody an alert tells - a few seconds on, when
    the settings just saved are the ones in use."""
    await asyncio.sleep(4)
    coordinator = hass.data.get(DOMAIN)
    if coordinator is None:
        return
    comma = decimal_comma(hass)
    # In the alert's own words, with an example in the variables' places.
    title, message, spoken = coordinator.alert_texts(
        {
            "name": "Test",
            "symbol": "TEST",
            "price": "123,45 EUR" if comma else "123.45 EUR",
            "limit": "120,00 EUR" if comma else "120.00 EUR",
            "currency": "EUR",
            "direction": local_text(hass, "direction_above"),
            "change": "+1,25 %" if comma else "+1.25 %",
        }
    )
    coordinator.tell_alert(title, message, f"{DOMAIN}_alert_test", {"test": True}, spoken)


def _settings_errors(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    code = str(user_input.get(CONF_BASE_CURRENCY) or "").strip().upper()
    if not _CURRENCY.match(code):
        errors[CONF_BASE_CURRENCY] = "invalid_currency"
    if not user_input.get(CONF_SOURCES):
        errors[CONF_SOURCES] = "no_source"
    return errors


def _group_schema(kind: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME): TextSelector(),
            vol.Required(CONF_KIND, default=kind): SelectSelector(
                SelectSelectorConfig(
                    options=list(KINDS),
                    mode=SelectSelectorMode.LIST,
                    translation_key="group_kind",
                )
            ),
            # The index a portfolio is compared with: one of the list, or
            # any symbol of Yahoo Finance typed in.
            vol.Optional(CONF_BENCHMARK): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": symbol, "label": name} for symbol, name in BENCHMARKS.items()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
        }
    )


async def _benchmark_error(hass: Any, user_input: dict[str, Any]) -> dict[str, str]:
    """Whether the index named can be asked for at all."""
    symbol = str(user_input.get(CONF_BENCHMARK) or "").strip().upper()
    if not symbol:
        return {}
    try:
        await YahooProvider(async_get_clientsession(hass)).history(symbol, "1mo")
    except ProviderError:
        return {CONF_BENCHMARK: "invalid_benchmark"}
    return {}


def _benchmark_option(user_input: dict[str, Any]) -> dict[str, Any]:
    symbol = str(user_input.get(CONF_BENCHMARK) or "").strip().upper()
    return {CONF_BENCHMARK: symbol} if symbol else {}


class MarketTickerUltraConfigFlow(ConfigFlow, domain=DOMAIN):
    """The first time: the settings, which become an entry of their own and
    bring the first two groups with them. Every time after: a new group."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MarketTickerUltraOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        # Instruments are added to a group; the settings have none.
        return {SUBENTRY_INSTRUMENT: InstrumentSubentryFlow} if is_group(config_entry) else {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """A new group - or, where there is nothing yet, the settings."""
        if settings_entry(self.hass) is None:
            return await self.async_step_settings()
        errors: dict[str, str] = {}
        if user_input is not None and user_input[CONF_NAME].strip():
            errors = await _benchmark_error(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME].strip(),
                    data={CONF_KIND: user_input[CONF_KIND]},
                    options=_benchmark_option(user_input),
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _group_schema(KIND_PORTFOLIO), user_input or {}
            ),
            errors=errors,
        )

    async def async_step_import(self, data: dict[str, Any]) -> ConfigFlowResult:
        """A group made by the integration itself: one of the first two, or
        one an older installation is taken apart into."""
        kind = data.get(CONF_KIND) if data.get(CONF_KIND) in KINDS else KIND_PORTFOLIO
        return self.async_create_entry(
            title=str(data.get(CONF_NAME) or "").strip() or "Portfolio", data={CONF_KIND: kind}
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _settings_errors(user_input)
            if not errors:
                await self.async_set_unique_id(SETTINGS_UNIQUE_ID)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=settings_title(self.hass),
                    data={CONF_KIND: KIND_SETTINGS},
                    options=_settings(user_input),
                )
        shown = user_input or {}
        return self.async_show_form(
            step_id="settings",
            data_schema=_settings_schema(
                int(shown.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                bool(shown.get(CONF_LOGOS, DEFAULT_LOGOS)),
                str(shown.get(CONF_BASE_CURRENCY, self.hass.config.currency)),
                list(shown.get(CONF_SOURCES, ALL_SOURCES)),
            ),
            errors=errors,
        )


class MarketTickerUltraOptionsFlow(OptionsFlow):
    """The settings, afterwards - or, of a group, its name and its kind."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if is_group(self.config_entry):
            return await self.async_step_group(user_input)
        return await self.async_step_settings(user_input)

    async def async_step_group(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None and user_input[CONF_NAME].strip():
            errors = await _benchmark_error(self.hass, user_input)
            if not errors:
                self.hass.config_entries.async_update_entry(
                    entry,
                    title=user_input[CONF_NAME].strip(),
                    data={**entry.data, CONF_KIND: user_input[CONF_KIND]},
                )
                kept = {key: value for key, value in entry.options.items() if key != CONF_BENCHMARK}
                return self.async_create_entry(data={**kept, **_benchmark_option(user_input)})
        return self.async_show_form(
            step_id="group",
            data_schema=self.add_suggested_values_to_schema(
                _group_schema(entry.data.get(CONF_KIND) or KIND_PORTFOLIO),
                user_input
                or {CONF_NAME: entry.title, CONF_BENCHMARK: entry.options.get(CONF_BENCHMARK)},
            ),
            errors=errors,
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The settings, a page for each kind of them."""
        return self.async_show_menu(
            step_id="settings",
            menu_options=["general", "sources", "alert_targets", "alert_texts"],
        )

    def _saved(self, changed: dict[str, Any]) -> ConfigFlowResult:
        """One page's settings, with those of the other pages as they are."""
        return self.async_create_entry(data={**self.config_entry.options, **changed})

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code = str(user_input.get(CONF_BASE_CURRENCY) or "").strip().upper()
            if not _CURRENCY.match(code):
                errors[CONF_BASE_CURRENCY] = "invalid_currency"
            else:
                return self._saved(
                    {
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                        CONF_BASE_CURRENCY: code,
                        CONF_LOGOS: bool(user_input[CONF_LOGOS]),
                    }
                )
        shown = user_input or self.config_entry.options
        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=int(shown.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    ),
                    vol.Required(
                        CONF_BASE_CURRENCY,
                        default=str(shown.get(CONF_BASE_CURRENCY) or self.hass.config.currency),
                    ): TextSelector(),
                    vol.Required(
                        CONF_LOGOS, default=bool(shown.get(CONF_LOGOS, DEFAULT_LOGOS))
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_SOURCES):
                errors[CONF_SOURCES] = "no_source"
            else:
                return self._saved(
                    {
                        # In the order they are listed in, whatever order
                        # they were ticked in.
                        CONF_SOURCES: [
                            source for source in ALL_SOURCES if source in user_input[CONF_SOURCES]
                        ],
                        CONF_NEWS_GOOGLE: bool(user_input.get(CONF_NEWS_GOOGLE, False)),
                    }
                )
        shown = user_input or self.config_entry.options
        return self.async_show_form(
            step_id="sources",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SOURCES,
                        default=list(
                            ALL_SOURCES if shown.get(CONF_SOURCES) is None else shown[CONF_SOURCES]
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=list(ALL_SOURCES),
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                            translation_key="sources",
                        )
                    ),
                    vol.Required(
                        CONF_NEWS_GOOGLE, default=bool(shown.get(CONF_NEWS_GOOGLE, False))
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_alert_targets(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Who is told about a price alert."""
        if user_input is not None:
            if user_input.get(CONF_ALERT_TEST):
                # After the entry is set up again with what was just saved:
                # the test goes to those now named.
                self.hass.async_create_task(_async_test_alert(self.hass))
            return self._saved(
                {
                    CONF_ALERT_PERSISTENT: bool(
                        user_input.get(CONF_ALERT_PERSISTENT, DEFAULT_ALERT_PERSISTENT)
                    ),
                    CONF_ALERT_NOTIFY: list(user_input.get(CONF_ALERT_NOTIFY) or []),
                    CONF_ALERT_SERVICES: [
                        str(name).strip()
                        for name in user_input.get(CONF_ALERT_SERVICES) or []
                        if str(name).strip()
                    ],
                    CONF_ALERT_SPEAKERS: list(user_input.get(CONF_ALERT_SPEAKERS) or []),
                    CONF_ALERT_TTS: user_input.get(CONF_ALERT_TTS) or None,
                }
            )
        shown = self.config_entry.options
        return self.async_show_form(
            step_id="alert_targets",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ALERT_PERSISTENT,
                        default=bool(shown.get(CONF_ALERT_PERSISTENT, DEFAULT_ALERT_PERSISTENT)),
                    ): BooleanSelector(),
                    vol.Optional(
                        CONF_ALERT_NOTIFY, default=list(shown.get(CONF_ALERT_NOTIFY) or [])
                    ): EntitySelector(EntitySelectorConfig(domain="notify", multiple=True)),
                    # Mail and the messengers: notify services, chosen among
                    # those there are - or written, for one set up later.
                    vol.Optional(
                        CONF_ALERT_SERVICES, default=list(shown.get(CONF_ALERT_SERVICES) or [])
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=_notify_services(self.hass),
                            multiple=True,
                            custom_value=True,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_ALERT_SPEAKERS, default=list(shown.get(CONF_ALERT_SPEAKERS) or [])
                    ): EntitySelector(EntitySelectorConfig(domain="media_player", multiple=True)),
                    vol.Optional(
                        CONF_ALERT_TTS,
                        description={"suggested_value": shown.get(CONF_ALERT_TTS)},
                    ): EntitySelector(EntitySelectorConfig(domain="tts")),
                    vol.Required(CONF_ALERT_TEST, default=False): BooleanSelector(),
                }
            ),
        )

    async def async_step_alert_texts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """What a price alert says. The fields show the defaults until they
        are given other words; a text that is the default, or empty, is
        kept as "the default" - so it follows Home Assistant's language."""
        keys = (CONF_ALERT_TITLE, CONF_ALERT_MESSAGE, CONF_ALERT_SPOKEN)
        defaults = {key: local_text(self.hass, key) for key in keys}
        if user_input is not None:
            changed = {}
            for key in keys:
                text = str(user_input.get(key) or "").strip()
                changed[key] = "" if text == defaults[key] else text
            if user_input.get(CONF_ALERT_TEST):
                self.hass.async_create_task(_async_test_alert(self.hass))
            return self._saved(changed)
        shown = self.config_entry.options
        return self.async_show_form(
            step_id="alert_texts",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Optional(CONF_ALERT_TITLE): TextSelector(),
                        vol.Optional(CONF_ALERT_MESSAGE): TextSelector(
                            TextSelectorConfig(multiline=True)
                        ),
                        vol.Optional(CONF_ALERT_SPOKEN): TextSelector(
                            TextSelectorConfig(multiline=True)
                        ),
                        vol.Required(CONF_ALERT_TEST, default=False): BooleanSelector(),
                    }
                ),
                {key: str(shown.get(key) or "").strip() or defaults[key] for key in keys},
            ),
            # The variables' names, shown as they are written.
            description_placeholders={
                name: "{" + name + "}"
                for name in ("name", "symbol", "price", "limit", "currency", "direction", "change")
            },
        )


def _listing_label(listing: Listing, quote: Quote | None) -> str:
    """One line of the venue choice: what, where, and what it last cost.

    The price and its day are what tell a live venue from a dead one - the
    same fund is quoted at a dozen exchanges, and some of those quotes are
    weeks old.
    """
    parts = [listing.name] if listing.symbol == listing.name else [listing.symbol, listing.name]
    if listing.exchange:
        parts.append(listing.exchange)
    if quote is not None:
        price = f"{quote.price:.{quote.precision}f} {quote.currency or ''}".strip()
        if quote.quote_time is not None:
            traded = dt_util.as_local(quote.quote_time)
            if traded.date() != dt_util.now().date():
                price += f" ({traded.date().isoformat()})"
        parts.append(price)
    return " · ".join(parts)


def _number(value: float) -> str:
    """A figure without the zeros a float prints behind it."""
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _lot_label(lot: dict[str, Any], currency: str) -> str:
    """One purchase, as the list to remove from shows it."""
    text = f"{_number(lot[LOT_QUANTITY])} × {_number(lot[LOT_PRICE])} {currency}".strip()
    return f"{lot[LOT_DATE]} · {text}" if lot.get(LOT_DATE) else text


def _lot_from_input(user_input: dict[str, Any]) -> dict[str, Any] | None:
    """The purchase a form describes - None where it is left empty."""
    quantity = user_input.get(LOT_QUANTITY)
    price = user_input.get(LOT_PRICE)
    if quantity in (None, "") or price in (None, ""):
        return None
    lots = clean_lots(
        [
            {
                LOT_QUANTITY: quantity,
                LOT_PRICE: price,
                LOT_DATE: user_input.get(LOT_DATE),
                LOT_FEES: user_input.get(LOT_FEES),
                LOT_TAXES: user_input.get(LOT_TAXES),
            }
        ]
    )
    return lots[0] if lots else None


def _lot_schema(required: bool, add_another: bool) -> vol.Schema:
    marker = vol.Required if required else vol.Optional
    fields: dict[Any, Any] = {
        marker(LOT_QUANTITY): _QUANTITY,
        marker(LOT_PRICE): _PRICE,
        vol.Optional(LOT_DATE): DateSelector(),
        vol.Optional(LOT_FEES): _PRICE,
        vol.Optional(LOT_TAXES): _PRICE,
    }
    if add_another:
        fields[vol.Required(CONF_ADD_ANOTHER, default=False)] = BooleanSelector()
    return vol.Schema(fields)


class InstrumentSubentryFlow(ConfigSubentryFlow):
    """Add one instrument - search, pick the venue, say what is held - and
    change it afterwards: its name and its purchases."""

    def __init__(self) -> None:
        self._query = ""
        self._listings: dict[str, Listing] = {}
        self._quotes: dict[str, Quote] = {}
        self._chosen: Listing | None = None
        self._lots: list[dict[str, Any]] = []


    def _providers(self) -> list[Provider]:
        """Every source, in the order their finds are listed in.

        The ones that only know one kind of thing come first: they find
        something only when the search clearly is for it - a currency pair,
        a metal, a coin - and then theirs is the cleanest quote there is.
        """
        entry = self._get_entry()
        chosen = settings_options(self.hass).get(CONF_SOURCES)
        enabled = set(ALL_SOURCES if chosen is None else chosen)
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            return [coordinator.providers[key] for key in ALL_SOURCES if key in enabled]
        session = async_get_clientsession(self.hass)
        providers: list[Provider] = [
            EcbProvider(session),
            GoldApiProvider(session),
            KrakenProvider(session),
            YahooProvider(session),
            BoerseFrankfurtProvider(session),
        ]
        return [provider for provider in providers if provider.key in enabled]

    @staticmethod
    def _known(entry: ConfigEntry) -> set[str]:
        """The listings a group already has - the same listing may stand in
        a second group, with purchases of its own."""
        return {
            f"{subentry.data.get(CONF_SOURCE) or SOURCE_YAHOO}:{subentry.data.get(CONF_SYMBOL)}"
            for subentry in entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_INSTRUMENT
        }

    def _other_groups(self) -> list[dict[str, str]]:
        """The groups an instrument of this one could move to."""
        here = self._get_entry().entry_id
        return [
            {"value": entry.entry_id, "label": entry.title}
            for entry in group_entries(self.hass)
            if entry.entry_id != here
        ]

    # ------------------------------------------------------------- adding

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._query = user_input[CONF_QUERY].strip()
            providers = self._providers()

            async def search(provider: Provider) -> list[Listing] | None:
                try:
                    return (await provider.search(self._query))[:_PER_SOURCE]
                except ProviderError:
                    return None

            answers = await asyncio.gather(*(search(provider) for provider in providers))
            found = [listing for answer in answers if answer for listing in answer]
            if not found:
                # Nothing because nobody could be asked, or because there
                # is nothing: two different things to say.
                errors["base"] = (
                    "cannot_connect" if all(a is None for a in answers) else "nothing_found"
                )
            else:
                found = found[:_MAX_LISTINGS]
                self._listings = {f"{l.source}:{l.symbol}": l for l in found}

                async def quote(provider: Provider) -> dict[str, Quote]:
                    symbols = [l.symbol for l in found if l.source == provider.key]
                    if not symbols:
                        return {}
                    try:
                        answered = await provider.quotes(symbols)
                    except ProviderError:
                        # The choice works without prices too.
                        return {}
                    return {f"{provider.key}:{s}": q for s, q in answered.items()}

                self._quotes = {}
                for answered in await asyncio.gather(*(quote(p) for p in providers)):
                    self._quotes.update(answered)
                return await self.async_step_listing()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_QUERY): TextSelector()}),
                {CONF_QUERY: self._query},
            ),
            errors=errors,
            last_step=False,
        )

    async def async_step_listing(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_LISTING]
            if key in self._known(self._get_entry()):
                errors["base"] = "already_configured"
            else:
                self._chosen = self._listings[key]
                if not is_portfolio(self._get_entry()):
                    # A watchlist holds nothing: nothing to ask.
                    return await self._create(None)
                return await self.async_step_holding()

        labels = {provider.key: provider.label for provider in self._providers()}
        options = [
            {
                "value": key,
                "label": _listing_label(listing, self._quotes.get(key))
                + (
                    f" · {labels[listing.source]}"
                    if labels.get(listing.source) and labels[listing.source] != listing.exchange
                    else ""
                ),
            }
            for key, listing in self._listings.items()
        ]
        return self.async_show_form(
            step_id="listing",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LISTING, default=options[0]["value"]): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                    )
                }
            ),
            description_placeholders={"query": self._query},
            errors=errors,
            last_step=False,
        )

    async def async_step_holding(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """What is held of it - or nothing, for an instrument that is only
        watched."""
        listing = self._chosen
        assert listing is not None
        quote = self._quotes.get(f"{listing.source}:{listing.symbol}")
        currency = (quote.currency if quote else None) or ""
        if user_input is not None:
            return await self._create(_lot_from_input(user_input))
        return self.async_show_form(
            step_id="holding",
            data_schema=_lot_schema(required=False, add_another=False),
            description_placeholders={"name": listing.name, "currency": currency},
            last_step=True,
        )

    async def _create(self, lot: dict[str, Any] | None) -> SubentryFlowResult:
        """The new instrument, in the group chosen for it."""
        listing = self._chosen
        assert listing is not None
        quote = self._quotes.get(f"{listing.source}:{listing.symbol}")
        currency = (quote.currency if quote else None) or ""
        data: dict[str, Any] = {
            CONF_SOURCE: listing.source,
            CONF_SYMBOL: listing.symbol,
            CONF_NAME: listing.name,
            CONF_EXCHANGE: (quote.exchange if quote else None) or listing.exchange,
            CONF_TYPE: (quote.type if quote else None) or listing.type,
            CONF_CURRENCY: currency or None,
            CONF_LOTS: [lot] if lot else [],
        }
        if is_isin(self._query):
            data[CONF_ISIN] = self._query.upper()
        elif listing.source == "boerse_frankfurt":
            # Its symbols carry the ISIN.
            data[CONF_ISIN] = listing.symbol.partition(":")[2]
        # What TradingView calls it, for the card's link: looked up now
        # where it cannot be worked out. Not answered in time, it is
        # asked again when the entry is set up.
        pair = frankfurt_isin(data)
        if pair:
            looked_up = await lookup_frankfurt(async_get_clientsession(self.hass), [pair])
            if pair in looked_up:
                data[CONF_TRADINGVIEW_FOUND] = looked_up[pair]
        return self.async_create_entry(
            title=listing.name,
            data=data,
            unique_id=f"{listing.source}:{listing.symbol}",
        )

    # ----------------------------------------------------------- changing

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        self._lots = clean_lots(subentry.data.get(CONF_LOTS))
        options = ["rename"]
        if self._other_groups():
            options.append("move")
        # A purchase on a watchlist takes the instrument into a portfolio
        # (see async_step_to_portfolio); taking purchases out again is a
        # portfolio's business.
        options.append("add_lot")
        held = holding_from_lots(self._lots)
        if is_portfolio(self._get_entry()) and held and held.quantity > 0:
            options.append("sell_lot")
        if is_portfolio(self._get_entry()) and self._lots:
            options.append("remove_lots")
        options.append("alerts")
        options.append("color")
        options.append("logo")
        options.append("tradingview")
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=options,
            description_placeholders=self._summary(),
        )

    def _summary(self) -> dict[str, str]:
        """What the forms say about the instrument and what is held of it."""
        subentry = self._get_reconfigure_subentry()
        currency = subentry.data.get(CONF_CURRENCY) or ""
        holding = holding_from_lots(self._lots)
        average = holding.average_price if holding else None
        ledger = ledger_from_lots(self._lots)
        return {
            "realized": f"{ledger.realized:.2f} {currency}".strip(),
            "name": subentry.title,
            "symbol": subentry.data.get(CONF_SYMBOL, ""),
            "currency": currency,
            "count": str(len(self._lots)),
            "quantity": _number(holding.quantity) if holding else "0",
            "average": f"{average:.2f} {currency}".strip() if average is not None else "-",
        }

    def _save_lots(self) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        return self.async_update_and_abort(
            self._get_entry(), subentry, data={**subentry.data, CONF_LOTS: self._lots}
        )

    async def async_step_rename(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Another name for an instrument - what its device and sensor are called."""
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            name = user_input[CONF_NAME].strip() or subentry.data.get(CONF_NAME) or subentry.title
            return self.async_update_and_abort(self._get_entry(), subentry, title=name)
        return self.async_show_form(
            step_id="rename",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_NAME): TextSelector()}),
                {CONF_NAME: subentry.title},
            ),
            description_placeholders=self._summary(),
        )

    async def async_step_move(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Into another group: out of this entry, into that one - with the
        id it has, so that its sensors and whatever names it stay the same."""
        subentry = self._get_reconfigure_subentry()
        data = subentry.data
        errors: dict[str, str] = {}
        groups = self._other_groups()
        if user_input is not None:
            target = self.hass.config_entries.async_get_entry(user_input[CONF_GROUP])
            listing = f"{data.get(CONF_SOURCE) or SOURCE_YAHOO}:{data.get(CONF_SYMBOL)}"
            if target is None or listing in self._known(target):
                errors["base"] = "already_configured"
            else:
                moved = ConfigSubentry(
                    data=MappingProxyType(dict(data)),
                    subentry_id=subentry.subentry_id,
                    subentry_type=SUBENTRY_INSTRUMENT,
                    title=subentry.title,
                    unique_id=subentry.unique_id,
                )
                self.hass.config_entries.async_remove_subentry(
                    self._get_entry(), subentry.subentry_id
                )
                self.hass.config_entries.async_add_subentry(target, moved)
                return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(
            step_id="move",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GROUP, default=groups[0]["value"]): SelectSelector(
                        SelectSelectorConfig(options=groups, mode=SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
            description_placeholders=self._summary(),
            errors=errors,
        )

    async def async_step_alerts(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """The two price limits - each there, or left empty for none."""
        subentry = self._get_reconfigure_subentry()
        data = subentry.data
        if user_input is not None:
            changed = {
                key: value
                for key, value in data.items()
                if key not in (CONF_ALERT_BELOW, CONF_ALERT_ABOVE)
            }
            for key in (CONF_ALERT_BELOW, CONF_ALERT_ABOVE):
                try:
                    limit = float(user_input.get(key))
                except (TypeError, ValueError):
                    continue
                if limit > 0:
                    changed[key] = limit
            return self.async_update_and_abort(self._get_entry(), subentry, data=changed)
        return self.async_show_form(
            step_id="alerts",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {vol.Optional(CONF_ALERT_BELOW): _PRICE, vol.Optional(CONF_ALERT_ABOVE): _PRICE}
                ),
                {
                    key: data[key]
                    for key in (CONF_ALERT_BELOW, CONF_ALERT_ABOVE)
                    if data.get(key)
                },
            ),
            description_placeholders=self._summary(),
        )

    async def async_step_color(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """A colour of its own - what the instrument is drawn in among a
        portfolio's shares - or the one it has away again."""
        subentry = self._get_reconfigure_subentry()
        data = subentry.data
        current = str(data.get(CONF_COLOR) or "")
        errors: dict[str, str] = {}
        if user_input is not None:
            changed = {key: value for key, value in data.items() if key != CONF_COLOR}
            # An emptied field takes the colour away again.
            picked = str(user_input.get(CONF_COLOR) or "").strip()
            if picked and picked not in THEME_COLORS and not _HEX_COLOR.match(picked):
                errors[CONF_COLOR] = "invalid_color"
            else:
                if picked:
                    changed[CONF_COLOR] = picked.lower()
                return self.async_update_and_abort(self._get_entry(), subentry, data=changed)
            current = picked
        return self.async_show_form(
            step_id="color",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Optional(CONF_COLOR): UiColorSelector()}),
                {CONF_COLOR: current} if current else {},
            ),
            errors=errors,
            description_placeholders=self._summary(),
        )

    async def async_step_tradingview(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """The instrument's symbol at TradingView, for the card's link to it."""
        subentry = self._get_reconfigure_subentry()
        data = subentry.data
        errors: dict[str, str] = {}
        found = tradingview_symbol(
            data.get(CONF_SOURCE) or SOURCE_YAHOO,
            data.get(CONF_SYMBOL, ""),
            data.get(CONF_EXCHANGE),
            data.get(CONF_TYPE),
            data.get(CONF_CURRENCY),
        ) or found_symbol(data)
        if user_input is not None:
            typed = (user_input.get(CONF_TRADINGVIEW) or "").strip()
            own = clean_own_symbol(typed)
            if typed and own is None:
                errors[CONF_TRADINGVIEW] = "invalid_tradingview"
            else:
                changed = {key: value for key, value in data.items() if key != CONF_TRADINGVIEW}
                # The field comes filled with the symbol in use: left as the
                # one worked out, it is not the user's own - and follows
                # what is worked out from then on too.
                if own and own != found:
                    changed[CONF_TRADINGVIEW] = own
                return self.async_update_and_abort(self._get_entry(), subentry, data=changed)
        return self.async_show_form(
            step_id="tradingview",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Optional(CONF_TRADINGVIEW): TextSelector()}),
                {
                    # What the link uses now: the user's own symbol, else
                    # the one worked out.
                    CONF_TRADINGVIEW: (user_input or {}).get(CONF_TRADINGVIEW)
                    or clean_own_symbol(data.get(CONF_TRADINGVIEW))
                    or found
                    or ""
                },
            ),
            errors=errors,
            description_placeholders={**self._summary(), "found": found or "-"},
        )

    async def async_step_logo(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """A logo of one's own for the instrument - or the uploaded one away."""
        subentry = self._get_reconfigure_subentry()
        has_own = bool(subentry.data.get(CONF_LOGO_FILE))
        errors: dict[str, str] = {}
        if user_input is not None:
            config_dir = self.hass.config.config_dir
            uploaded = user_input.get(CONF_FILE)
            data = dict(subentry.data)
            if uploaded:

                def _store() -> str:
                    with process_uploaded_file(self.hass, uploaded) as path:
                        return store_own_logo(config_dir, subentry.subentry_id, path)

                try:
                    data[CONF_LOGO_FILE] = await self.hass.async_add_executor_job(_store)
                except ValueError as err:
                    errors["base"] = (
                        "logo_too_large" if str(err) == "size" else "logo_wrong_type"
                    )
            elif user_input.get(CONF_REMOVE_LOGO):
                await self.hass.async_add_executor_job(
                    remove_own_logo, config_dir, subentry.subentry_id
                )
                data.pop(CONF_LOGO_FILE, None)
            if not errors:
                # Always a change, so that the entry reloads and a replaced
                # image under the same name is picked up.
                data["logo_changed"] = dt_util.utcnow().isoformat()
                return self.async_update_and_abort(self._get_entry(), subentry, data=data)

        fields: dict[Any, Any] = {
            vol.Optional(CONF_FILE): FileSelector(
                FileSelectorConfig(accept=",".join(OWN_LOGO_TYPES))
            )
        }
        if has_own:
            fields[vol.Required(CONF_REMOVE_LOGO, default=False)] = BooleanSelector()
        return self.async_show_form(
            step_id="logo",
            data_schema=vol.Schema(fields),
            description_placeholders=self._summary(),
            errors=errors,
        )

    async def async_step_add_lot(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """One more purchase."""
        return await self._async_lot_step("add_lot", user_input)

    async def async_step_sell_lot(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """A sale: entered as what was sold, kept as a negative quantity."""
        return await self._async_lot_step("sell_lot", user_input)

    async def _async_lot_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        """The form of a purchase or of a sale. Both ask for a quantity above
        zero; a sale cannot take out more than there is."""
        sale = step_id == "sell_lot"
        errors: dict[str, str] = {}
        if user_input is not None:
            lot = _lot_from_input(user_input)
            if lot is None or lot[LOT_QUANTITY] <= 0:
                errors["base"] = "invalid_lot"
            else:
                held = holding_from_lots(self._lots)
                if sale and lot[LOT_QUANTITY] > (held.quantity if held else 0.0) + 1e-9:
                    errors["base"] = "sell_too_many"
                else:
                    if sale:
                        # A sale has a day: without one it could not be put
                        # behind the purchases it takes from.
                        lot = {
                            **lot,
                            LOT_QUANTITY: -lot[LOT_QUANTITY],
                            LOT_DATE: lot.get(LOT_DATE) or dt_util.now().date().isoformat(),
                        }
                    self._lots.append(lot)
                    if not user_input.get(CONF_ADD_ANOTHER):
                        return await self._async_after_lots()
                    user_input = None
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                _lot_schema(required=True, add_another=True),
                user_input or ({LOT_DATE: dt_util.now().date().isoformat()} if sale else {}),
            ),
            description_placeholders=self._summary(),
            errors=errors,
        )

    def _moved(self, target: ConfigEntry) -> SubentryFlowResult:
        """Out of this entry, into that one - with the purchases as they
        stand now, and with the id it has, so that its sensors and whatever
        names it stay the same."""
        subentry = self._get_reconfigure_subentry()
        moved = ConfigSubentry(
            data=MappingProxyType({**subentry.data, CONF_LOTS: self._lots}),
            subentry_id=subentry.subentry_id,
            subentry_type=SUBENTRY_INSTRUMENT,
            title=subentry.title,
            unique_id=subentry.unique_id,
        )
        self.hass.config_entries.async_remove_subentry(self._get_entry(), subentry.subentry_id)
        self.hass.config_entries.async_add_subentry(target, moved)
        return self.async_abort(reason="reconfigure_successful")

    async def _async_after_lots(self) -> SubentryFlowResult:
        """What follows the purchases and sales just entered: on a watchlist
        the way into a portfolio, after the sale of the last of a position
        the question where the instrument goes, else nothing."""
        subentry = self._get_reconfigure_subentry()
        if not is_portfolio(self._get_entry()):
            return await self.async_step_to_portfolio()
        before = holding_from_lots(clean_lots(subentry.data.get(CONF_LOTS)))
        after = holding_from_lots(self._lots)
        if before and before.quantity > 0 and (after is None or after.quantity <= 0):
            return await self.async_step_sold_out()
        return self._save_lots()

    async def async_step_to_portfolio(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """A purchase on a watchlist: the instrument goes into a portfolio
        with it - one there is, or a new one, the first or one more."""
        subentry = self._get_reconfigure_subentry()
        data = subentry.data
        listing = f"{data.get(CONF_SOURCE) or SOURCE_YAHOO}:{data.get(CONF_SYMBOL)}"
        portfolios = [
            entry
            for entry in group_entries(self.hass)
            if is_portfolio(entry) and listing not in self._known(entry)
        ]
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = user_input.get(CONF_TARGET)
            if chosen == _NEW:
                taken = {entry.title for entry in group_entries(self.hass)}
                name = str(user_input.get(CONF_NAME) or "").strip() or local_text(self.hass, "portfolio")
                if name in taken:
                    errors[CONF_NAME] = "group_exists"
                else:
                    target = await async_new_group(self.hass, name, KIND_PORTFOLIO)
                    if target is None:
                        errors["base"] = "cannot_connect"
                    else:
                        return self._moved(target)
            else:
                target = next((entry for entry in portfolios if entry.entry_id == chosen), None)
                if target is None:
                    errors["base"] = "already_configured"
                else:
                    return self._moved(target)
        # What is not a name is worded by the translations (translation_key),
        # in the language of whoever has the dialog open.
        options = [{"value": entry.entry_id, "label": entry.title} for entry in portfolios]
        options.append({"value": _NEW, "label": "➕"})
        return self.async_show_form(
            step_id="to_portfolio",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_TARGET, default=options[0]["value"]): SelectSelector(
                            SelectSelectorConfig(
                                options=options,
                                mode=SelectSelectorMode.LIST,
                                translation_key="to_portfolio",
                            )
                        ),
                        vol.Optional(CONF_NAME): TextSelector(),
                    }
                ),
                user_input or {},
            ),
            description_placeholders=self._summary(),
            errors=errors,
        )

    async def async_step_sold_out(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Everything of a position is sold: it stays in the portfolio, goes
        to a watchlist - with its purchases and sales, which keep what it
        has earned -, or is removed."""
        watchlists = [entry for entry in group_entries(self.hass) if not is_portfolio(entry)]
        subentry = self._get_reconfigure_subentry()
        data = subentry.data
        listing = f"{data.get(CONF_SOURCE) or SOURCE_YAHOO}:{data.get(CONF_SYMBOL)}"
        free = [entry for entry in watchlists if listing not in self._known(entry)]
        if user_input is not None:
            chosen = user_input.get(CONF_AFTER_SALE)
            if chosen == _DELETE:
                self.hass.config_entries.async_remove_subentry(self._get_entry(), subentry.subentry_id)
                return self.async_abort(reason="reconfigure_successful")
            if chosen == _NEW:
                target = await async_new_group(self.hass, "Watchlist", KIND_WATCHLIST)
                if target is not None:
                    return self._moved(target)
            else:
                target = next((entry for entry in free if entry.entry_id == chosen), None)
                if target is not None:
                    return self._moved(target)
            return self._save_lots()
        # A watchlist is named, the other choices are worded by the
        # translations (translation_key) in the language of whoever asks.
        options = [{"value": _KEEP, "label": "Portfolio"}]
        for entry in free:
            options.append({"value": entry.entry_id, "label": f"📂 → {entry.title}"})
        if not watchlists:
            options.append({"value": _NEW, "label": "📂 → Watchlist"})
        options.append({"value": _DELETE, "label": "🗑️"})
        return self.async_show_form(
            step_id="sold_out",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AFTER_SALE, default=_KEEP): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                            translation_key="after_sale",
                        )
                    )
                }
            ),
            description_placeholders=self._summary(),
        )

    async def async_step_remove_lots(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Take purchases out again."""
        if user_input is not None:
            gone = {int(index) for index in user_input.get(CONF_REMOVE) or []}
            self._lots = [lot for index, lot in enumerate(self._lots) if index not in gone]
            return self._save_lots()
        currency = self._get_reconfigure_subentry().data.get(CONF_CURRENCY) or ""
        options = [
            {"value": str(index), "label": _lot_label(lot, currency)}
            for index, lot in enumerate(self._lots)
        ]
        return self.async_show_form(
            step_id="remove_lots",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_REMOVE, default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=options, multiple=True, mode=SelectSelectorMode.LIST
                        )
                    )
                }
            ),
            description_placeholders=self._summary(),
        )
