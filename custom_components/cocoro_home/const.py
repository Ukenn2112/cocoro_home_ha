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

# ECHONET Lite 0x03D3 (洗濯乾燥機) プロパティ日本語表示
OP_STATUS = {0x30: "オン", 0x31: "オフ"}
DOOR_LOCK = {0x41: "ロック中", 0x42: "解錠"}
WASHER_STATE = {
    0x41: "洗い",   0x42: "すすぎ", 0x43: "停止",
    0x44: "乾燥",   0x45: "脱水",
}
FAULT_STATUS = {0x41: "異常あり", 0x42: "正常"}
