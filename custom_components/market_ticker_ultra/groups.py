"""Groups: a watchlist, a portfolio, a second portfolio.

Every group is a config entry of its own - a service on the integration's
page that folds open to its instruments, which are its subentries. A group
is a portfolio, whose purchases are added up, or a watchlist, which is only
watched and counts in no sum. One more entry, listed first, holds the
settings all of them share.

An installation from before - one entry with everything in it - is taken
apart the first time it is set up: the entry becomes the settings, and its
instruments move into the groups they were in (see async_split_old_entry).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant

from .localized import text as local_text
from .const import (
    CONF_GROUP,
    CONF_KIND,
    CONF_NAME,
    DOMAIN,
    KIND_PORTFOLIO,
    KIND_SETTINGS,
    KIND_WATCHLIST,
    KINDS,
    SETTINGS_GEAR,
    SETTINGS_UNIQUE_ID,
    SUBENTRY_GROUP,
    SUBENTRY_INSTRUMENT,
)
from .holdings import CONF_LOTS, clean_lots


@dataclass(frozen=True, slots=True)
class Group:
    """One group: its entry's id, its name and its kind."""

    id: str
    name: str
    kind: str


def settings_title(hass: HomeAssistant) -> str:
    """What the settings' entry is called. The gear in front puts it first
    in the list, which is sorted by name."""
    return f"{SETTINGS_GEAR} {local_text(hass, 'settings')}"


def default_groups(hass: HomeAssistant) -> list[tuple[str, str]]:
    """The two groups a new installation starts with."""
    return [
        (local_text(hass, "portfolio"), KIND_PORTFOLIO),
        (local_text(hass, "watchlist"), KIND_WATCHLIST),
    ]


def settings_entry(hass: HomeAssistant) -> ConfigEntry | None:
    return next(
        (
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.data.get(CONF_KIND) == KIND_SETTINGS
        ),
        None,
    )


def settings_options(hass: HomeAssistant) -> dict[str, Any]:
    """The settings every group shares - empty while there are none."""
    entry = settings_entry(hass)
    return dict(entry.options) if entry else {}


def is_group(entry: ConfigEntry) -> bool:
    return entry.data.get(CONF_KIND) in KINDS


def is_portfolio(entry: ConfigEntry) -> bool:
    """Whether the purchases of a group's instruments are added up."""
    return entry.data.get(CONF_KIND) == KIND_PORTFOLIO


def group_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """The groups, in the order they were added. An entry that is switched
    off is no group for as long as it is."""
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if is_group(entry) and not entry.disabled_by
    ]


def groups_of(hass: HomeAssistant) -> list[Group]:
    return [
        Group(id=entry.entry_id, name=entry.title, kind=entry.data[CONF_KIND])
        for entry in group_entries(hass)
    ]


async def _async_new_group(hass: HomeAssistant, name: str, kind: str) -> ConfigEntry | None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_NAME: name, CONF_KIND: kind}
    )
    return result.get("result")


async def async_new_group(hass: HomeAssistant, name: str, kind: str) -> ConfigEntry | None:
    """One more group - a portfolio or a watchlist - made by a dialog that
    needs it then and there."""
    return await _async_new_group(hass, name, kind)


async def async_ensure_first_groups(hass: HomeAssistant) -> None:
    """Give an installation without any group its first two."""
    if any(is_group(entry) for entry in hass.config_entries.async_entries(DOMAIN)):
        return
    for name, kind in default_groups(hass):
        await _async_new_group(hass, name, kind)


async def async_split_old_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """One entry with everything in it becomes the settings' entry, and its
    instruments move into a group entry each - the groups it had, or the
    first two where it had none.

    The instruments keep their ids, and with them their sensors' ids and
    whatever a card names them by.
    """
    old_groups = [s for s in entry.subentries.values() if s.subentry_type == SUBENTRY_GROUP]
    instruments = [s for s in entry.subentries.values() if s.subentry_type == SUBENTRY_INSTRUMENT]
    plan: list[tuple[str | None, str, str]] = [
        (
            group.subentry_id,
            group.title,
            group.data.get(CONF_KIND) if group.data.get(CONF_KIND) in KINDS else KIND_PORTFOLIO,
        )
        for group in old_groups
    ] or [(None, name, kind) for name, kind in default_groups(hass)]

    def home(subentry: ConfigSubentry) -> int:
        """The place in the plan an instrument goes to."""
        named = subentry.data.get(CONF_GROUP)
        for index, (old_id, _name, _kind) in enumerate(plan):
            if old_id is not None and old_id == named:
                return index
        held = bool(clean_lots(subentry.data.get(CONF_LOTS)))
        wanted = KIND_PORTFOLIO if held else KIND_WATCHLIST
        return next((i for i, (_id, _name, kind) in enumerate(plan) if kind == wanted), 0)

    moves = [(home(subentry), subentry) for subentry in instruments]
    # Out of the old entry first: an id can stand in one entry only.
    for subentry in [*instruments, *old_groups]:
        hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)
    hass.config_entries.async_update_entry(
        entry,
        title=settings_title(hass),
        data={CONF_KIND: KIND_SETTINGS},
        unique_id=SETTINGS_UNIQUE_ID,
    )
    for index, (_old_id, name, kind) in enumerate(plan):
        target = await _async_new_group(hass, name, kind)
        if target is None:
            continue
        for at, subentry in moves:
            if at != index:
                continue
            data = {key: value for key, value in subentry.data.items() if key != CONF_GROUP}
            hass.config_entries.async_add_subentry(
                target,
                ConfigSubentry(
                    data=MappingProxyType(data),
                    subentry_id=subentry.subentry_id,
                    subentry_type=SUBENTRY_INSTRUMENT,
                    title=subentry.title,
                    unique_id=subentry.unique_id,
                ),
            )
