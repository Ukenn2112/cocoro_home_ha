"""DataUpdateCoordinator — polls washer status every N seconds."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CocoroHomeAPI
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class CocoroHomeCoordinator(DataUpdateCoordinator):
    """Single coordinator per config entry; fetches status for all devices."""

    def __init__(self, hass: HomeAssistant, api: CocoroHomeAPI) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.api = api

    async def _async_update_data(self) -> dict:
        """Fetch status for every known device; return {deviceId: {epc->edt map, raw}}."""
        out: dict[int, dict] = {}
        for dev in self.api.state.get("devices", []):
            try:
                raw = await self.api.get_device_status(dev)
                ds = raw["deviceStatus"]
                by_epc = {}
                for s in ds.get("status", []):
                    epc = int(s["statusCode"], 16)
                    val = s.get("valueSingle") or s.get("valueBinary") or s.get("valueRange") or {}
                    by_epc[epc] = val.get("code")
                out[dev["deviceId"]] = {
                    "updated_at": ds.get("propertyUpdatedAt"),
                    "by_epc": by_epc,
                    "device": dev,
                }
            except Exception as err:
                _LOGGER.exception("status fetch failed for %s: %s", dev.get("name"), err)
                raise UpdateFailed(str(err)) from err
        return out
