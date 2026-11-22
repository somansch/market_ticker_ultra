"""The price alerts: on while a price stands at or beyond its limit."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MarketTickerUltraConfigEntry
from .const import CONF_EXCHANGE, CONF_SYMBOL, DOMAIN, SUBENTRY_INSTRUMENT
from .coordinator import MarketTickerUltraCoordinator

_SIDES = ("below", "above")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MarketTickerUltraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    # The settings' entry has no instruments, and no subentries either.
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_INSTRUMENT:
            continue
        limits = coordinator.alert_limits(subentry.subentry_id)
        entities = [AlertSensor(coordinator, subentry, side) for side in _SIDES if side in limits]
        for side in _SIDES:
            if side not in limits:
                # The limit taken away: its sensor goes with it, instead of
                # standing there as "no longer provided".
                entity_id = registry.async_get_entity_id(
                    "binary_sensor", DOMAIN, f"{subentry.subentry_id}_alert_{side}"
                )
                if entity_id:
                    registry.async_remove(entity_id)
        if entities:
            async_add_entities(entities, config_subentry_id=subentry.subentry_id)


class AlertSensor(CoordinatorEntity[MarketTickerUltraCoordinator], BinarySensorEntity):
    """One limit of one instrument."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MarketTickerUltraCoordinator, subentry: ConfigSubentry, side: str
    ) -> None:
        super().__init__(coordinator)
        self._id = subentry.subentry_id
        self._side = side
        self._attr_translation_key = f"alert_{side}"
        self._attr_unique_id = f"{subentry.subentry_id}_alert_{side}"
        self._attr_icon = "mdi:bell-arrow-down" if side == "below" else "mdi:bell-arrow-up"
        data = subentry.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer=data.get(CONF_EXCHANGE) or None,
            model=data[CONF_SYMBOL],
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.alert_on(self._id, self._side) is not None

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.alert_on(self._id, self._side)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        quote = data.quotes.get(self._id) if data else None
        return {
            "limit": self.coordinator.alert_limits(self._id).get(self._side),
            "price": quote.price if quote else None,
            "currency": quote.currency if quote else None,
        }
