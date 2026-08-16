#!/usr/bin/env python3
"""Generate the camera cards dashboard from a private cameras.json config.

The repo deliberately ships NO dashboard with real cameras — entity ids,
names and stream mappings are private. Everything is generated from
``cameras.json`` (gitignored; see cameras.example.json for the shape):

    {
      "dashboard": {"title": "...", "view_title": "...", "url_path": "district"},
      "cameras": [
        {"id": "240", "entity": "camera.x", "lock": "lock.x",
         "jpg": "/local/snapshots/x.jpg", "title": "...", "codec": "h264|h265"}
      ]
    }

Card shape per camera (v7):

  static   picture-glance — core card: jpg + lock.open entity icon +
           tap image -> more-info(camera)  [native dialog, always works]
  popup    custom:popup-card (browser_mod) right after the static card —
           replaces the camera's more-info dialog with a LIVE
           picture-glance (aspect_ratio 16:9 = placeholder while loading)
           + a big «ОТКРЫТЬ» button. Invisible outside edit mode.
           Graceful degradation: if browser_mod fails, the native
           more-info camera player still plays the stream.

Usage:
    # fresh dashboard skeleton (install.sh / new instances)
    python3 generate_district.py --create out.json [--cameras cameras.json]

    # rebuild camera cards inside an existing exported dashboard
    python3 generate_district.py dashboard.json [--cameras cameras.json]

    # diff only (also normalizes to one card pair per camera)
    python3 generate_district.py --check dashboard.json [--cameras cameras.json]
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_cameras(path: str | None = None) -> tuple[dict, dict[str, tuple]]:
    """Return (dashboard_meta, {camera_entity: (hik_id, lock, jpg, title)})."""
    path = path or os.path.join(HERE, "cameras.json")
    if not os.path.isfile(path):
        sys.exit(
            f"cameras config not found: {path}\n"
            "Copy dashboards/cameras.example.json -> dashboards/cameras.json "
            "and fill in YOUR cameras (the file is gitignored)."
        )
    cfg = json.load(open(path, encoding="utf-8"))
    meta = cfg.get("dashboard") or {}
    by_cam = {
        c["entity"]: (
            str(c["id"]),
            c.get("lock") or None,
            c["jpg"],
            c.get("title", c["entity"]),
        )
        for c in cfg.get("cameras", [])
    }
    return meta, by_cam


def _open_lock(lock: str) -> dict:
    return {
        "entity": lock,
        "icon": "mdi:door-open",
        "tap_action": {
            "action": "perform-action",
            "perform_action": "lock.open",
            "target": {"entity_id": lock},
        },
    }


def card_for(cam: str, by_cam: dict[str, tuple]) -> dict:
    """Static core card: snapshot jpg + lock-open icon + native more-info."""
    _hik_id, lock, jpg, title = by_cam[cam]
    entities = [_open_lock(lock)] if lock else [
        {"entity": cam, "icon": "mdi:cctv", "name": " "}
    ]
    return {
        "type": "picture-glance",
        "title": title,
        "image": jpg,
        "entities": entities,
        "tap_action": {"action": "more-info", "entity": cam},
    }


def popup_card_for(cam: str, by_cam: dict[str, tuple]) -> dict:
    """browser_mod popup-card: replaces the camera's more-info dialog with
    live video (fixed-height placeholder) + a big «ОТКРЫТЬ» button."""
    _hik_id, lock, jpg, title = by_cam[cam]
    video_card = {
        "type": "picture-glance",
        "title": " ",
        "camera_image": cam,
        "camera_view": "live",
        # aspect_ratio держит высоту карточки ещё до старта стрима
        "aspect_ratio": "16:9",
        "entities": [_open_lock(lock)] if lock else [],
    }
    open_button = {
        "type": "custom:button-card",
        "name": "ОТКРЫТЬ",
        "icon": "mdi:door-open",
        "tap_action": {
            "action": "perform-action",
            "perform_action": "lock.open",
            "target": {"entity_id": lock},
        },
        "styles": {
            "card": [{"height": "64px", "font-size": "22px"}],
            "icon": [{"--mdc-icon-size": "36px"}],
        },
    }
    return {
        "type": "custom:popup-card",
        "entity": cam,
        "title": title,
        "size": "normal",
        "card": {
            "type": "vertical-stack",
            "cards": [video_card] + ([open_button] if lock else []),
        },
    }


def create_dashboard(meta: dict, by_cam: dict[str, tuple]) -> dict:
    """Fresh minimal dashboard skeleton with one section of camera cards."""
    cards: list = [{"type": "heading", "heading": meta.get("view_title", "Камеры")}]
    for cam in by_cam:
        cards.append(card_for(cam, by_cam))
        cards.append(popup_card_for(cam, by_cam))
    return {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace.district",
        "data": {
            "config": {
                "title": meta.get("title", "Район"),
                "views": [{
                    "title": meta.get("view_title", "Камеры"),
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


def _cam_of(card: dict, by_cam: dict[str, tuple]) -> str | None:
    """Camera entity of a camera card (any historical form)."""
    if card.get("type") == "custom:popup-card":
        return card.get("entity")
    tap = card.get("tap_action") or {}
    if tap.get("action") == "fire-dom-event":
        try:
            content = tap["browser_mod"]["data"]["content"][0]
            if content.get("type") == "vertical-stack":
                content = content["cards"][0]
            return content["camera_image"]
        except (KeyError, IndexError, TypeError):
            return None
    return tap.get("entity")


def _is_static_cam_card(card: dict, by_cam: dict[str, tuple]) -> bool:
    """Только статичные карточки камер (popup-card сюда НЕ входит)."""
    if card.get("type") == "custom:popup-card":
        return False
    if card.get("type") == "custom:button-card":
        return bool(card.get("picture")) and _cam_of(card, by_cam) in by_cam
    if card.get("type") != "picture-glance":
        return False
    return _cam_of(card, by_cam) in by_cam


def regenerate(doc: dict, by_cam: dict[str, tuple]) -> int:
    """Rebuild static camera cards in-place; normalize to exactly one
    static + one popup-card per camera (removes older-run duplicates)."""
    changed = 0
    for view in doc["data"]["config"].get("views", []):
        for section in view.get("sections", []):
            seen: set = set()
            new_cards: list = []
            for card in section.get("cards", []):
                if card.get("type") == "custom:popup-card":
                    continue  # пересоберём после статиков
                if card.get("type") == "vertical-stack":
                    inner_seen: set = set()
                    new_inner: list = []
                    for c in card.get("cards", []):
                        if c.get("type") == "custom:popup-card":
                            continue
                        if _is_static_cam_card(c, by_cam) and (cam := _cam_of(c, by_cam)):
                            if cam in inner_seen:
                                changed += 1
                                continue
                            inner_seen.add(cam)
                            new_inner.append(card_for(cam, by_cam))
                            new_inner.append(popup_card_for(cam, by_cam))
                            changed += 1
                        else:
                            new_inner.append(c)
                    card["cards"] = new_inner
                    new_cards.append(card)
                elif _is_static_cam_card(card, by_cam) and (cam := _cam_of(card, by_cam)):
                    if cam in seen:
                        changed += 1
                        continue
                    seen.add(cam)
                    new_cards.append(card_for(cam, by_cam))
                    new_cards.append(popup_card_for(cam, by_cam))
                    changed += 1
                else:
                    new_cards.append(card)
            section["cards"] = new_cards
    return changed


def main() -> None:
    args = sys.argv[1:]
    check = "--check" in args
    create = "--create" in args
    cameras_path = args[args.index("--cameras") + 1] if "--cameras" in args else None
    meta, by_cam = load_cameras(cameras_path)
    skip = {"--check", "--create", "--cameras", cameras_path or ""}
    paths = [a for a in args if a not in skip]

    if create:
        out = paths[0] if paths else "/dev/stdout"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(create_dashboard(meta, by_cam), f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"created dashboard skeleton: {out} ({len(by_cam)} cameras)")
        return
    if not paths:
        sys.exit("usage: generate_district.py <dashboard.json> [--cameras ...] [--check] | --create <out>")
    path = paths[0]
    doc = json.load(open(path, encoding="utf-8"))
    before = json.dumps(doc, ensure_ascii=False, sort_keys=True)
    n = regenerate(doc, by_cam)
    after = json.dumps(doc, ensure_ascii=False, sort_keys=True)
    print(f"camera cards rebuilt: {n}")
    if check:
        print("DRY" if before == after else "CHANGED")
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
