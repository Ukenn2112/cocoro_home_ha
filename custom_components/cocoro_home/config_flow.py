"""Config flow — user enters Sharp Members email + password."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import CocoroAuthError, CocoroHomeAPI
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_EMAIL): str,
    vol.Required(CONF_PASSWORD): str,
})


async def _validate(hass: HomeAssistant, data: dict) -> dict:
    comp_dir = Path(__file__).parent
    cert = comp_dir / "assets" / "cocoro.crt"
    key = comp_dir / "assets" / "cocoro.key"
    if not cert.exists() or not key.exists():
        raise CocoroAuthError(f"mTLS cert not found at {cert}")
    api = CocoroHomeAPI(
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
        cert_path=cert,
        key_path=key,
    )
    await api.async_init()
    try:
        await api.full_login()
        return {
            "title": f"COCORO HOME ({data[CONF_EMAIL]})",
            "member_no": api.state.get("member_no"),
            "devices": api.state.get("devices", []),
        }
    finally:
        await api.async_close()


class CocoroHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for COCORO HOME."""
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _validate(self.hass, user_input)
            except CocoroAuthError as err:
                _LOGGER.error("login failed: %s", err)
                errors["base"] = "auth"
            except Exception:
                _LOGGER.exception("unexpected")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["member_no"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors,
        )
