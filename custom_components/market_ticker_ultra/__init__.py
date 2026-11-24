"""Market Ticker Ultra: quotes from public sources, without an account or a key."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from . import websocket
from .bundle import CARD_RESOURCE_PATHS, async_register_card
from .const import CONF_KIND, CONF_LOGO_FILE, CONF_TRADINGVIEW_FOUND, DOMAIN, KIND_SETTINGS
from .coordinator import MarketTickerUltraCoordinator
from .groups import (
    async_ensure_first_groups,
    async_split_old_entry,
    group_entries,
    is_portfolio,
    settings_entry,
)
from .logo_view import OwnLogoView
from .logos import own_logo_dir, own_logo_url, tidy_own_logos
from .lovelace_resource import async_unregister as async_unregister_resource
from .tradingview import frankfurt_isin, lookup_frankfurt, needs_lookup

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type MarketTickerUltraConfigEntry = ConfigEntry[MarketTickerUltraCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Put the dashboard card in place, once for the domain.

    The card is part of the integration rather than a second thing to
    install, so it is served from here. See bundle.py; websocket.py is what
    the card asks.
    """
    await async_register_card(hass)
    websocket.async_register(hass)

    # The logos users upload for their instruments, kept in the
    # configuration folder and served to who is signed in.
    folder = own_logo_dir(hass.config.config_dir)
    await hass.async_add_executor_job(lambda: folder.mkdir(parents=True, exist_ok=True))
    hass.http.register_view(OwnLogoView())
    return True


def _portfolios(hass: HomeAssistant) -> list[tuple[str, str]]:
    """The portfolios the settings' entry has sums for: id and name."""
    return [(g.entry_id, g.title) for g in group_entries(hass) if is_portfolio(g)]


def _follow_groups(hass: HomeAssistant) -> None:
    """Set the settings' entry up again where its sums no longer fit the
    portfolios there are - one was added, removed, renamed, or changed its
    kind."""
    coordinator = hass.data.get(DOMAIN)
    settings = settings_entry(hass)
    if coordinator is None or settings is None or settings.state is not ConfigEntryState.LOADED:
        return
    if coordinator.summed != _portfolios(hass):
        hass.config_entries.async_schedule_reload(settings.entry_id)


def _coordinator(hass: HomeAssistant) -> MarketTickerUltraCoordinator:
    """The one coordinator of the integration: made for the first entry
    that is set up, and there until the last one is unloaded."""
    coordinator = hass.data.get(DOMAIN)
    if coordinator is None:
        coordinator = hass.data[DOMAIN] = MarketTickerUltraCoordinator(hass)
    return coordinator


async def async_setup_entry(hass: HomeAssistant, entry: MarketTickerUltraConfigEntry) -> bool:
    """Set up one entry: the settings', or a group with its instruments."""
    if CONF_KIND not in entry.data:
        # From before every group was an entry: taken apart, once. What is
        # left of this entry is the settings.
        await async_split_old_entry(hass, entry)

    coordinator = _coordinator(hass)
    entry.runtime_data = coordinator
    # An instrument added, renamed or removed, a group renamed, or a setting
    # changed: set up again. Listened for from here on, not from the end of
    # the setup - an instrument added while the setup is still asking the
    # sources would else stay without a quote until the next poll.
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    if entry.data.get(CONF_KIND) == KIND_SETTINGS:
        coordinator.settings_changed()
        # What its sensors are about to be set up for (see _follow_groups).
        coordinator.summed = _portfolios(hass)
        # A new installation gets its first two groups - beside the setup,
        # which a config flow of the same domain must not wait for. Not a
        # task of this entry: the first group to appear has this entry set
        # up again (see _follow_groups), and that would end the task before
        # the second group is there.
        hass.async_create_background_task(
            async_ensure_first_groups(hass), "market_ticker_ultra first groups"
        )
    else:
        # The uploaded logos: where each is served, and away with those of
        # instruments that were removed - of every group, since they share
        # one folder. Off the event loop - it is the disk.
        files = {
            subentry_id: subentry.data.get(CONF_LOGO_FILE)
            for group in group_entries(hass)
            for subentry_id, subentry in group.subentries.items()
            if subentry.data.get(CONF_LOGO_FILE)
        }
        config_dir = hass.config.config_dir

        def _own_logos() -> dict[str, str]:
            tidy_own_logos(config_dir, set(files.values()))
            urls = {key: own_logo_url(config_dir, name) for key, name in files.items()}
            return {key: url for key, url in urls.items() if url}

        coordinator.own_logos = await hass.async_add_executor_job(_own_logos)
        # Whatever was worked out for this group before is of what it was
        # then: its purchases or its index may be what has changed.
        for key in [key for key in coordinator.performances if key[0] == entry.entry_id]:
            del coordinator.performances[key]
        # Not "first refresh or not ready": a group whose source is down at
        # start still loads, so that instruments can be added and removed -
        # the sensors come back with the first poll that succeeds.
        await coordinator.async_ensure_quotes()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if entry.data.get(CONF_KIND) != KIND_SETTINGS:
        _follow_groups(hass)
    # TradingView's symbols for the instruments that are known by ISIN only
    # and have none yet - added before there was a lookup, or while it gave
    # no answer. Beside the setup, not in its way.
    if any(needs_lookup(subentry.data) for subentry in entry.subentries.values()):
        entry.async_create_background_task(
            hass, _async_look_up_symbols(hass, entry), "market_ticker_ultra TradingView symbols"
        )
    return True


async def _async_look_up_symbols(hass: HomeAssistant, entry: MarketTickerUltraConfigEntry) -> None:
    """Look the missing TradingView symbols up and keep them with their instruments."""
    waiting = {
        subentry_id: frankfurt_isin(subentry.data)
        for subentry_id, subentry in entry.subentries.items()
        if needs_lookup(subentry.data)
    }
    found = await lookup_frankfurt(async_get_clientsession(hass), sorted(set(waiting.values())))
    # All of them in one go: each change asks for the entry to be loaded
    # again, and that takes this task with it.
    for subentry_id, pair in waiting.items():
        subentry = entry.subentries.get(subentry_id)
        if subentry is not None and pair in found:
            hass.config_entries.async_update_subentry(
                entry, subentry, data={**subentry.data, CONF_TRADINGVIEW_FOUND: found[pair]}
            )


async def _async_reload(hass: HomeAssistant, entry: MarketTickerUltraConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MarketTickerUltraConfigEntry) -> bool:
    """Unload the entry - and with the last one, the coordinator."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        others = [
            other
            for other in hass.config_entries.async_entries(DOMAIN)
            if other.entry_id != entry.entry_id and other.state is ConfigEntryState.LOADED
        ]
        if not others:
            coordinator = hass.data.pop(DOMAIN, None)
            if coordinator is not None:
                coordinator.clear_issues()
                await coordinator.async_shutdown()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: MarketTickerUltraConfigEntry) -> None:
    """Take the card back out of the dashboards' resources with the last entry."""
    if hass.config_entries.async_entries(DOMAIN):
        # A group gone: its sums go with it.
        _follow_groups(hass)
        return
    await async_unregister_resource(hass, CARD_RESOURCE_PATHS)
