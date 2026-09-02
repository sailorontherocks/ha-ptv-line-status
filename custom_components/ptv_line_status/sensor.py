"""Sensor platform for PTV Line Status."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PtvConfigEntry
from .const import CONF_DIRECTION_NAME, CONF_ROUTE_NAME, CONF_STATION_NAME
from .coordinator import PtvDataUpdateCoordinator
from .service_alerts import ServiceStatus


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PtvConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the PTV service-status sensor."""
    async_add_entities([PtvServiceStatusSensor(entry.runtime_data.coordinator, entry)])


class PtvServiceStatusSensor(CoordinatorEntity[PtvDataUpdateCoordinator], SensorEntity):
    """Service status for one configured station, route, and direction."""

    _attr_has_entity_name = True
    _attr_name = "Service status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [status.value for status in ServiceStatus]

    def __init__(
        self, coordinator: PtvDataUpdateCoordinator, entry: PtvConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._station_name = entry.data[CONF_STATION_NAME]
        self._route_name = entry.data[CONF_ROUTE_NAME]
        self._direction_name = entry.data[CONF_DIRECTION_NAME]
        suffix = (
            "north_williamstown_city_status"
            if entry.unique_id == "north_williamstown_city"
            else "service_status"
        )
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_name = (
            f"{self._station_name} → {self._direction_name} Service status"
        )

    @property
    def native_value(self) -> str:
        """Return the machine-friendly service state."""
        return self.coordinator.data.status.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return compact operational context."""
        data = self.coordinator.data
        return {
            "station": self._station_name,
            "direction": self._direction_name,
            "route": self._route_name,
            "matching_operational_alert_count": len(data.operational_alerts),
            "matching_alerts": [
                {
                    "id": alert.alert_id,
                    "effect": alert.effect,
                    "header": alert.header,
                    "route_wide": alert.route_wide,
                    "stop_specific": alert.stop_specific,
                }
                for alert in data.operational_alerts
            ],
            "feed_timestamp": data.feed_timestamp,
        }
