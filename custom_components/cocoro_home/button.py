"""Button platform — manual triggers.

- Refresh course catalog (slow: ~18 HTTP calls, run on demand only).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CocoroHomeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coord: CocoroHomeCoordinator = data["coordinator"]
    api = data["api"]
    ents = []
    for _dev_id, dev_data in (coord.data or {}).items():
        dev = dev_data["device"]
        ents.append(RefreshCatalogButton(coord, api, dev))
    async_add(ents)


class RefreshCatalogButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "コース一覧を更新"
    _attr_icon = "mdi:refresh-circle"

    def __init__(self, coord: CocoroHomeCoordinator, api: Any, device: dict) -> None:
        super().__init__(coord)
        self._api = api
        self._device = device
        self._attr_unique_id = f"cocoro_home_{device['deviceId']}_refresh_catalog"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device["deviceId"]))},
        )

    async def async_press(self) -> None:
        _LOGGER.info("refreshing COCORO WASH catalog…")
        catalog = await self._api.fetch_course_catalog(self._device)
        _LOGGER.info("catalog refreshed: %d courses", len(catalog))
        # Nudge the select entity to re-render its options
        await self.coordinator.async_request_refresh()
