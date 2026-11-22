"""The price of every instrument, and when the source last answered."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MarketTickerUltraConfigEntry
from .const import (
    CONF_CURRENCY,
    CONF_KIND,
    CONF_EXCHANGE,
    CONF_ISIN,
    CONF_SOURCE,
    CONF_SYMBOL,
    CONF_TYPE,
    DOMAIN,
    KIND_SETTINGS,
    SUBENTRY_INSTRUMENT,
)
from .coordinator import MarketTickerUltraCoordinator
from .groups import group_entries, is_portfolio
from .holdings import (
    CONF_LOTS,
    Holding,
    Ledger,
    Position,
    holding_from_lots,
    ledger_from_lots,
    position_at,
)
from .providers import Quote

_ICONS = {
    "EQUITY": "mdi:chart-line",
    "ETF": "mdi:chart-donut",
    "MUTUALFUND": "mdi:chart-donut",
    "INDEX": "mdi:chart-timeline-variant",
    "FUTURE": "mdi:chart-bell-curve-cumulative",
    "COMMODITY": "mdi:gold",
    "CURRENCY": "mdi:cash-multiple",
    "CRYPTOCURRENCY": "mdi:bitcoin",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MarketTickerUltraConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    if entry.data.get(CONF_KIND) == KIND_SETTINGS:
        # The settings' entry: when a source last answered, every portfolio
        # added up - unavailable while nothing is held anywhere - and each
        # portfolio by itself. All on the one device, so that a group's own
        # entry lists nothing but its instruments.
        sums: list[SensorEntity] = [
            LastUpdateSensor(coordinator, entry),
            TotalValueSensor(coordinator, entry, None),
            TotalGainSensor(coordinator, entry, None),
        ]
        portfolios = [group for group in group_entries(hass) if is_portfolio(group)]
        for group in portfolios:
            sums.append(TotalValueSensor(coordinator, entry, group))
            sums.append(TotalGainSensor(coordinator, entry, group))
        async_add_entities(sums)
        # The sums of a group that is gone, or is a watchlist now.
        kept = {entry.entry_id, *(group.entry_id for group in portfolios)}
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            owner, _, what = entity.unique_id.partition("_total_")
            if what in ("value", "gain") and owner not in kept:
                registry.async_remove(entity.entity_id)
        return

    # A group: its instruments.
    portfolio = is_portfolio(entry)
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_INSTRUMENT:
            continue
        entities: list[SensorEntity] = [PriceSensor(coordinator, subentry)]
        # A watchlist is only watched: whatever purchases an instrument in
        # one still carries, it has no position.
        lots = subentry.data.get(CONF_LOTS) if portfolio else None
        holding = holding_from_lots(lots)
        if holding is not None:
            entities.append(PositionValueSensor(coordinator, subentry, holding))
            entities.append(
                PositionGainSensor(coordinator, subentry, holding, ledger_from_lots(lots))
            )
        else:
            # The last purchase removed: the position's sensors go with it,
            # instead of standing there as "no longer provided".
            _forget(registry, f"{subentry.subentry_id}_position_value")
            _forget(registry, f"{subentry.subentry_id}_position_gain")
        async_add_entities(entities, config_subentry_id=subentry.subentry_id)




def _forget(registry: er.EntityRegistry, unique_id: str) -> None:
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    if entity_id:
        registry.async_remove(entity_id)


def _instrument_device(subentry: ConfigSubentry) -> DeviceInfo:
    data = subentry.data
    return DeviceInfo(
        identifiers={(DOMAIN, subentry.subentry_id)},
        name=subentry.title,
        manufacturer=data.get(CONF_EXCHANGE) or None,
        model=data[CONF_SYMBOL],
        entry_type=DeviceEntryType.SERVICE,
    )


def _entry_device(entry: MarketTickerUltraConfigEntry) -> DeviceInfo:
    """The one device of the settings' entry: what belongs to no instrument."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Market Ticker Ultra",
        entry_type=DeviceEntryType.SERVICE,
    )


class PriceSensor(CoordinatorEntity[MarketTickerUltraCoordinator], SensorEntity):
    """What one instrument costs, with the rest of its quote as attributes."""

    _attr_has_entity_name = True
    # The device's own name: the sensor is the instrument.
    _attr_name = None
    # A measurement, not "monetary": a price has a mean, a low and a high
    # over time, which is what the long-term statistics should keep.
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MarketTickerUltraCoordinator, subentry: ConfigSubentry) -> None:
        super().__init__(coordinator)
        data = subentry.data
        self._id = subentry.subentry_id
        self._symbol: str = data[CONF_SYMBOL]
        self._isin: str | None = data.get(CONF_ISIN)
        self._source: str = data.get(CONF_SOURCE, "")
        self._stored_currency: str | None = data.get(CONF_CURRENCY)
        self._stored_type: str | None = data.get(CONF_TYPE)
        self._attr_unique_id = f"{subentry.subentry_id}_price"
        self._attr_icon = _ICONS.get(data.get(CONF_TYPE) or "", "mdi:chart-line")
        self._attr_device_info = _instrument_device(subentry)

    @property
    def _quote(self) -> Quote | None:
        data = self.coordinator.data
        return data.quotes.get(self._id) if data else None

    @property
    def available(self) -> bool:
        # A quote that was kept through a failed poll is still a quote: it
        # says when it is from.
        return self._quote is not None

    @property
    def native_value(self) -> float | None:
        quote = self._quote
        return None if quote is None else quote.price

    @property
    def native_unit_of_measurement(self) -> str | None:
        quote = self._quote
        # An index stands in points: no currency, whatever its source names.
        if ((quote.type if quote else None) or self._stored_type) == "INDEX":
            return None
        return (quote.currency if quote else None) or self._stored_currency

    @property
    def suggested_display_precision(self) -> int:
        quote = self._quote
        return quote.precision if quote else 2

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        quote = self._quote
        data = self.coordinator.data
        attrs: dict[str, Any] = {
            "symbol": self._symbol,
            # The source the quote is from - the instrument's own, or the
            # one that stood in for it this time.
            "source": (data.sources.get(self._id) if data else None) or self._source,
        }
        if self._isin:
            attrs["isin"] = self._isin
        if quote is None:
            return attrs

        def rounded(value: float | None, digits: int = quote.precision) -> float | None:
            return None if value is None else round(value, digits)

        attrs.update(
            {
                "change": rounded(quote.change),
                "change_percent": rounded(quote.change_percent, 2),
                "previous_close": rounded(quote.previous_close),
                "day_low": rounded(quote.day_low),
                "day_high": rounded(quote.day_high),
                "fifty_two_week_low": rounded(quote.year_low),
                "fifty_two_week_high": rounded(quote.year_high),
                "volume": quote.volume,
                "market_state": quote.market_state,
                "quote_time": quote.quote_time.isoformat() if quote.quote_time else None,
                "exchange": quote.exchange,
                "instrument_type": quote.type,
                "instrument_name": quote.name,
            }
        )
        return attrs


class LastUpdateSensor(CoordinatorEntity[MarketTickerUltraCoordinator], SensorEntity):
    """When a source last answered - and what it said the last time it did not."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MarketTickerUltraCoordinator, entry: MarketTickerUltraConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_update"
        self._attr_device_info = _entry_device(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None

    @property
    def native_value(self) -> datetime | None:
        data = self.coordinator.data
        return data.fetched_at if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "error": data.error if data else None,
            "instruments": len(self.coordinator.instruments),
        }


class _PositionSensor(CoordinatorEntity[MarketTickerUltraCoordinator], SensorEntity):
    """What is held of one instrument, at its current quote."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(
        self, coordinator: MarketTickerUltraCoordinator, subentry: ConfigSubentry, holding: Holding
    ) -> None:
        super().__init__(coordinator)
        self._id = subentry.subentry_id
        self._stored_currency: str | None = subentry.data.get(CONF_CURRENCY)
        self._holding = holding
        self._attr_device_info = _instrument_device(subentry)

    @property
    def _quote(self) -> Quote | None:
        data = self.coordinator.data
        return data.quotes.get(self._id) if data else None

    @property
    def _position(self) -> Position | None:
        quote = self._quote
        return None if quote is None else position_at(self._holding, quote)

    @property
    def available(self) -> bool:
        return self._quote is not None

    @property
    def native_unit_of_measurement(self) -> str | None:
        quote = self._quote
        return (quote.currency if quote else None) or self._stored_currency


class PositionValueSensor(_PositionSensor):
    """What the holding is worth."""

    _attr_translation_key = "position_value"
    _attr_icon = "mdi:briefcase-outline"

    def __init__(
        self, coordinator: MarketTickerUltraCoordinator, subentry: ConfigSubentry, holding: Holding
    ) -> None:
        super().__init__(coordinator, subentry, holding)
        self._attr_unique_id = f"{subentry.subentry_id}_position_value"

    @property
    def native_value(self) -> float | None:
        position = self._position
        return None if position is None else round(position.value, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        position = self._position
        average = self._holding.average_price
        attrs: dict[str, Any] = {
            "quantity": self._holding.quantity,
            "average_price": None if average is None else round(average, 4),
            "cost": round(self._holding.cost, 2),
        }
        if position is not None and position.day_change is not None:
            attrs["day_change"] = round(position.day_change, 2)
        return attrs


class PositionGainSensor(_PositionSensor):
    """What the holding has gained or lost against what it cost."""

    _attr_translation_key = "position_gain"
    _attr_icon = "mdi:chart-line-variant"

    def __init__(
        self,
        coordinator: MarketTickerUltraCoordinator,
        subentry: ConfigSubentry,
        holding: Holding,
        ledger: Ledger,
    ) -> None:
        super().__init__(coordinator, subentry, holding)
        self._ledger = ledger
        self._attr_unique_id = f"{subentry.subentry_id}_position_gain"

    @property
    def native_value(self) -> float | None:
        position = self._position
        return None if position is None else round(position.gain, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        position = self._position
        percent = position.gain_percent if position else None
        return {
            "gain_percent": None if percent is None else round(percent, 2),
            # What sales have realised so far, and what was paid in fees and
            # taxes - beside the gain of what is still held.
            "realized_gain": round(self._ledger.realized, 2),
            "fees": round(self._ledger.fees, 2),
            "taxes": round(self._ledger.taxes, 2),
        }


class _TotalSensor(CoordinatorEntity[MarketTickerUltraCoordinator], SensorEntity):
    """All positions together, in the base currency - of every portfolio,
    or of one group."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: MarketTickerUltraCoordinator,
        entry: MarketTickerUltraConfigEntry,
        group: MarketTickerUltraConfigEntry | None,
    ) -> None:
        """`group`: the portfolio whose sums these are - None for those of
        every portfolio together. `entry` is the settings' entry, on whose
        device both stand."""
        super().__init__(coordinator)
        self._group = group.entry_id if group else None
        # What the unique id hangs on: the group, or the entry for all.
        self._owner = group.entry_id if group else entry.entry_id
        if group:
            # Named after its group: "Portfolio value".
            self._attr_translation_placeholders = {"group": group.title}
        self._attr_device_info = _entry_device(entry)

    @property
    def _totals(self) -> dict[str, Any] | None:
        return self.coordinator.totals(self._group)

    @property
    def available(self) -> bool:
        return self._totals is not None

    @property
    def native_unit_of_measurement(self) -> str:
        return self.coordinator.base_currency


class TotalValueSensor(_TotalSensor):
    """What everything held is worth."""

    _attr_translation_key = "total_value"
    _attr_icon = "mdi:briefcase"

    def __init__(
        self,
        coordinator: MarketTickerUltraCoordinator,
        entry: MarketTickerUltraConfigEntry,
        group: MarketTickerUltraConfigEntry | None,
    ) -> None:
        super().__init__(coordinator, entry, group)
        if group:
            self._attr_translation_key = "group_value"
        self._attr_unique_id = f"{self._owner}_total_value"

    @property
    def native_value(self) -> float | None:
        totals = self._totals
        return None if totals is None else round(totals["value"], 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        totals = self._totals
        if totals is None:
            return {}
        return {
            "cost": round(totals["cost"], 2),
            "day_change": round(totals["day_change"], 2),
            "positions": totals["positions"],
            "not_converted": totals["not_converted"],
            "rates_date": totals["rates_date"],
        }


class TotalGainSensor(_TotalSensor):
    """What everything held has gained or lost."""

    _attr_translation_key = "total_gain"
    _attr_icon = "mdi:chart-line-variant"

    def __init__(
        self,
        coordinator: MarketTickerUltraCoordinator,
        entry: MarketTickerUltraConfigEntry,
        group: MarketTickerUltraConfigEntry | None,
    ) -> None:
        super().__init__(coordinator, entry, group)
        if group:
            self._attr_translation_key = "group_gain"
        self._attr_unique_id = f"{self._owner}_total_gain"

    @property
    def native_value(self) -> float | None:
        totals = self._totals
        return None if totals is None else round(totals["gain"], 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        totals = self._totals
        if totals is None:
            return {}
        percent = totals["gain_percent"]
        return {
            "gain_percent": None if percent is None else round(percent, 2),
            "realized_gain": round(totals["realized"], 2),
            "fees": round(totals["fees"], 2),
            "taxes": round(totals["taxes"], 2),
        }
