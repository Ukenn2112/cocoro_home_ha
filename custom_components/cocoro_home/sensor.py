"""Sensor platform — exposes washer state as HA sensors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DOOR_LOCK, FAULT_STATUS, OP_STATUS, WASHER_STATE
from .coordinator import CocoroHomeCoordinator


def _hex_to_int(code: str | None) -> int | None:
    if code is None:
        return None
    try:
        return int(code, 16)
    except Exception:
        return None


@dataclass(frozen=True)
class Desc:
    key: str              # HA entity key suffix
    epc: int              # ECHONET Lite property code
    name: str             # display name
    decode: Callable[[str | None], Any]
    unit: str | None = None
    state_class: SensorStateClass | None = None


def _decode_map(m: dict[int, str]) -> Callable[[str | None], str | None]:
    def inner(code: str | None) -> str | None:
        v = _hex_to_int(code)
        return m.get(v) if v is not None else None
    return inner


def _decode_raw(code: str | None) -> str | None:
    return code


def _decode_uint16(code: str | None) -> int | None:
    v = _hex_to_int(code)
    if v is None or v == 0xFFFF:
        return None
    return v


DESCS: list[Desc] = [
    Desc("operation_status", 0x80, "電源状態", _decode_map(OP_STATUS)),
    Desc("door_lock", 0xB0, "ドアロック", _decode_map(DOOR_LOCK)),
    Desc("washer_state", 0xB2, "運転状態", _decode_map(WASHER_STATE)),
    Desc("fault_status", 0x88, "故障状態", _decode_map(FAULT_STATUS)),
    Desc("remaining_minutes", 0xE9, "残り時間", _decode_uint16, "min", SensorStateClass.MEASUREMENT),
    Desc("course_number", 0xE7, "コース番号", _decode_raw),
    Desc("detergent", 0xE5, "洗剤設定", _decode_raw),
    Desc("softener", 0xE6, "柔軟剤設定", _decode_raw),
    Desc("mfg_fault", 0x8B, "メーカー故障コード", _decode_raw),
    Desc("washing_status", 0xD0, "洗濯ステータス", _decode_raw),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add: AddEntitiesCallback
) -> None:
    coord: CocoroHomeCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = []
    for dev_id, dev_data in (coord.data or {}).items():
        dev = dev_data["device"]
        for d in DESCS:
            entities.append(CocoroSensor(coord, dev, d))
        entities.append(CocoroLastUpdated(coord, dev))
    async_add(entities)


class CocoroSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord: CocoroHomeCoordinator, device: dict, desc: Desc) -> None:
        super().__init__(coord)
        self._device = device
        self._desc = desc
        self._attr_unique_id = f"cocoro_home_{device['deviceId']}_{desc.key}"
        self._attr_name = desc.name
        if desc.unit:
            self._attr_native_unit_of_measurement = desc.unit
        if desc.state_class:
            self._attr_state_class = desc.state_class
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device["deviceId"]))},
            manufacturer="SHARP",
            model=device["model"],
            name=f"{device['name']} ({device['place']})",
        )

    @property
    def native_value(self) -> Any:
        data = (self.coordinator.data or {}).get(self._device["deviceId"])
        if not data:
            return None
        code = data["by_epc"].get(self._desc.epc)
        return self._desc.decode(code)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = (self.coordinator.data or {}).get(self._device["deviceId"])
        if not data:
            return {}
        return {"raw_code": data["by_epc"].get(self._desc.epc)}


class CocoroLastUpdated(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "最終更新"

    def __init__(self, coord: CocoroHomeCoordinator, device: dict) -> None:
        super().__init__(coord)
        self._device = device
        self._attr_unique_id = f"cocoro_home_{device['deviceId']}_last_updated"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device["deviceId"]))},
        )

    @property
    def native_value(self) -> Any:
        data = (self.coordinator.data or {}).get(self._device["deviceId"])
        return data.get("updated_at") if data else None
