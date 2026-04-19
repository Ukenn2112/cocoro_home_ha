"""Binary sensors — running / has_fault / door_locked."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CocoroHomeCoordinator


def _hex_int(c: str | None) -> int | None:
    try:
        return int(c, 16) if c else None
    except Exception:
        return None


@dataclass(frozen=True)
class BDesc:
    key: str
    name: str
    eval_: Callable[[dict[int, str | None]], bool | None]
    device_class: BinarySensorDeviceClass | None = None


DESCS: list[BDesc] = [
    BDesc("running", "Running",
          lambda by: (_hex_int(by.get(0xB2)) or 0x43) != 0x43,
          BinarySensorDeviceClass.RUNNING),
    BDesc("has_fault", "Has fault",
          lambda by: (_hex_int(by.get(0x88)) or 0x42) != 0x42,
          BinarySensorDeviceClass.PROBLEM),
    BDesc("door_locked", "Door locked",
          lambda by: (_hex_int(by.get(0xB0)) or 0x42) == 0x41,
          BinarySensorDeviceClass.LOCK),
    BDesc("power", "Powered on",
          lambda by: (_hex_int(by.get(0x80)) or 0x31) == 0x30,
          BinarySensorDeviceClass.POWER),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add: AddEntitiesCallback
) -> None:
    coord: CocoroHomeCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[BinarySensorEntity] = []
    for dev_id, dev_data in (coord.data or {}).items():
        dev = dev_data["device"]
        for d in DESCS:
            entities.append(CocoroBinary(coord, dev, d))
    async_add(entities)


class CocoroBinary(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord: CocoroHomeCoordinator, device: dict, desc: BDesc) -> None:
        super().__init__(coord)
        self._device = device
        self._desc = desc
        self._attr_unique_id = f"cocoro_home_{device['deviceId']}_{desc.key}"
        self._attr_name = desc.name
        if desc.device_class:
            self._attr_device_class = desc.device_class
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device["deviceId"]))},
        )

    @property
    def is_on(self) -> bool | None:
        data = (self.coordinator.data or {}).get(self._device["deviceId"])
        if not data:
            return None
        try:
            return self._desc.eval_(data["by_epc"])
        except Exception:
            return None
