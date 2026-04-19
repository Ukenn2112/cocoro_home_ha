# Sharp COCORO HOME — Home Assistant custom component

Brings Sharp drum washer-dryer (tested on ES-8XS1) status and limited control
into Home Assistant. Communicates directly with Sharp's cloud using the same
endpoints as the official app (reverse-engineered from COCORO HOME v2.29.00).

## What this gives you

### Sensors (auto-polled every 60s)

- `sensor.<washer>_operation_status` — `on` / `off`
- `sensor.<washer>_washer_state` — `washing` / `rinsing` / `stopped` / `drying` / `spinning`
- `sensor.<washer>_door_lock` — `locked` / `unlocked`
- `sensor.<washer>_fault_status` — `fault` / `no_fault`
- `sensor.<washer>_mfg_fault_code` — manufacturer-specific fault code (3-char)
- `sensor.<washer>_remaining` — remaining minutes (int)
- `sensor.<washer>_course` / `_detergent` / `_softener` / `_washing_status` — raw hex
- `sensor.<washer>_last_updated` — ISO timestamp Sharp cloud last received update
- Binary sensors: `running`, `has_fault`, `door_locked`, `power`

### Services

- `cocoro_home.send_course` — push a download course to the washer's slot.
  User must then physically select "ダウンロードコース" on the panel to run.
- `cocoro_home.write_epc` — raw ECHONET write (mostly rejected by device for
  safety-regulated properties like 0x80 operation_status).

## What this does NOT give you

- **Remote start/stop**. Japanese 遠隔操作 ガイドライン prohibits remote
  on/off for washers. Both Sharp's cloud and the device firmware refuse
  writes to EPC 0x80. There is no way around this from software alone.

## Install

1. Copy the `custom_components/cocoro_home` folder into your HA config directory.
2. Restart HA.
3. Settings → Devices & Services → Add Integration → search "Sharp COCORO HOME".
4. Enter your COCORO MEMBERS email + password.
5. After ~30s of login flow, your washer will appear as a device with the
   sensors listed above.

## Requirements

- `aiohttp` (already bundled with HA)
- Washer paired to COCORO MEMBERS account and online

## The `assets/` cert bundle

The component ships with `cocoro.crt` + `cocoro.key` — the mTLS client
certificate extracted from the official APK's `CocoroHomeClient.pfx`. Required
for the initial OAuth bootstrap against `device.api.aiot.jp.sharp`. Same for
every install. Keep your HA config directory private.

## Usage example — notify when wash finishes

```yaml
automation:
  - alias: Washer finished
    trigger:
      - platform: state
        entity_id: binary_sensor.sentakuki_running
        from: "on"
        to: "off"
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: "洗濯が終わりました"
```

## Usage — push a course (tower sterilization)

```yaml
service: cocoro_home.send_course
data:
  id_code: "0x0003D4F1"
  course_type: "0x10"
```

Course idCodes you can find by watching the network tab on
<https://cocoroplusapp.jp.sharp/wash/navi> — each course's URL contains
`idCode=0x...`.

## Troubleshooting

- **"mTLS cert missing"**: ensure `custom_components/cocoro_home/assets/cocoro.crt`
  and `.key` exist.
- **401/403 after 1h**: the integration auto-refreshes Bearer when expired. If
  it doesn't, remove the integration and re-add.
- **No washer appears**: make sure the washer is registered under your
  COCORO MEMBERS account (check the official app first).

## License / disclaimer

For personal interop/research on your own device. Sharp's ToS prohibits
redistribution of the client cert / cloud API use outside the official app.
