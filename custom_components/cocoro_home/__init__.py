"""Sharp COCORO HOME integration — setup hooks."""
from __future__ import annotations

import json
import logging
import voluptuous as vol
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .api import CocoroHomeAPI
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from .coordinator import CocoroHomeCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.BUTTON,
]

SEND_COURSE_SCHEMA = vol.Schema({
    vol.Required("id_code"): cv.string,
    vol.Required("course_type"): cv.string,
})
WRITE_EPC_SCHEMA = vol.Schema({
    vol.Required("epc"): cv.string,
    vol.Required("edt"): cv.string,
})


def _state_path(hass: HomeAssistant, entry: ConfigEntry) -> Path:
    d = Path(hass.config.path(".storage")) / f"{DOMAIN}_{entry.entry_id}.json"
    return d


def _load_state(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    p = _state_path(hass, entry)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _save_state(hass: HomeAssistant, entry: ConfigEntry, state: dict) -> None:
    p = _state_path(hass, entry)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    comp_dir = Path(__file__).parent
    cert = comp_dir / "assets" / "cocoro.crt"
    key = comp_dir / "assets" / "cocoro.key"
    if not cert.exists() or not key.exists():
        _LOGGER.error("mTLS cert missing at %s / %s — place cocoro.crt + cocoro.key in the 'assets' subdir", cert, key)
        return False

    state = _load_state(hass, entry)
    api = CocoroHomeAPI(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        cert_path=cert,
        key_path=key,
        state=state,
    )
    await api.async_init()

    if not api.state.get("bearer"):
        await api.full_login()
        _save_state(hass, entry, api.state)

    coordinator = CocoroHomeCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    # Save state after each successful refresh (bearer may have rotated)
    async def _save_on_update():
        _save_state(hass, entry, api.state)
    coordinator.async_add_listener(lambda: hass.async_create_task(_save_on_update()))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Services
    async def handle_send_course(call: ServiceCall) -> None:
        # Targets first device by default; users with multiple washers
        # should pick via device_id in a future revision.
        if not api.state.get("devices"):
            return
        dev = api.state["devices"][0]
        res = await api.send_course(dev, call.data["id_code"], call.data["course_type"])
        _LOGGER.info("send_course → %s", res)

    async def handle_write_epc(call: ServiceCall) -> None:
        if not api.state.get("devices"):
            return
        dev = api.state["devices"][0]
        res = await api.write_epc(dev, [{"epc": call.data["epc"], "edt": call.data["edt"]}])
        _LOGGER.info("write_epc → %s", res)

    async def handle_refresh_catalog(call: ServiceCall) -> None:
        if not api.state.get("devices"):
            return
        dev = api.state["devices"][0]
        catalog = await api.fetch_course_catalog(dev)
        _save_state(hass, entry, api.state)
        await coordinator.async_request_refresh()
        _LOGGER.info("refresh_catalog → %d courses", len(catalog))

    hass.services.async_register(DOMAIN, "send_course", handle_send_course, schema=SEND_COURSE_SCHEMA)
    hass.services.async_register(DOMAIN, "write_epc", handle_write_epc, schema=WRITE_EPC_SCHEMA)
    hass.services.async_register(DOMAIN, "refresh_catalog", handle_refresh_catalog)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["api"].async_close()
    return ok
