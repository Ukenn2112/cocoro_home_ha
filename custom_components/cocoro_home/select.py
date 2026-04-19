"""Select platform — dropdown of downloadable COCORO WASH courses.

Picking an option triggers send_course_by_name automatically. The washer will
have the course in its "ダウンロードコース" slot afterward; user must still
select it on the panel and press start (Japan regulation — no remote start).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CocoroHomeCoordinator

_LOGGER = logging.getLogger(__name__)

PLACEHOLDER = "— コース一覧を更新してください —"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coord: CocoroHomeCoordinator = data["coordinator"]
    api = data["api"]
    entities = []
    for _dev_id, dev_data in (coord.data or {}).items():
        dev = dev_data["device"]
        entities.append(DownloadCourseSelect(coord, api, dev))
    async_add(entities)


class DownloadCourseSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "ダウンロードコース"
    _attr_icon = "mdi:playlist-check"

    def __init__(self, coord: CocoroHomeCoordinator, api: Any, device: dict) -> None:
        super().__init__(coord)
        self._api = api
        self._device = device
        self._attr_unique_id = f"cocoro_home_{device['deviceId']}_download_course"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device["deviceId"]))},
        )
        self._pending: str | None = None

    @property
    def options(self) -> list[str]:
        catalog = self._api.state.get("course_catalog") or []
        if not catalog:
            return [PLACEHOLDER]
        return [c["name"] for c in catalog]

    @property
    def current_option(self) -> str | None:
        return self._pending or (self.options[0] if self.options else None)

    async def async_select_option(self, option: str) -> None:
        if option == PLACEHOLDER:
            return
        _LOGGER.info("sending course to washer: %s", option)
        self._pending = option
        self.async_write_ha_state()
        res = await self._api.send_course_by_name(self._device, option)
        _LOGGER.info("send_course response: %s", res)
