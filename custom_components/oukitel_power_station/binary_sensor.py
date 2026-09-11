"""Binary sensor platform for the Oukitel Power Station integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OukitelConfigEntry
from .coordinator import OukitelCoordinator
from .entity import OukitelEntity

_TAG_TOTAL_INPUT_POWER = 4
_ON_BATTERY_DESCRIPTION = EntityDescription(key="on_battery")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OukitelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    async_add_entities([OnBatteryBinarySensor(entry.runtime_data)])


class OnBatteryBinarySensor(OukitelEntity, BinarySensorEntity):
    """`on` when the station is battery-powered (mains lost).

    AC unplug/replug testing showed ``total_input_power == 0`` on battery and
    ``> 0`` on mains. This is only an inference: at full charge with no output
    load, firmware may report zero while mains remains connected, producing a
    false positive. No direct mains-present tag is known. The charging-power
    sensors (tags 11/12) cannot disambiguate this state either.

    No device class is set: `power` would make `off` look like "no power",
    while this entity answers the operational question "is the station
    running from its battery?".
    """

    def __init__(self, coordinator: OukitelCoordinator) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, _ON_BATTERY_DESCRIPTION, tag=_TAG_TOTAL_INPUT_POWER)

    @property
    def is_on(self) -> bool | None:
        """Return True on battery, False on mains, None if input is unknown."""
        raw: Any = self.coordinator.data.get(_TAG_TOTAL_INPUT_POWER)
        if raw is None:
            return None
        try:
            return float(raw) == 0
        except (TypeError, ValueError):
            return None
