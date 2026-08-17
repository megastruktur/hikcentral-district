#!/usr/bin/env python3
"""Auto-discover doorbell channels and seed cameras.json with them.

Why: on HikCentral Professional servers < V3 the mobile app shows each
intercom ONLY with its door-station camera channel (no RelatedElementList /
CCTV links exist server-side — verified on V1.7, see APP-API.md §8 in the
research notes). The doorbell channel is therefore the only "related"
camera the server itself defines, and this script discovers it for every
door you track so a fresh install doesn't have to hunt cameras manually.

What it does (merge, never destructive):
  - reads the door -> door_id map from cameras.json (``"doors"`` block,
    optional; see below)
  - logs into HikCentral (HIK_URL/HIK_USER/HIK_PASS env — same values as
    the go2rtc sidecar), walks video intercom details and resolves every
    door to its door-station camera element (id + name)
  - for each door ensures a doorbell entry exists in that lock's camera
    group and is placed FIRST (views order = cameras.json order; CCTV
    entries you added manually stay after it, untouched)
  - entity id is derived with the same slugify Home Assistant uses
    (verified against live entity ids); override by editing the entry
    afterwards — reruns are idempotent and respect your edits

cameras.json schema addition (optional, ignored when absent):

    "doors": {
      "lock.dver_mr5_p2a": "536",
      "lock.vyezd2_1": "999"
    }

Usage:
    HIK_URL=... HIK_USER=... HIK_PASS=... \
      python3 autodiscover.py [--cameras cameras.json] [--write]

Requires hikcentral_bumblebee (pip install
git+https://github.com/megastruktur/hikcentral-bumblebee).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

try:
    from hikcentral_bumblebee import BumblebeeClient
except ImportError:
    sys.exit(
        "hikcentral_bumblebee not installed:\n"
        "  pip install git+https://github.com/megastruktur/hikcentral-bumblebee"
    )


def slugify(name: str) -> str:
    """HA entity slug: lowercase, non-alphanumeric runs -> single '_'."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def discover_doorbells(client: BumblebeeClient) -> dict[str, dict]:
    """door_id -> {"id": element_id, "name": element_name}."""
    result: dict[str, dict] = {}
    intercoms = client.get_video_intercoms()
    for it in intercoms:
        try:
            detail = client.get_video_intercom(it.id)
        except Exception:  # noqa: BLE001 — one dead panel ≠ failure
            continue
        for cam in detail.cameras:
            if not cam.element_id:
                continue
            for door_id in detail.door_ids:
                result.setdefault(door_id, {"id": cam.element_id, "name": cam.name})
    return result


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0] or __name__
    )
    ap.add_argument("--cameras", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "cameras.json"))
    ap.add_argument("--write", action="store_true",
                    help="apply changes (default: dry-run)")
    args = ap.parse_args()

    url = os.environ.get("HIK_URL")
    user = os.environ.get("HIK_USER")
    password = os.environ.get("HIK_PASS")
    if not (url and user and password):
        sys.exit("set HIK_URL / HIK_USER / HIK_PASS (same as the go2rtc sidecar env)")

    cfg = json.load(open(args.cameras, encoding="utf-8"))
    doors: dict[str, str] = cfg.get("doors") or {}  # lock entity -> door_id
    if not doors:
        print(
            "no \"doors\" map in cameras.json — nothing to discover.\n"
            "Add {\"lock.entity\": \"<door_id>\"} pairs (door ids come from\n"
            "the hikcentral_district lock entity unique_ids) and rerun."
        )
        return

    client = BumblebeeClient(url, user, password, verify=False)
    client.login()
    doorbells = discover_doorbells(client)
    print(f"server: {len(doorbells)} door->doorbell channels discovered")

    cameras: list[dict] = cfg.get("cameras", [])
    changed = 0
    for lock_entity, door_id in doors.items():
        bell = doorbells.get(str(door_id))
        if not bell:
            print(f"  {lock_entity}: no doorbell channel for door {door_id} (skip)")
            continue
        entity = "camera." + slugify(bell["name"])
        group = [c for c in cameras if c.get("lock") == lock_entity]
        existing = next(
            (c for c in group if str(c.get("id")) == bell["id"]), None)
        if existing is None:
            entry = {
                "id": bell["id"],
                "entity": entity,
                "lock": lock_entity,
                "jpg": f"/local/snapshots/{slugify(bell['name'])}.jpg",
                "title": (group[0]["title"] if group else bell["name"]),
                "codec": "h264",  # door-station channels are h264 in practice
                "autodiscovered": True,
            }
            if group:
                idx = next(i for i, c in enumerate(cameras) if c in group)
                cameras.insert(idx, entry)
            else:
                cameras.append(entry)
            print(f"  {lock_entity}: + doorbell {entity} ({bell['name']}, id {bell['id']})")
            changed += 1
        elif group and group.index(existing) != 0:
            cameras.remove(existing)
            idx = next(i for i, c in enumerate(cameras) if c in group and c is not existing)
            cameras.insert(idx, existing)
            print(f"  {lock_entity}: doorbell {entity} moved to first view")
            changed += 1
        else:
            print(f"  {lock_entity}: doorbell {existing['entity']} already first (ok)")

    cfg["cameras"] = cameras
    if not changed:
        print("nothing to change")
        return
    if args.write:
        with open(args.cameras, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"written: {args.cameras} ({changed} changes)")
        print("next: regenerate go2rtc.yaml + dashboard, or rerun install.sh")
    else:
        print(f"dry-run: {changed} changes (use --write to apply)")


if __name__ == "__main__":
    main()
