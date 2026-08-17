# district-intercom-card — manual test checklist

Run on a live Home Assistant after the integration (0.6.2+) is installed via
HACS and the Lovelace resource is registered
(`/local/district/district-intercom-card.js?v=<version>`, JavaScript Module).

Conventions used below:

- **DevTools console** = browser developer tools → Console.
- Replace `camera.X`, `lock.Y`, `DEVICE_ID` with real values from your setup.
- All config examples are added via dashboard edit mode → Add card → search
  for "district-intercom" (visual editor), or via raw YAML
  (`type: custom:district-intercom-card`).

---

## 0. Sanity / registration

- [ ] Card appears in the card picker (search "district-intercom"). Adding it
      with no changes shows a friendly "Nothing configured yet" state, not an
      error card.
- [ ] Console shows one info line
      `district-intercom-card v0.6.2` and no red errors from this file.
- [ ] Card follows the active theme: switch HA to dark mode — card background,
      text, and borders follow (no white card stuck on a dark dashboard).

## 1. Placeholder cover (no `image`)

Config: `entity: lock.Y`, `views: [camera.X]`, no `image`.

- [ ] Cover area shows the built-in placeholder (dark gradient with a camera
      glyph) — not a broken-image icon.
- [ ] Title line shows the lock's friendly name when `title` is not set.

## 2. Refresh updates the cover (cache-bust)

Same config as §1.

- [ ] Small round refresh button (⤵) is visible top-right of the cover.
- [ ] Tap it: the button shows a spinner while the call is pending.
- [ ] When the snapshot succeeds, the cover updates to the fresh image
      (DevTools → Network or Elements: `<img>` src is
      `/local/snapshots/<file>.jpg?t=<timestamp>` — the `?t=` changes on each
      successful refresh).
- [ ] With `snapshot_file: custom.jpg` in config, the service call uses
      `filename: custom.jpg` (check DevTools → Network → WebSocket frames or
      the integration log), and the cover reloads
      `/local/snapshots/custom.jpg?t=…`.
- [ ] With `image:` set in config, refresh reloads that image path (with the
      `?t=` cache-buster) instead of the snapshot path.

## 3. Open button calls `lock.open`

Config with a real lock: `entity: lock.Y`.

- [ ] Full-width Open button at the bottom, text "Open" (or your `open_text`).
- [ ] Tap: button shows a brief pending state, then a green success flash with
      a check mark (~1.5 s), and the door/lock actually opens.
- [ ] DevTools → WebSocket frames (or Developer Tools → Actions log) shows a
      `lock/open` call with `entity_id: lock.Y`.
- [ ] With the lock entity unavailable (e.g. disable the camera/lock device
      temporarily), the Open button is visibly disabled and tapping does
      nothing.

## 4. Popup opens with live stream

Config with at least one streaming camera view.

- [ ] Tap the cover (not the buttons): a browser_mod popup opens.
- [ ] DevTools → WebSocket frames shows a `browser_mod/popup` call (browser_mod
      3.x service name — NOT `show_popup`) with `title` and `content` fields.
- [ ] Popup title matches the card title.
- [ ] Popup shows THIS card in live mode: live video of the first view
      (`camera_view: live`), the Open button underneath, and a vertical column
      of view buttons on the right.
- [ ] A "Live" badge with a pulsing dot is visible in the popup card header.

## 5. View-switch column

Config with 2+ views, e.g.
`views: [camera.X1, {entity: camera.X2, label: "Courtyard"}]`.

- [ ] One button per view in the right column; the active view is highlighted
      (accent border) and the others are dimmed.
- [ ] Labels: explicit `label` is shown when given; otherwise a readable label
      derived from the entity id (`camera.mr3_30_93` → "mr3 30 93").
- [ ] Thumbnails show the camera's latest HA snapshot when available
      (icon placeholder otherwise).
- [ ] Tap another view: the live stream switches to that camera and the
      highlight moves to the tapped button.
- [ ] Switching back and forth repeatedly keeps working (no blank stream).

## 6. Camera-only card (no Open button)

Config: only `views: [camera.X]` (no `entity`, no `device`) — e.g. the lift
camera.

- [ ] Cover + refresh button render normally.
- [ ] No Open button at the bottom.
- [ ] Tap the cover: popup opens with the live stream and no Open button.

## 7. Open-only card (no views)

Config: only `entity: lock.Y`.

- [ ] Placeholder cover, no refresh button.
- [ ] Tap the cover: popup opens with no video — just the Open button (and the
      "No cameras configured" note).
- [ ] Open button works from inside the popup too.

## 8. `device:` resolution

Config: `device: DEVICE_ID` (a device that has a lock entity) instead of
`entity:`. Find a device id under Settings → Devices & Services → device →
(copied from the URL or diagnostics).

- [ ] After the card loads, the Open button appears (resolved via the entity
      registry websocket `config/entity_registry/list`).
- [ ] Tapping Open calls `lock/open` for the device's lock entity.
- [ ] With a `device:` id that has no lock entity, no Open button appears and
      the card behaves as camera-only / empty.
- [ ] If both `entity:` and `device:` are set, `entity:` wins.

## 9. browser_mod missing → more-info fallback

Temporarily disable/uninstall browser_mod (or test on an HA without it).

- [ ] Tapping the cover does NOT throw; instead the native camera more-info
      dialog opens for the active view.
- [ ] Re-enable browser_mod: tapping the cover opens the popup again.

## 10. Offline camera / refresh failure

Use a camera that is offline in HikCentral (e.g. the known-offline P2B cam).

- [ ] Tap refresh: after the call fails, a small toast
      ("Couldn't refresh snapshot") appears over the cover and auto-dismisses
      (~3.5 s).
- [ ] The previous cover is kept (last snapshot or placeholder) — never a
      broken-image icon.
- [ ] If the configured `image:` file does not exist (404), the card falls
      back to the placeholder instead of showing a broken image.
- [ ] Open button still works while the camera is offline.

## 11. Visual editor round-trip

Edit the card in UI mode (pencil → card → edit).

- [ ] Fields present: Title, Lock entity, Camera views (textarea), Cover image,
      Snapshot file, Open button text, and Advanced → Device ID.
- [ ] Existing YAML config pre-fills all fields, including views
      (`camera.x | Label` lines for labeled views).
- [ ] Typing in any field live-previews the card (config-changed fires).
- [ ] Save, reopen the editor: values are unchanged (round-trip). Views with
      labels survive the round-trip.
- [ ] Clearing a field removes that key from the saved YAML (no empty strings
      left behind).

## 12. Responsive layout

- [ ] In a normal dashboard column (~300–500 px wide) the card looks correct:
      16:9 cover, legible title, full-width Open button.
- [ ] In the (wider) popup the view column stays on the right and usable.
- [ ] On a narrow phone-width popup/column, the view column shrinks but stays
      tappable; labels truncate with ellipsis instead of wrapping.

---

Known interpretations of the frozen spec (see Phase 2 lane report):

- After a successful refresh with **no** `image:` configured, the cover shows
  `/local/snapshots/<filename>` (the freshly written file) — that is the only
  way "refresh updates the cover" is observable without a configured image.
- more-info fallback targets the active camera; if the card has no views it
  targets the lock entity instead.
- The popup uses browser_mod 3.x's `browser_mod/popup` service with only
  schema fields (`title`, `content`) — no `size`, which doesn't exist in 3.x.
