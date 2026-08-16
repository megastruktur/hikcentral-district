# HikCentral District — Home Assistant Integration

A **Home Assistant custom integration** (HACS-compatible) for HikCentral Pro (Bumblebee API v2.x). Controls door locks, monitors door contact sensors, displays camera streams, and exposes system diagnostics for a HikCentral-based access control system.

## Features

- **Door Locks** — Lock/unlock/open, remain locked/unlocked per door (actions 1–4 via raw HTTP PUT)
- **Door Contact Binary Sensors** — magnet state per door (open/closed)
- **Online Status Binary Sensors** — per-door online/offline monitoring
- **Camera Entities** — live snapshots via the Authenty protocol (real current frame from the VTDU, no direct camera access needed); HikCentral thumbnail as fallback
- **Live Video (optional)** — RTSP bridge script (`rtsp_bridge.py`) for the bundled go2rtc, giving on-demand live streams in Lovelace
- **System Diagnostics Sensors** — online controller count, total doors, total cameras
- **Door Action Service** — `hikcentral_district.door_action` with `door_id` + `action` fields
- **Config Flow** — URL, username, password, SSL toggle, scan interval (10–300 s)
- **Options Flow** — multi-select which doors and cameras to expose

## Requirements

- Python 3.11+
- [hikcentral_bumblebee](https://github.com/megastruktur/hikcentral-bumblebee) ≥ 0.3.0
- `ffmpeg` in the Home Assistant container (stock images include it) — for live snapshots
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

## Door Discovery

On every poll cycle the coordinator discovers doors in two ways and merges them
(deduplicated by door ID):

1. **List discovery** — `POST /ISAPI/Bumblebee/ACS/DoorElements` enumerates the
   doors visible to the account; full per-door status is then fetched for each.
2. **Extra door IDs** — the hardcoded `EXTRA_DOOR_IDS` (in `const.py`) are
   fetched directly by ID and merged into the result.

The extra IDs exist because these doors are present on this district's
HikCentral server, but the account's list call does **not** return them. A
direct `GET /ISAPI/Bumblebee/ACS/DoorElements/{id}` still works for each
(verified live 2026-08-15):

| Extra Door ID | Name |
|---|---|
| 999 | Vyezd2.1 (barrier) |
| 1002 | Vyezd2.2 (barrier) |
| 1007 | Kalitka_MR1-2 |
| 536 | дверь_MR5 P2A |
| 538 | дверь_MR5 P2B |

These IDs are intentionally hardcoded — this repository is district-specific,
and they are deliberately **not** a config-flow option. A failed fetch of an
extra door is logged as a warning and skipped; it never breaks the update cycle.

## Entity Types

| Platform | Entity | Description |
|---|---|---|
| `lock` | `Door Lock (<name>)` | Lock control per door. State from `DoorStatus.LockState` (0=locked, 1=unlocked, other=unknown). Services: lock, unlock, open |
| `binary_sensor` | `<name> Door Contact` | Door contact magnet state (0=closed=off, 1=open=on) |
| `binary_sensor` | `<name> Online` | Door online/offline status |
| `camera` | `<name>` | Snapshot: live Authenty frame → HikCentral thumbnail → ffmpeg RTSP fallback. Live view: see [Live Video](#live-video-optional) |
| `sensor` | `HikCentral System` | Online controller count, total doors/cameras |

## Door Status Semantics

Each door reports a `DoorStatus` block; the fields below are also exposed as
state attributes on the lock entity:

| Field | Meaning |
|---|---|
| `MagnetState` | Door-contact magnet state (0=closed, 1=open) |
| `LockState` | 0 = locked, 1 = unlocked (any other value → unknown) |
| `PolicyState` | Access-policy state reported by the controller |
| `OverallStatus` | Aggregate door status reported by the controller |

## Services

### `hikcentral_district.door_action`

Send a control action to a specific door.

```yaml
service: hikcentral_district.door_action
data:
  door_id: "996"   # Door element ID
  action: 1        # 1=unlock/open, 2=lock, 3=remain unlocked, 4=remain locked
```

## Door Actions

Door control is sent as a raw HTTP PUT:

```
PUT /ISAPI/Bumblebee/ACS/DoorElements/{DoorID}/DoorAction?SID=<sid>
```

| Action | Meaning |
|---|---|
| 1 | Open / unlock |
| 2 | Lock |
| 3 | Remain unlocked |
| 4 | Remain locked |

These actions are exposed both through the lock entities (`open`, `lock`,
`unlock` — where `open` and `unlock` both send action 1) and through the
`hikcentral_district.door_action` service.

## Protocol Notes

- Authentication: plain-password XML login → AES key derivation (MD5^100(password + challenge))
- Each request: `AppendInfo` = AES-CBC base64 signature
- Door actions use **raw HTTP PUT** to `/ISAPI/Bumblebee/ACS/DoorElements/{id}/DoorAction?SID=<sid>` (no `MT=` parameter)
- Door status polled via `GET /ISAPI/Bumblebee/ACS/DoorElements/{id}`
- **Live streams**: `CommonUrl` → RTSP `Authenty` handshake (SEP DATA / Key / Identification headers,
  AES-256-CBC with challenge-mixed key) → RTP H.264, depacketized to Annex-B (see
  `hikcentral_bumblebee.streaming` docstring for the full reverse-engineered protocol)

## Live Video (optional)

Snapshots work out of the box (options → **live_snapshots** on by default).
For live streams in Lovelace, use the bundled go2rtc with the bridge script:

```yaml
# configuration.yaml
go2rtc:
  streams:
    hik_cam_240:                       # any name; reuse it below
      - exec: >
          python3 /config/custom_components/hikcentral_district/rtsp_bridge.py
          --host https://YOUR-HCP --username USER --password PASS
          --camera 240 --insecure
```

Then in the integration **Options** set *stream URL template* to
`rtsp://127.0.0.1:18554/hik_cam_{id}` — every camera entity gets a working
`stream_source` and Lovelace picture cards show live video. go2rtc starts
the bridge per viewer and stops it on disconnect (stream on demand).

Bridge modes:

```bash
# RTSP on stdout (for go2rtc exec:) — default mode
rtsp_bridge.py --host … --camera 240

# one-shot JPEG to stdout ( handy for cron/scripts )
rtsp_bridge.py --host … --camera 240 --jpeg 3 > frame.jpg

# raw H.264 to file (debug)
rtsp_bridge.py --host … --camera 240 --h264 /tmp/cam.h264
```

## Real Doors

> **Warning:** Real door open/lock commands are sent to live hardware.
> Test with mocks only in development. The integration will open physical doors.

## Credits

- Bumblebee API reverse-engineered from HikCentral Professional OverSea_Pro v2.x
- Python package: [hikcentral-bumblebee](https://github.com/megastruktur/hikcentral-bumblebee)

## License

MIT
