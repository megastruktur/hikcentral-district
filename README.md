# HikCentral District — Home Assistant Integration

A **Home Assistant custom integration** (HACS-compatible) for HikCentral Pro (Bumblebee API v2.x). Controls door locks, monitors door contact sensors, displays camera streams, and exposes system diagnostics for a HikCentral-based access control system.

## Features

- **Door Locks** — Lock/unlock/open, remain locked/unlocked per door (actions 1–4 via raw HTTP PUT)
- **Door Contact Binary Sensors** — magnet state per door (open/closed)
- **Online Status Binary Sensors** — per-door online/offline monitoring
- **Camera Entities** — RTSP streams via NVR credentials from CameraElements
- **System Diagnostics Sensors** — online controller count, total doors, total cameras
- **Door Action Service** — `hikcentral_district.door_action` with `door_id` + `action` fields
- **Config Flow** — URL, username, password, SSL toggle, scan interval (10–300 s)
- **Options Flow** — multi-select which doors and cameras to expose

## Requirements

- Python 3.11+
- [hikcentral_bumblebee](https://github.com/megastruktur/hikcentral-bumblebee) ≥ 0.1.0
- Home Assistant 2024.11+
- Network access to HikCentral Pro server

## Installation

### Via HACS (recommended)

1. Add this repository as a **custom repository** in HACS:
   - HACS → Integrations → ⋮ → Custom repositories
   - URL: `https://github.com/megastruktur/hikcentral-district`
   - Category: Integration
2. Click **Explore & Add** → search for **HikCentral District** → Install

### Manual

Copy `custom_components/hikcentral_district/` into your Home Assistant's
`custom_components/` folder.

## Configuration

### Config Flow (UI)

| Field | Default | Description |
|---|---|---|
| URL | `https://86.57.210.56:443` | HikCentral Pro base URL |
| Username | — | HikCentral user |
| Password | — | HikCentral password |
| Verify SSL | `false` | Toggle SSL certificate verification |
| Scan Interval | `30` | Polling interval in seconds (10–300) |

### Options Flow

| Field | Description |
|---|---|
| Selected Doors | Multi-select which doors to create entities for |
| Selected Cameras | Multi-select which cameras to create entities for |

## Entity Types

| Platform | Entity | Description |
|---|---|---|
| `lock` | `Door Lock (<name>)` | Lock control per door. State from `DoorStatus.LockState` (0=unlocked, 1=locked, 2+=blocked). Services: lock, unlock, open |
| `binary_sensor` | `<name> Door Contact` | Door contact magnet state (0=closed=off, 1=open=on) |
| `binary_sensor` | `<name> Online` | Door online/offline status |
| `camera` | `<name>` | RTSP camera stream from NVR |
| `sensor` | `HikCentral System` | Online controller count, total doors/cameras |

## Services

### `hikcentral_district.door_action`

Send a control action to a specific door.

```yaml
service: hikcentral_district.door_action
data:
  door_id: "996"   # Door element ID
  action: 1        # 1=unlock/open, 2=lock, 3=remain unlocked, 4=remain locked
```

## Protocol Notes

- Authentication: plain-password XML login → AES key derivation (MD5^100(password + challenge))
- Each request: `AppendInfo` = AES-CBC base64 signature
- Door actions use **raw HTTP PUT** to `/ISAPI/Bumblebee/ACS/DoorElements/{id}/DoorAction?SID=<sid>` (no `MT=` parameter)
- Door status polled via `GET /ISAPI/Bumblebee/ACS/DoorElements/{id}`

## Real Doors

> **Warning:** Real door open/lock commands are sent to live hardware.
> Test with mocks only in development. The integration will open physical doors.

## Credits

- Bumblebee API reverse-engineered from HikCentral Professional OverSea_Pro v2.x
- Python package: [hikcentral-bumblebee](https://github.com/megastruktur/hikcentral-bumblebee)

## License

MIT
