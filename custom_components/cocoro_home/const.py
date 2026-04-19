"""Constants for Sharp COCORO HOME integration."""
from __future__ import annotations

DOMAIN = "cocoro_home"
DEFAULT_SCAN_INTERVAL = 60  # seconds

# Sharp cloud endpoints (reverse-engineered from cocorohome_a:2.29.00)
UA             = "cocoroplus/100 (dev; healsio)"
UA_BROWSER     = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"
X_CLIENT       = "CocoroAppAPI/7f7f2f953a7f93d2fd38bf500cef712e"

DEVICE_API     = "https://device.api.aiot.jp.sharp"
HMS_BASE       = "https://hms.cloudlabs.sharp.co.jp"
TOKEN_BASE     = "https://cboard.cloudlabs.sharp.co.jp/cocoroapp"
SSO_BASE       = "https://cocoromembers.jp.sharp"
COCOROPLUSAPP  = "https://cocoroplusapp.jp.sharp"

KEY_CM         = "1mISQwzrO-1Ic24AQI3RqNa6sFd2weWWwyi9Z75qBCs"
KEY_HMS        = "GeeuJKknEYHKW0oyvyv9bMDs3uncXqHUz7VGLdDp2vR"
APPKEY_CM      = "U7jB2YwZnver8WdhRHjRaNoiZ5mWUtLs-Lin6JChUSw"
APPKEY_HMS     = "1mISQwzrO-1Ic24AQI3RqNa6sFd2weWWwyi9Z75qBCs"
APPSECRET_HMS  = "yfNXbDWnLzsjJ0ZSN7OCZmq41wwgktWJONbL5FO%2BJwY%3D"
CM_EXSITEID    = "50100"
HMS_EXSITEID   = "50110"
APP_NAME       = "cocorohome_ha:0.1.0"

# Config flow keys
CONF_EMAIL     = "email"
CONF_PASSWORD  = "password"

# ECHONET Lite 0x03D3 (washer-dryer) property decoding
OP_STATUS = {0x30: "on", 0x31: "off"}
DOOR_LOCK = {0x41: "locked", 0x42: "unlocked"}
WASHER_STATE = {
    0x41: "washing", 0x42: "rinsing", 0x43: "stopped",
    0x44: "drying",  0x45: "spinning",
}
FAULT_STATUS = {0x41: "fault", 0x42: "no_fault"}
