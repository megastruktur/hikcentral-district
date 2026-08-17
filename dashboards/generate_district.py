#!/usr/bin/env python3
"""Generate the district dashboard from a private cameras.json config.

The repo deliberately ships NO dashboard with real cameras — entity ids,
names and stream mappings are private. Everything is generated from
``cameras.json`` (gitignored; see cameras.example.json for the shape):

    {
      "dashboard": {"title": "...", "view_title": "...", "url_path": "district"},
      "cameras": [
        {"id": "240", "entity": "camera.x", "lock": "lock.x",
         "jpg": "/local/snapshots/x.jpg", "title": "...", "codec": "h264|h265"}
      ],
      "locks_only": [                      // optional; may be absent
        {"lock": "lock.y", "title": "Door Y"}
      ]
    }

Cameras are grouped into ONE card per door by their shared ``lock`` value:

  views         = the group's camera entities, in cameras.json order
  entity        = the shared lock entity
  image         = the FIRST camera's jpg (card cover)
  snapshot_file = basename of the first camera's jpg (refresh target)
  title         = the first camera's title

Cameras with ``lock: null`` become their own camera-only card
(``views: [<entity>]``, no ``entity`` — the card hides the Open button).
``locks_only`` entries become Open-only cards (``entity`` set, empty
``views``) for doors that have no streamable cameras yet.

Card shape (v8 — custom:district-intercom-card; frozen config schema):

    {
      "type": "custom:district-intercom-card",
      "entity": "lock.x",                    # lock entity; omitted camera-only
      "views": ["camera.a", "camera.b"],     # explicit camera entities
      "image": "/local/snapshots/x.jpg",     # optional cover
      "snapshot_file": "x.jpg",              # optional refresh target
      "title": "X"                           # optional
    }

The card itself handles cover/refresh, the Open button and the popup
(browser_mod live stream + views column) — no popup-card interception is
emitted anymore. The card JS is registered by install.sh as the Lovelace
resource /local/district/district-intercom-card.js?v=<version>.

Usage:
    # fresh dashboard skeleton (install.sh / new instances)
    python3 generate_district.py --create out.json [--cameras cameras.json]

    # rebuild district cards inside an existing exported dashboard
    python3 generate_district.py dashboard.json [--cameras cameras.json]

    # diff only (also normalizes legacy v7 picture-glance/popup-card pairs)
    python3 generate_district.py --check dashboard.json [--cameras cameras.json]
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

CARD_TYPE = "custom:district-intercom-card"


def load_cameras(path: str | None = None) -> tuple[dict, list[dict], list[dict]]:
    """Return (dashboard_meta, cameras_list, locks_only_list).

    cameras_list items: {"entity", "lock" (str|None), "jpg", "title"}.
    locks_only_list items: {"lock", "title"}.
    """
    path = path or os.path.join(HERE, "cameras.json")
    if not os.path.isfile(path):
        sys.exit(
            f"cameras config not found: {path}\n"
            "Copy dashboards/cameras.example.json -> dashboards/cameras.json "
            "and fill in YOUR cameras (the file is gitignored)."
        )
    cfg = json.load(open(path, encoding="utf-8"))
    meta = cfg.get("dashboard") or {}
    cameras = [
        {
            "entity": c["entity"],
            "lock": c.get("lock") or None,
            "jpg": c["jpg"],
            "title": c.get("title", c["entity"]),
        }
        for c in cfg.get("cameras", [])
    ]
    locks_only = [
        {"lock": lo["lock"], "title": lo.get("title", lo["lock"])}
        for lo in cfg.get("locks_only", [])
    ]
    return meta, cameras, locks_only


def _lock_title(lock: str) -> str:
    """Human title from a lock entity id: lock.vyezd2_3 -> 'Vyezd2 3'."""
    name = lock.split(".", 1)[-1]
    parts = name.replace("_", " ").split()
    return " ".join(p.capitalize() for p in parts) if parts else lock


def build_cards(cameras: list[dict], locks_only: list[dict]) -> list[dict]:
    """One district-intercom card per door (grouped by lock), then
    camera-only cards for lockless cameras, then locks_only cards."""
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    camera_only: list[dict] = []
    for cam in cameras:
        lock = cam["lock"]
        if lock is None:
            camera_only.append(cam)
            continue
        if lock not in groups:
            groups[lock] = []
            order.append(lock)
        groups[lock].append(cam)

    cards: list[dict] = []
    for lock in order:
        cams = groups[lock]
        first = cams[0]
        cards.append({
            "type": CARD_TYPE,
            "entity": lock,
            "views": [c["entity"] for c in cams],
            "image": first["jpg"],
            "snapshot_file": os.path.basename(first["jpg"]),
            "title": first["title"],
        })
    for cam in camera_only:
        cards.append({
            "type": CARD_TYPE,
            "views": [cam["entity"]],
            "image": cam["jpg"],
            "snapshot_file": os.path.basename(cam["jpg"]),
            "title": cam["title"],
        })
    for lo in locks_only:
        cards.append({
            "type": CARD_TYPE,
            "entity": lo["lock"],
            "views": [],
            "title": lo["title"],
        })
    return cards


def create_dashboard(meta: dict, cameras: list[dict], locks_only: list[dict]) -> dict:
    """Fresh minimal dashboard skeleton with one section of district cards."""
    cards: list = [{"type": "heading", "heading": meta.get("view_title", "Район")}]
    cards.extend(build_cards(cameras, locks_only))
    return {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace.district",
        "data": {
            "config": {
                "title": meta.get("title", "Район"),
                "views": [{
                    "title": meta.get("view_title", "Район"),
                    "path": meta.get("url_path", "district"),
                    "type": "sections",
                    "icon": "mdi:shield-home",
                    "max_columns": 4,
                    "sections": [{"type": "grid", "cards": cards}],
                }],
            }
        },
    }


def _walk(cards: list):
    for c in cards:
        yield c
        yield from _walk(c.get("cards", []))


def _legacy_cam_of(card: dict, entities: set[str]) -> str | None:
    """Camera entity of a legacy v7 camera card (picture-glance / popup-card /
    button-card with picture), or None if the card is not a known legacy form."""
    ctype = card.get("type")
    if ctype == "custom:popup-card":
        ent = card.get("entity")
        return ent if ent in entities else None
    if ctype == "custom:button-card":
        if not card.get("picture"):
            return None
    elif ctype != "picture-glance":
        return None
    tap = card.get("tap_action") or {}
    if tap.get("action") == "fire-dom-event":
        try:
            content = tap["browser_mod"]["data"]["content"][0]
            if content.get("type") == "vertical-stack":
                content = content["cards"][0]
            cam = content["camera_image"]
            return cam if cam in entities else None
        except (KeyError, IndexError, TypeError):
            return None
    ent = tap.get("entity")
    if ent in entities:
        return ent
    return None


def regenerate(doc: dict, cameras: list[dict], locks_only: list[dict]) -> int:
    """Replace legacy v7 camera cards with the new district-intercom cards and
    refresh the managed cards from cameras.json. Idempotent: a second run
    reports 0 changes. Non-district cards are preserved in place."""
    new_cards = build_cards(cameras, locks_only)
    by_key = {_card_key(c): c for c in new_cards}
    placed: set = set()
    entities = {c["entity"] for c in cameras}
    changed = 0

    def _process(cards: list) -> list:
        nonlocal changed
        out: list = []
        for card in cards:
            ctype = card.get("type")
            if ctype == "vertical-stack":
                card["cards"] = _process(card.get("cards", []))
                out.append(card)
                continue
            if ctype == CARD_TYPE:
                key = _card_key(card)
                fresh = by_key.get(key)
                if fresh is None:
                    changed += 1
                    continue  # stale managed card: no longer in cameras.json
                if key in placed:
                    changed += 1
                    continue  # duplicate of an already-placed managed card
                placed.add(key)
                if card != fresh:
                    card = dict(fresh)
                    changed += 1
                out.append(card)
                continue
            cam = _legacy_cam_of(card, entities)
            if cam is not None:
                # legacy v7 card: its group's new card is emitted at the first
                # legacy occurrence; further legacy cards of the same group
                # (second camera, popup-card) are dropped.
                for fresh in new_cards:
                    key = _card_key(fresh)
                    if key in placed:
                        continue
                    if cam in fresh.get("views", []):
                        placed.add(key)
                        out.append(dict(fresh))
                        break
                changed += 1
                continue
            out.append(card)
        return out

    for view in doc["data"]["config"].get("views", []):
        for section in view.get("sections", []):
            section["cards"] = _process(section.get("cards", []))

    # managed cards missing from the dashboard entirely -> append
    missing = [dict(c) for c in new_cards if _card_key(c) not in placed]
    if missing:
        sections = None
        for view in doc["data"]["config"].get("views", []):
            if view.get("sections"):
                sections = view["sections"]
                break
        if sections is None:
            sections = [{"type": "grid", "cards": []}]
            doc["data"]["config"].setdefault("views", []).append({
                "title": "Район", "path": "district", "type": "sections",
                "sections": sections,
            })
        sections[-1].setdefault("cards", []).extend(missing)
        changed += len(missing)
    return changed


def _card_key(card: dict) -> tuple:
    """Stable identity of a district card: its lock, or its first view."""
    return ("lock", card.get("entity")) if card.get("entity") else \
           ("view", (card.get("views") or [None])[0])


def main() -> None:
    args = sys.argv[1:]
    check = "--check" in args
    create = "--create" in args
    cameras_path = args[args.index("--cameras") + 1] if "--cameras" in args else None
    meta, cameras, locks_only = load_cameras(cameras_path)
    skip = {"--check", "--create", "--cameras", cameras_path or ""}
    paths = [a for a in args if a not in skip]
    n_cards = len(build_cards(cameras, locks_only))

    if create:
        out = paths[0] if paths else "/dev/stdout"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(create_dashboard(meta, cameras, locks_only), f,
                      ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"created dashboard skeleton: {out} ({n_cards} cards)")
        return
    if not paths:
        sys.exit("usage: generate_district.py <dashboard.json> [--cameras ...] [--check] | --create <out>")
    path = paths[0]
    doc = json.load(open(path, encoding="utf-8"))
    before = json.dumps(doc, ensure_ascii=False, sort_keys=True)
    n = regenerate(doc, cameras, locks_only)
    after = json.dumps(doc, ensure_ascii=False, sort_keys=True)
    print(f"district cards rebuilt: {n}")
    if check:
        print("DRY" if before == after else "CHANGED")
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
