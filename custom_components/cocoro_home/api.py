"""Sharp COCORO HOME API client — async, runs inside Home Assistant."""
from __future__ import annotations

import datetime as dt
import logging
import re
import ssl
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

import aiohttp

from .const import (
    APPKEY_CM, APPKEY_HMS, APPSECRET_HMS, APP_NAME,
    CM_EXSITEID, COCOROPLUSAPP, DEVICE_API, HMS_BASE, HMS_EXSITEID,
    KEY_CM, KEY_HMS, SSO_BASE, TOKEN_BASE, UA, UA_BROWSER, X_CLIENT,
)

_LOGGER = logging.getLogger(__name__)


class CocoroAuthError(Exception):
    """Raised when authentication fails irrecoverably."""


class CocoroHomeAPI:
    """Stateful client that does full OAuth dance then polls/controls devices."""

    def __init__(
        self,
        *,
        email: str,
        password: str,
        cert_path: Path,
        key_path: Path,
        state: dict | None = None,
    ) -> None:
        self._email = email
        self._password = password
        self._cert_path = cert_path
        self._key_path = key_path
        self.state: dict[str, Any] = state or {"uniq_id": str(uuid.uuid4())}
        self._session: aiohttp.ClientSession | None = None
        self._mtls_ssl: ssl.SSLContext | None = None

    # ── Setup/teardown ────────────────────────────────────────────────────
    async def async_init(self) -> None:
        self._mtls_ssl = ssl.create_default_context()
        self._mtls_ssl.load_cert_chain(str(self._cert_path), str(self._key_path))
        self._session = aiohttp.ClientSession()

    async def async_close(self) -> None:
        if self._session:
            await self._session.close()

    # ── Auth flow ─────────────────────────────────────────────────────────
    async def _sso_login(self, browser_sess: aiohttp.ClientSession) -> None:
        async with browser_sess.get(
            f"{SSO_BASE}/sic-front/member/A050101ViewAction.do",
            headers={"User-Agent": UA_BROWSER},
        ) as r:
            r.raise_for_status()
            html = await r.text()
        m = re.search(
            r'org\.apache\.struts\.taglib\.html\.TOKEN[^"]*"\s*value="([a-f0-9]+)"', html
        )
        if not m:
            raise CocoroAuthError("SSO login form: Struts TOKEN not found")
        token = m.group(1)
        async with browser_sess.post(
            f"{SSO_BASE}/sic-front/member/A050101LoginAction.do",
            headers={"User-Agent": UA_BROWSER},
            data={
                "memberId": self._email,
                "password": self._password,
                "captchaText": "1",
                "autoLogin": "on",
                "exsiteId": "200000",
                "org.apache.struts.taglib.html.TOKEN": token,
            },
            allow_redirects=False,
        ) as r:
            if r.status != 302:
                body = await r.text()
                raise CocoroAuthError(f"SSO login failed {r.status} {body[:200]}")

    async def _oauth_flow(
        self,
        browser_sess: aiohttp.ClientSession,
        *,
        kind: str,
        consumer_key: str,
        app_key: str,
        exsiteid: str,
        callback_host: str,
        extra: dict | None = None,
    ) -> tuple[str, str]:
        """CM/HMS 4-step OAuth; returns (cloudKey_url, memberNo)."""
        # Step 1 — requires mTLS
        async with self._session.get(
            f"{DEVICE_API}/v1/devices/dmf/login",
            headers={"User-Agent": UA, "X-SIC-API-CONSUMERKEY": consumer_key},
            ssl=self._mtls_ssl,
        ) as r:
            r.raise_for_status()
            req_token = (await r.json(content_type=None))["requestToken"]

        # Step 2 — follow SSO redirects to extract tempAccToken from cocorohome:// scheme
        url = (
            f"{SSO_BASE}/sic-front/sso/rLoginAuthAction.do"
            f"?requestToken={req_token}&exsiteid={exsiteid}"
            f"&callbackUri=cocorohome://{callback_host}"
        )
        loc = None
        current = url
        chain = []
        for _ in range(15):
            async with browser_sess.get(
                current,
                headers={"User-Agent": UA_BROWSER},
                allow_redirects=False,
            ) as r:
                chain.append(f"{r.status} {current[:80]}")
                if r.status not in (301, 302, 303):
                    _LOGGER.debug("oauth chain stopped at non-redirect: status=%s url=%s", r.status, current)
                    break
                loc = r.headers.get("Location", "")
                if loc.startswith("cocorohome://"):
                    break
                current = loc if loc.startswith("http") else f"{SSO_BASE}{loc}"
        if not loc or not loc.startswith("cocorohome://"):
            _LOGGER.error("oauth chain trace:\n  %s", "\n  ".join(chain))
            raise CocoroAuthError(f"SSO chain didn't reach cocorohome:// (last={loc})")
        temp_acc = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)["tempAccToken"][0]

        # Step 3 — mTLS
        async with self._session.post(
            f"{DEVICE_API}/v1/devices/dmf/token",
            headers={
                "User-Agent": UA,
                "X-SIC-API-CONSUMERKEY": consumer_key,
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"requestToken": req_token, "tempAccToken": temp_acc},
            ssl=self._mtls_ssl,
        ) as r:
            r.raise_for_status()
            j = await r.json(content_type=None)
            temp_access, member_no = j["tempAccessToken"], j["memberNo"]

        # Step 4 — mTLS
        payload = {"tempAccessToken": temp_access, "uniq_id": self.state["uniq_id"], "appKey": app_key}
        if extra:
            payload.update(extra)
        async with self._session.post(
            f"{DEVICE_API}/v1/devices/dmf/cloudkey",
            headers={
                "User-Agent": UA,
                "X-SIC-API-CONSUMERKEY": consumer_key,
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
            ssl=self._mtls_ssl,
        ) as r:
            body_json: dict = {}
            try:
                body_json = await r.json(content_type=None)
            except Exception:
                pass
            # 200 = fresh register; 400 "Duplicate uniq_id" also returns cloudKey → treat as OK.
            cloud_key_url = body_json.get("cloudKey")
            if not cloud_key_url:
                raise CocoroAuthError(f"[{kind}] cloudkey {r.status} {body_json}")
            if r.status not in (200, 400):
                raise CocoroAuthError(f"[{kind}] cloudkey {r.status} {body_json}")
            if r.status == 400:
                _LOGGER.debug("[%s] cloudkey: Duplicate uniq_id (reusing existing)", kind)
        return cloud_key_url, member_no

    async def _exchange_bearer(self, hms_cloudkey: str) -> dict:
        async with self._session.post(
            f"{TOKEN_BASE}/api/v1/token",
            headers={
                "User-Agent": UA,
                "X-Client-Id": X_CLIENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"cloudkey": hms_cloudkey},
            ssl=self._mtls_ssl,
        ) as r:
            r.raise_for_status()
            return await r.json(content_type=None)

    async def _hms_login(self, bearer: str, hms_cloudkey: str) -> str:
        async with self._session.post(
            f"{HMS_BASE}/hems/pfApi/ta/setting/login?appSecret={APPSECRET_HMS}",
            headers={
                "User-Agent": UA,
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json",
            },
            json={"terminalAppId": hms_cloudkey},
            ssl=self._mtls_ssl,
        ) as r:
            r.raise_for_status()
            for c in r.headers.getall("Set-Cookie", []):
                m = re.search(r"JSESSIONID=([^;]+)", c)
                if m:
                    return m.group(1)
        raise CocoroAuthError("HMS login: no JSESSIONID")

    async def _cocoroplusapp_session(self, browser_sess: aiohttp.ClientSession) -> str:
        """Trigger COCORO WASH login → Keycloak OIDC → Sharp SSO → callback → jsessionid.

        Flow (emulating SPA behavior):
          1. GET  /v1/cocoro-wash/login      → 200 JSON {"redirectUrl":"...keycloak..."}
          2. GET  that keycloak URL          → 303 broker/cocomem/login
          3. GET  broker URL                 → 302 rLoginAuthAction.do?exsiteid=50130
          4. GET  rLoginAuthAction.do        → 200 ExLoginViewAction.do (final) → mints jsessionid
        Relies on cocoromembers.jp.sharp SSO cookies being present in browser_sess.
        """
        async with browser_sess.get(
            f"{COCOROPLUSAPP}/v1/cocoro-wash/login",
            headers={"User-Agent": UA_BROWSER},
        ) as r:
            resp = await r.json(content_type=None)
        redirect_url = resp.get("redirectUrl") or resp.get("redirect_url")
        if not redirect_url:
            raise CocoroAuthError(f"/v1/cocoro-wash/login no redirectUrl: {resp}")
        # Follow the OIDC chain; aiohttp handles all redirects.
        async with browser_sess.get(
            redirect_url,
            headers={"User-Agent": UA_BROWSER},
            allow_redirects=True,
            max_redirects=20,
        ) as r:
            await r.read()
        for c in browser_sess.cookie_jar:
            name = getattr(c, "key", None)
            domain = (c["domain"] if "domain" in c else "")
            if name == "jsessionid" and "cocoroplusapp" in (domain or ""):
                return c.value
        for c in browser_sess.cookie_jar:
            if getattr(c, "key", None) == "jsessionid":
                return c.value
        raise CocoroAuthError("cocoro-wash: no jsessionid after OIDC chain")

    async def _list_devices(self, bearer: str, cm_cloudkey: str) -> list[dict]:
        async with self._session.get(
            f"{DEVICE_API}/v1/cocoro-home/devices",
            headers={
                "User-Agent": UA,
                "Authorization": f"Bearer {bearer}",
                "X-Cloud-Key": cm_cloudkey,
            },
            ssl=self._mtls_ssl,
        ) as r:
            r.raise_for_status()
            raw = await r.json(content_type=None)
        out = []
        for group, items in raw.items():
            if not isinstance(items, list):
                continue
            for it in items:
                try:
                    out.append({
                        "boxId":       it["boxId"],
                        "deviceId":    it["deviceId"],
                        "deviceToken": it["bffToken"],
                        "echonetNode": it["uniqueId"],
                        "echonetObject": it["objectId"].removeprefix("0x"),
                        "model":       it["model"],
                        "type":        it["type"],
                        "place":       it.get("place", group),
                        "name":        it.get("name", it.get("model", "washer")),
                    })
                except KeyError as err:
                    _LOGGER.warning("list_devices: skip entry missing %s: %s", err, list(it.keys()))
        return out

    async def full_login(self) -> None:
        """Run all 7 steps; populate self.state."""
        _LOGGER.info("COCORO HOME full login starting for %s", self._email)
        browser_jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=browser_jar) as browser:
            await self._sso_login(browser)
            cm_cloudkey, member_no = await self._oauth_flow(
                browser, kind="CM", consumer_key=KEY_CM, app_key=APPKEY_CM,
                exsiteid=CM_EXSITEID, callback_host="cm-login",
            )
            hms_cloudkey, _ = await self._oauth_flow(
                browser, kind="HMS", consumer_key=KEY_HMS, app_key=APPKEY_HMS,
                exsiteid=HMS_EXSITEID, callback_host="hms-login",
                extra={"name": "HA", "os": "Android", "osVersion": "13", "appName": APP_NAME},
            )
            token = await self._exchange_bearer(hms_cloudkey)
            bearer = token["access_token"]
            expires_in = int(token.get("expire_in", 3600))
            hms_jsess = await self._hms_login(bearer, hms_cloudkey)
            wash_jsess = await self._cocoroplusapp_session(browser)
            devices = await self._list_devices(bearer, cm_cloudkey)

        self.state.update({
            "email": self._email,
            "member_no": member_no,
            "cm_cloudkey": cm_cloudkey,
            "hms_cloudkey": hms_cloudkey,
            "bearer": bearer,
            "bearer_expires_at": (dt.datetime.now() + dt.timedelta(seconds=expires_in - 60)).isoformat(),
            "hms_jsessionid": hms_jsess,
            "wash_jsessionid": wash_jsess,
            "devices": devices,
        })
        _LOGGER.info("COCORO HOME login done; %d device(s)", len(devices))

    # ── Tiered refresh ────────────────────────────────────────────────────
    # Cheapest → most expensive:
    #   Tier 1  _refresh_bearer()         1 HTTPS call  ~300ms
    #   Tier 2  _refresh_hms_session()    1 HTTPS call
    #   Tier 3  full_login()              ~10 HTTPS calls ~3-5s
    #
    # Normal hourly rotation uses T1+T2. T3 only on cookie-jar expiry
    # (cocoromembers SSO dead) or hms_cloudkey revoked.

    def _bearer_is_fresh(self) -> bool:
        exp = self.state.get("bearer_expires_at")
        if not exp:
            return False
        try:
            return dt.datetime.now() < dt.datetime.fromisoformat(exp)
        except Exception:
            return False

    async def _refresh_bearer(self) -> None:
        """Tier 1: mint new Bearer from stored hms_cloudkey (1 HTTPS call)."""
        if not self.state.get("hms_cloudkey"):
            raise CocoroAuthError("no cached hms_cloudkey for fast refresh")
        _LOGGER.debug("T1: refresh bearer via stored hms_cloudkey")
        tok = await self._exchange_bearer(self.state["hms_cloudkey"])
        self.state["bearer"] = tok["access_token"]
        exp_in = int(tok.get("expire_in", 3600))
        self.state["bearer_expires_at"] = (
            dt.datetime.now() + dt.timedelta(seconds=exp_in - 60)
        ).isoformat()

    async def _refresh_hms_session(self) -> None:
        """Tier 2: rebind HMS JSESSIONID using current Bearer + stored cloudkey."""
        if not (self.state.get("bearer") and self.state.get("hms_cloudkey")):
            raise CocoroAuthError("cannot refresh HMS session without bearer+cloudkey")
        _LOGGER.debug("T2: refresh HMS JSESSIONID")
        self.state["hms_jsessionid"] = await self._hms_login(
            self.state["bearer"], self.state["hms_cloudkey"]
        )

    async def ensure_authenticated(self) -> None:
        """Make sure Bearer is fresh. Use cheapest refresh tier that works."""
        if self.state.get("bearer") and self._bearer_is_fresh():
            return
        if not self.state.get("bearer"):
            _LOGGER.info("no Bearer cached — full login")
            await self.full_login()
            return
        # Try fast refresh first
        try:
            await self._refresh_bearer()
            await self._refresh_hms_session()
            _LOGGER.info("fast refresh OK (no SSO)")
            return
        except Exception as err:
            _LOGGER.warning("fast refresh failed (%s); falling back to full login", err)
        await self.full_login()

    # ── Read/write operations with per-call retry ─────────────────────────
    async def get_device_status(self, device: dict) -> dict:
        """GET hms/pfApi/ta/control/deviceStatus — returns raw EPC map."""
        await self.ensure_authenticated()
        url = (
            f"{HMS_BASE}/hems/pfApi/ta/control/deviceStatus"
            f"?appSecret={APPSECRET_HMS}"
            f"&boxId={urllib.parse.quote(device['boxId'], safe='')}"
            f"&echonetNode={device['echonetNode']}"
            f"&echonetObject={device['echonetObject']}"
            f"&deviceId={device['deviceId']}"
        )
        for attempt in ("first", "after_hms_refresh", "after_full_login"):
            async with self._session.get(
                url,
                headers={
                    "User-Agent": UA,
                    "Authorization": f"Bearer {self.state['bearer']}",
                    "Cookie": f"JSESSIONID={self.state['hms_jsessionid']}",
                },
                ssl=self._mtls_ssl,
            ) as r:
                if r.status in (401, 403):
                    if attempt == "first":
                        _LOGGER.info("HMS 401/403 — refreshing HMS session")
                        try:
                            await self._refresh_hms_session()
                            continue
                        except Exception:
                            pass
                    if attempt == "after_hms_refresh":
                        _LOGGER.info("still 401/403 — full login")
                        await self.full_login()
                        continue
                    r.raise_for_status()
                r.raise_for_status()
                return await r.json(content_type=None)

    async def write_epc(self, device: dict, data: list[dict]) -> dict:
        """POST /v1/cocoro-wash/sync/epc — generic ECHONET write."""
        await self.ensure_authenticated()
        await self._ensure_wash_session()
        for attempt in ("first", "after_full_login"):
            async with self._session.post(
                f"{COCOROPLUSAPP}/v1/cocoro-wash/sync/epc",
                headers={
                    "User-Agent": UA_BROWSER,
                    "Content-Type": "application/json",
                    "Cookie": f"jsessionid={self.state['wash_jsessionid']}",
                },
                json={
                    "deviceToken": device["deviceToken"],
                    "event_key": "echonet_control",
                    "data": data,
                },
            ) as r:
                if r.status in (401, 403) and attempt == "first":
                    _LOGGER.info("wash 401/403 — full login (no cheap wash refresh)")
                    await self.full_login()
                    continue
                return {"status": r.status, "body": await r.text()}

    async def send_course(self, device: dict, id_code: str, course_type: str) -> dict:
        """Look up course meta + push full EPC bundle to washer."""
        await self.ensure_authenticated()
        await self._ensure_wash_session()
        for attempt in ("first", "after_full_login"):
            async with self._session.post(
                f"{COCOROPLUSAPP}/v1/cocoro-wash/sensors",
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": UA_BROWSER,
                    "Cookie": f"jsessionid={self.state['wash_jsessionid']}",
                },
                json={
                    "deviceToken": device["deviceToken"],
                    "properties": [{
                        "apg": "0x02",
                        "apc": ["0x00","0x01","0x02","0x04","0x05","0x06","0x07",
                                "0x08","0x09","0x0A","0x0B","0x0C","0x0D","0x0E"],
                        "code": {"0x00": {"0x00": course_type},
                                 "0x01": {"0x00": id_code}},
                    }],
                },
            ) as r:
                if r.status in (401, 403) and attempt == "first":
                    await self.full_login()
                    continue
                r.raise_for_status()
                j = await r.json(content_type=None)
                break
        course = j["sensors_post_021"]["body"]["data"][0]
        settings = course["0x08"][0]["0x10"]
        data = [
            {"epc": "0xD0", "edt": settings["0x00"]},
            {"epc": "0xF1", "edt": f"0x7200{settings['0x01'][2:]}00000000"},
            {"epc": "0xE5", "edt": settings["0x03"]},
            {"epc": "0xE6", "edt": settings["0x04"]},
            {"epc": "0xE7", "edt": settings["0x05"]},
            {"epc": "0xE8", "edt": settings["0x06"]},
            {"epc": "0xE9", "edt": settings["0x07"]},
        ]
        return await self.write_epc(device, data)

    # ── Course catalog enumeration ────────────────────────────────────────
    # Sharp groups courses by item category (品类) × operation type.
    # Observed via COCORO WASH web UI:
    #   categories 0x11..0x18 correspond to:
    #     0x11 上着/トップス  0x12 下着/インナー  0x13 パンツ/ボトムス
    #     0x14 季節モノ       0x15 赤ちゃん       0x16 ペット/ぬいぐるみ
    #     0x17 カバー/大物洗い  0x19 タオル
    #   types:
    #     0x00 = wash-only       0x10 = wash-to-dry     0x20 = dry-only
    CATALOG_CATEGORIES = (
        "0x11", "0x12", "0x13", "0x14", "0x15", "0x16", "0x17", "0x18", "0x19"
    )
    CATALOG_TYPES = ("0x00", "0x10", "0x20")

    async def _ensure_wash_session(self) -> None:
        """Make sure we have a wash_jsessionid — full_login if missing."""
        if not self.state.get("wash_jsessionid"):
            _LOGGER.info("no wash_jsessionid — full login")
            await self.full_login()

    async def _list_courses_in_category(
        self, device: dict, category_hex: str
    ) -> list[dict]:
        """POST /sensors with apg=0x02 + category filter → list of courses in that category."""
        await self._ensure_wash_session()
        for attempt in ("first", "after_full_login"):
            async with self._session.post(
                f"{COCOROPLUSAPP}/v1/cocoro-wash/sensors",
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": UA_BROWSER,
                    "Cookie": f"jsessionid={self.state['wash_jsessionid']}",
                },
                json={
                    "deviceToken": device["deviceToken"],
                    "properties": [{
                        "apg": "0x02",
                        "apc": ["0x01", "0x02", "0x05", "0x06", "0x09", "0x0A"],
                        "code": {"0x30": {"0x00": category_hex}},
                    }],
                },
            ) as r:
                if r.status in (401, 403) and attempt == "first":
                    await self.full_login()
                    continue
                if r.status != 200:
                    return []
                j = await r.json(content_type=None)
                break
        body = j.get("sensors_post_021", {}).get("body", {})
        return body.get("data", []) or []

    async def fetch_course_catalog(self, device: dict) -> list[dict]:
        """Enumerate all available download courses for this device.

        Returns list of {id_code, name, category, type, summary} dicts.
        Slow (18 requests); call explicitly via service, not on every poll.
        """
        _LOGGER.info("fetching COCORO WASH course catalog…")
        seen: dict[str, dict] = {}  # dedupe by id_code
        for cat in self.CATALOG_CATEGORIES:
            raws = await self._list_courses_in_category(device, cat)
            for c in raws:
                id_code = c.get("0x01")
                if not id_code or id_code in seen:
                    continue
                seen[id_code] = {
                    "id_code": id_code,
                    "name": c.get("0x02", id_code),
                    "category": cat,
                    "type": c.get("0x09", "0x00"),  # per-course type flag
                    "summary": c.get("0x0A", ""),
                }
        catalog = list(seen.values())
        _LOGGER.info("course catalog: %d unique courses", len(catalog))
        self.state["course_catalog"] = catalog
        self.state["course_catalog_fetched_at"] = dt.datetime.now().isoformat()
        return catalog

    async def send_course_by_name(self, device: dict, name_or_id: str) -> dict:
        """Look up a course in cached catalog by name or id_code, then send."""
        catalog = self.state.get("course_catalog") or []
        match = next(
            (c for c in catalog
             if c["name"] == name_or_id or c["id_code"] == name_or_id),
            None,
        )
        if not match:
            raise CocoroAuthError(f"course not in catalog: {name_or_id}")
        # Default operation type: wash-to-dry if available else wash-only
        course_type = "0x10"
        return await self.send_course(device, match["id_code"], course_type)
