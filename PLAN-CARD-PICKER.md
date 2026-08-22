# Plan — Fix issue #1: district-intercom-card missing from the card picker

Issue: https://github.com/megastruktur/hikcentral-district/issues/1
Reporter cannot find "District Intercom" when adding a card to a dashboard.

## 1. Root cause

The HA card picker does **not** enumerate registered custom elements. It builds
its list exclusively from:

- built-in localized cards,
- energy cards,
- **`window.customCards` entries** (`src/data/lovelace_custom_cards.ts` in
  home-assistant/frontend captures `window.customCards` by reference at module
  init; `hui-card-picker.ts` filters `card.isCustom` from that array).

`district-intercom-card.js` defines the element, `getConfigElement()` and
`getStubConfig()` (lines 424–430) — but **never pushes an entry into
`window.customCards`**. `grep customCards` across the repo: 0 matches.
Per the official docs ("Graphical card configuration",
developers.home-assistant.io/docs/frontend/custom-ui/custom-card/), that push
is required for picker visibility.

Everything else in the delivery chain is present and tested: www sync
(`sync_frontend_js`), resource registration + `?v=` upkeep
(`async_sync_frontend_resource`, `install.sh` staging), editor element, stub
config. Only the picker registration is missing.

Secondary defects found during investigation (fixed alongside):

| # | Defect | Where |
|---|--------|-------|
| S1 | `VERSION = "0.6.6"` in JS vs `manifest.json` `"0.6.9"` — console banner lies; `?v=` cache-buster keys off the manifest, not this constant | `frontend/district-intercom-card.js:36` |
| S2 | README resource example pinned to `?v=0.6.0`; no mention that the card is picker-discoverable | `README.md:410–419` |
| S3 | TEST-CHECKLIST references v0.6.6; the "card appears in picker" checkbox (line 19) has never been satisfiable | `frontend/TEST-CHECKLIST.md:3,19,23` |

## 2. Fix design

### 2.1 Core change — register in `window.customCards`

One file: `custom_components/hikcentral_district/frontend/district-intercom-card.js`.

Insert after the two `customElements.define` guards in the boot block
(after current line 1234, before `console.info`):

```js
// Card picker registration (HA custom-card docs): the picker lists ONLY
// types present in window.customCards. Always push onto the existing
// array — never reassign — HA's lovelace_custom_cards module captures the
// array reference at frontend load. Dedupe guards a double module eval
// (e.g. stale + fresh resource URL registered side by side).
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c && c.type === "custom:" + CARD_TAG)) {
  window.customCards.push({
    type: "custom:" + CARD_TAG,
    name: "District Intercom",
    description:
      "HikCentral door entry — camera views, snapshot refresh, open button",
    preview: true, // live preview from getStubConfig(): friendly empty state
    documentationURL: "https://github.com/megastruktur/hikcentral-district",
    // HA >= 2026.6: entity-first picker shows this under "Community".
    // Unknown keys are ignored by older HA — safe to ship unconditionally.
    getEntitySuggestion: (hass, entityId) => {
      const domain = String(entityId || "").split(".")[0];
      if (domain === "lock")
        return {
          config: { type: "custom:" + CARD_TAG, entity: entityId, views: [] },
        };
      if (domain === "camera")
        return {
          config: { type: "custom:" + CARD_TAG, views: [entityId] },
        };
      return null;
    },
  });
}
```

Design decisions:

- **`lock` → open-only card** (`entity` + empty `views`) and **`camera` →
  camera-only card** (`views` only, no Open button): both are documented,
  supported modes (README "Card config reference" / "Open-only"). We cannot
  know a door's camera set from the entity id, so suggest the minimal valid
  config; the visual editor refines it. `null` for everything else keeps the
  Community section noise-free (docs explicitly warn against over-suggesting).
- **`preview: true`**: `getStubConfig()` returns `{ entity: "", views: [] }`
  and the card renders a friendly "Nothing configured yet" state — this is
  already an explicit TEST-CHECKLIST expectation (line 19–21).
- **Push, never reassign** `window.customCards`: reassignment desyncs from
  HA's captured reference. `.some()` dedupe matches the file's existing
  `if (!customElements.get(...))` idempotency style.
- Suggestion `config` includes the `custom:`-prefixed `type` (docs require it).

### 2.2 Version alignment

- `frontend/district-intercom-card.js:36` — `VERSION = "0.6.6"` → `"0.6.10"`
  (restores banner/truth parity; S1).
- `manifest.json` — `"version": "0.6.9"` → `"0.6.10"`. HACS offers the update
  only on a manifest version bump + GitHub Release (README release rule).

## 3. Phases

### Phase 0 — Baseline
1. `pytest` in repo root (pytest.ini already scopes testpaths). All green
   before touching anything. No Python code changes are planned, so this is
   a regression gate only.

### Phase 1 — Code
1. Apply §2.1 insertion to `frontend/district-intercom-card.js`.
2. Bump `VERSION` (§2.2).
3. Bump `manifest.json` version (§2.2).

### Phase 2 — Verification (no Python surface changed → JS-level proof)
1. **Syntax**: `node --check district-intercom-card.js`.
2. **Behavioral smoke** (browser tool + throwaway harness, deleted after):
   - serve `frontend/` over localhost;
   - harness page pre-creates `window.customCards = []` (HA loads before any
     resource module, so this mimics production ordering), imports the module
     twice under different URLs (`card.js` and `card.js?v=2`) to simulate the
     stale+fresh double-registration;
   - assert exactly ONE entry with `type: "custom:district-intercom-card"`,
     `name`/`preview`/`documentationURL` set;
   - assert `customElements.get("district-intercom-card")` and the editor tag
     are defined;
   - assert `getEntitySuggestion({}, "lock.a")` → open-only config with
     correct `type`; `("camera.b")` → camera-only config; `("light.c")` →
     `null`.
3. **Regression gate**: re-run `pytest` — still green.

### Phase 3 — Docs
1. `README.md` card section:
   - state the card appears in the picker as **"District Intercom"** (since
     v0.6.10), searchable via "district-intercom";
   - note the HA ≥ 2026.6 Community suggestions for lock/camera entities;
   - replace the `?v=0.6.0` example with a current one and note the `?v=` is
     auto-maintained by the integration on restart (S2);
   - troubleshooting line: after a HACS update → restart HA → reload the
     browser tab once (the dashboard imports resources at page load).
2. `frontend/TEST-CHECKLIST.md`:
   - version refs 0.6.6 → 0.6.10 (lines 3, 23);
   - expand the picker checkbox (line 19): picker entry exists, live preview
     shows the empty state, and (HA ≥ 2026.6) lock/camera entities offer the
     card under Community.

### Phase 4 — Release & rollout
1. Commit (`fix(card): register district-intercom-card in window.customCards
   so it appears in the card picker (fixes #1)`).
2. Push; tag `v0.6.10`; create GitHub Release `v0.6.10` — HACS requires the
   release to offer the update.
3. Live HA: HACS → HikCentral District → Update → restart HA
   (`sync_frontend_js` + `async_sync_frontend_resource` run at setup) →
   hard-reload the browser tab → verify the Phase 3 checklist items on the
   live instance (own instance: platform/homeassistant).
4. Reply on issue #1:
   - root cause (picker lists only `window.customCards`; the card never
     registered);
   - **interim workaround valid today**: Add card → *Manual* → paste the YAML
     config from README (`type: custom:district-intercom-card`, …) — the card
     itself works without the picker entry;
   - fixed in v0.6.10: update via HACS, restart HA, reload the browser, the
     card appears in the picker ("District Intercom") and as a suggestion
     when picking a lock/camera entity on HA ≥ 2026.6.

## 4. Acceptance criteria

- [ ] `node --check` passes on the patched JS.
- [ ] Harness run: exactly one `window.customCards` entry after double import;
      both custom elements defined; suggestion function returns lock/camera
      configs and `null` otherwise.
- [ ] `pytest` green before and after.
- [ ] `manifest.json` 0.6.10 ≠ released 0.6.9; JS `VERSION` matches manifest.
- [ ] README/TEST-CHECKLIST updated as above.
- [ ] GitHub Release v0.6.10 published.
- [ ] Issue #1 answered with workaround + fix version.

## 5. Risks & mitigations

| Risk | Assessment |
|------|------------|
| `getEntitySuggestion` on HA < 2026.6 | Unknown key ignored by the frontend's `CustomCardEntry` handling — harmless. Mechanism shipped in 2026.6 (May 2026); current stable is 2026.8. |
| Double module eval (stale + fresh resource URL both registered) duplicates the picker entry | `.some()` dedupe by type. |
| Reassigning instead of pushing breaks all picker visibility silently | Guarded by design + harness asserts push-onto-existing-array ordering. |
| `preview: true` renders a broken preview | Stub config `{entity:"", views:[]}` renders the designed empty state (TEST-CHECKLIST line 19–21 already asserts it). |
| Users on the current release still can't find the card | Interim workaround (Manual + YAML) posted in the issue; `?v=` URL change forces a fresh fetch, no stale-cache window. |
| YAML-mode Lovelace | Resource already registered manually by such users; picker registration is client-side and mode-independent. |

## 6. Rollback

Revert the commit and release `v0.6.9.1` (or re-release 0.6.9 instructions);
the next HA restart re-syncs `www/district/` and the resource `?v=` back.
No data/config migrations involved — the change is additive client JS.

## 7. Out of scope

- Any change to `install.sh`, resource staging, or the Python integration
  (verified correct and covered by `test_frontend_sync.py`).
- Restructuring the card into a build-step/lit project.
- Auto-suggesting intercom camera pairing for locks (needs device registry
  lookups in the suggestion; revisit only if users ask).
