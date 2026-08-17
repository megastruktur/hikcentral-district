#!/usr/bin/env python3
"""Refresh district dashboard camera snapshots (/config/www/snapshots/*.jpg).

Reads HikCentral credentials from the hikcentral_district config entry,
pulls each camera's thumbnail via hikcentral_bumblebee, and atomically
replaces the jpg files used by the lovelace 'district' dashboard cards.

Run inside the homeassistant container:
    docker exec homeassistant python3 /config/scripts/refresh_district_snapshots.py
Triggered by automation 'district snapshots refresh' (time_pattern /10).
"""

from __future__ import annotations

import json
import os
import sys

from hikcentral_bumblebee import BumblebeeClient

# Camera mapping lives in the private cameras.json (gitignored; see
# dashboards/cameras.example.json) — the repo ships no real camera ids.
# Search order: --cameras PATH / $HIK_CAMERAS / <script>/../dashboards/cameras.json
OUT_DIR = "/config/www/snapshots"
CONFIG_ENTRIES = "/config/.storage/core.config_entries"


def load_camera_files() -> dict[str, str]:
    """HikCentral camera id -> output file name (from cameras.json jpgs)."""
    argv = sys.argv[1:]
    path = (
        argv[argv.index("--cameras") + 1] if "--cameras" in argv
        else os.environ.get("HIK_CAMERAS")
        or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "dashboards", "cameras.json"
        )
    )
    if not os.path.isfile(path):
        raise SystemExit(
            f"cameras config not found: {path}\n"
            "Fill dashboards/cameras.json (copy from cameras.example.json)."
        )
    cfg = json.load(open(path))
    return {
        str(c["id"]): os.path.basename(c["jpg"])
        for c in cfg.get("cameras", [])
        if c.get("jpg")
    }


def load_entry_data() -> dict:
    with open(CONFIG_ENTRIES) as f:
        for entry in json.load(f)["data"]["entries"]:
            if entry["domain"] == "hikcentral_district":
                return entry["data"]
    raise SystemExit("hikcentral_district config entry not found")


def main() -> int:
    camera_files = load_camera_files()
    data = load_entry_data()
    client = BumblebeeClient(
        data["url"], data["username"], data["password"],
        verify=data.get("verify_ssl", False),
    )
    client.login()
    os.makedirs(OUT_DIR, exist_ok=True)

    ok: list[str] = []
    failures: list[str] = []
    for cam_id, fname in camera_files.items():
        try:
            jpeg = client.get_camera_thumbnail(cam_id)
            if not jpeg or not jpeg.startswith(b"\xff\xd8"):
                failures.append(f"{cam_id}: no/invalid image (offline?)")
                continue
            tmp = os.path.join(OUT_DIR, f".{fname}.tmp")
            with open(tmp, "wb") as f:
                f.write(jpeg)
            os.replace(tmp, os.path.join(OUT_DIR, fname))
            ok.append(cam_id)
        except Exception as exc:  # noqa: BLE001 - per-camera isolation
            failures.append(f"{cam_id}: {exc}"[:160])

    print(f"refreshed {len(ok)}/{len(camera_files)}: {','.join(ok)}")
    for line in failures:
        print(f"  FAIL {line}", file=sys.stderr)
    # offline cameras (e.g. 280/P2B) are not a hard failure
    return 0 if len(ok) >= len(camera_files) - 2 else 1


if __name__ == "__main__":
    sys.exit(main())
