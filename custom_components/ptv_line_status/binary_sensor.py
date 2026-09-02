"""Binary sensor platform for PTV Line Status."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PtvConfigEntry
from .const import CONF_DIRECTION_NAME, CONF_STATION_NAME
from .coordinator import PtvDataUpdateCoordinator
from .service_alerts import ServiceStatus


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PtvConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the PTV service-issue binary sensor."""
    async_add_entities(
        [PtvServiceIssueBinarySensor(entry.runtime_data.coordinator, entry)]
    )


class PtvServiceIssueBinarySensor(
    CoordinatorEntity[PtvDataUpdateCoordinator], BinarySensorEntity
):
    """Whether a configured Metro service has an operational issue."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self, coordinator: PtvDataUpdateCoordinator, entry: PtvConfigEntry
    ) -> None:
        super().__init__(coordinator)
        station_name = entry.data[CONF_STATION_NAME]
        direction_name = entry.data[CONF_DIRECTION_NAME]
        self._attr_unique_id = f"{entry.entry_id}_service_issue"
        self._attr_name = f"{station_name} → {direction_name} Service issue"

    @property
    def is_on(self) -> bool:
        """Return whether the coordinator reports a non-normal status."""
        return self.coordinator.data.status is not ServiceStatus.NORMAL
