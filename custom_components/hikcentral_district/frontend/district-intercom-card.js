/**
 * district-intercom-card — Lovelace card for HikCentral District door entry.
 *
 * One file, no build step, no dependencies. Registers:
 *   - <district-intercom-card>          (the card)
 *   - <district-intercom-card-editor>   (visual config editor)
 *
 * Config (the ONLY source of views — nothing is hardcoded):
 *   type: custom:district-intercom-card
 *   entity: lock.my_door              # door lock entity; OR device: <device_id>
 *   device: 1a2b3c4d...               # alternative to entity (entity wins)
 *   views:                            # any number of camera entities
 *     - camera.gate_1                 #   plain entity id
 *     - entity: camera.gate_2         #   or object form with optional label
 *       label: Gate 2
 *   image: /local/snapshots/gate.jpg  # optional cover; default placeholder
 *   snapshot_file: gate.jpg           # optional refresh target
 *   title: Main Gate                  # optional
 *   open_text: Open                   # optional, default "Open"
 *   live: true                        # internal: popup/live mode (set by the card)
 *
 * Behaviors:
 *   - Cover: `image` or a built-in SVG placeholder; refresh button (top-right)
 *     calls hikcentral_district.refresh_snapshot, then cache-busts the cover.
 *   - Open (bottom, full width): lock.open for the configured lock.
 *   - Card click: wide browser_mod popup (3.x `popup` service with
 *     initial_style "wide") holding this same card in live mode (live
 *     stream + view-switch strip). Falls back to native more-info when
 *     browser_mod is unavailable. Live mode is popup-only by design.
 *     The stream is a real picture-glance card; since HA registers hui-*
 *     elements lazily, it is created via window.loadCardHelpers() when the
 *     element is not on the page yet.
 *   - device: resolved to a lock entity via the entity registry websocket.
 */

const VERSION = "0.6.10";
const CARD_TAG = "district-intercom-card";
const EDITOR_TAG = "district-intercom-card-editor";
const SNAPSHOT_BASE = "/local/snapshots/";

/* ------------------------------------------------------------------ misc */

function entityLocalPart(entityId) {
  return String(entityId || "")
    .split(".")
    .slice(1)
    .join(".");
}

/** camera.mr5_p2a -> mr5_p2a.jpg (frozen service contract default). */
function deriveFilename(entityId) {
  return (entityLocalPart(entityId) || "snapshot") + ".jpg";
}

/** Short human label from a camera entity id. */
function deriveLabel(entityId) {
  return (
    entityLocalPart(entityId)
      .replace(/[_\-]+/g, " ")
      .trim() || String(entityId)
  );
}

function cacheBust(url) {
  return url + (url.includes("?") ? "&" : "?") + "t=" + Date.now();
}

/** Tiny DOM builder. */
function h(tag, props, ...children) {
  const node = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else if (k === "value") node.value = v;
      else if (k.startsWith("on") && typeof v === "function")
        node.addEventListener(k.slice(2), v);
      else if (v === true) node.setAttribute(k, "");
      else node.setAttribute(k, v);
    }
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    node.appendChild(
      typeof child === "string" ? document.createTextNode(child) : child
    );
  }
  return node;
}

/* -------------------------------------------------------- visual assets */

/** Neutral "camera / doorbell" placeholder, inlined so it never 404s. */
const PLACEHOLDER_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#262c3a"/><stop offset="1" stop-color="#141821"/></linearGradient></defs><rect width="800" height="450" fill="url(#g)"/><g fill="none" stroke="#4e5a70" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"><path d="M353 158a22 22 0 0 1 44 0" opacity="0.85"/><path d="M335 158a40 40 0 0 1 80 0" opacity="0.45"/><rect x="315" y="185" width="120" height="90" rx="16"/><path d="M435 210l57-28v96l-57-28z"/><circle cx="357" cy="230" r="15" opacity="0.55"/></g></svg>`;
const PLACEHOLDER_URL = "data:image/svg+xml," + encodeURIComponent(PLACEHOLDER_SVG);

/** Inline icons (stroke-based, follow currentColor). */
const ICONS = {
  refresh:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>',
  unlock:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>',
  check:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  video:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>'
};

/* ------------------------------------------------------------------- css */

const CSS = `
:host { display: block; }

[hidden] { display: none !important; }

.card {
  position: relative;
  background: var(--ha-card-background-color, var(--card-background-color, #fff));
  color: var(--primary-text-color, #212121);
  border-radius: var(--ha-card-border-radius, 12px);
  border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, rgba(0,0,0,0.10));
  box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,0.14));
  overflow: hidden;
  font-family: var(--paper-font-body1_-_font-family, inherit);
}

/* ---------------- static cover ---------------- */

.media {
  position: relative;
  aspect-ratio: 16 / 9;
  background: #10141c;
  cursor: pointer;
  outline: none;
}
.media:focus-visible { box-shadow: inset 0 0 0 2px var(--primary-color, #03a9f4); }
.media.static { transition: filter 0.15s ease; }
.media.static:hover { filter: brightness(1.05); }
.media.static:active { filter: brightness(0.96); }

img.cover {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
  transition: opacity 0.35s ease;
}
img.cover.dim { opacity: 0.3; }

.scrim {
  position: absolute; inset: 0;
  pointer-events: none;
  background: linear-gradient(to top, rgba(0,0,0,0.62), rgba(0,0,0,0.22) 42%, rgba(0,0,0,0) 68%);
}

.title {
  position: absolute; left: 14px; right: 56px; bottom: 10px;
  color: #fff;
  font-size: 16px; font-weight: 600; letter-spacing: 0.01em;
  text-shadow: 0 1px 3px rgba(0,0,0,0.6);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  pointer-events: none;
}

.icon-btn {
  position: absolute; top: 8px; right: 8px;
  width: 36px; height: 36px;
  border: none; border-radius: 50%;
  background: rgba(13,16,23,0.55);
  color: #fff;
  display: grid; place-items: center;
  cursor: pointer;
  -webkit-backdrop-filter: blur(4px); backdrop-filter: blur(4px);
  transition: background 0.15s ease, transform 0.1s ease;
}
.icon-btn:hover { background: rgba(13,16,23,0.78); }
.icon-btn:active { transform: scale(0.9); }
.icon-btn:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 1px; }
.icon-btn .ic { width: 18px; height: 18px; display: block; }
.icon-btn .ic svg { width: 100%; height: 100%; display: block; }

.spin {
  width: 16px; height: 16px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  animation: dic-spin 0.8s linear infinite;
}
@keyframes dic-spin { to { transform: rotate(360deg); } }

/* ---------------- open button ---------------- */

.open {
  display: flex; align-items: center; justify-content: center; gap: 10px;
  width: 100%;
  min-height: 54px;
  padding: 10px 16px;
  border: none;
  background: var(--primary-color, #03a9f4);
  color: var(--text-primary-color, #fff);
  font-size: 16px; font-weight: 600; letter-spacing: 0.02em;
  cursor: pointer;
  border-top: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  transition: filter 0.15s ease, transform 0.08s ease, background-color 0.25s ease;
}
.open:hover:not(:disabled) { filter: brightness(1.07); }
.open:active:not(:disabled) { transform: scale(0.99); filter: brightness(0.92); }
.open:focus-visible { outline: 2px solid var(--text-primary-color, #fff); outline-offset: -4px; }
.open:disabled {
  background: var(--disabled-color, #9e9e9e);
  color: var(--text-primary-color, #fff);
  cursor: default; opacity: 0.85;
}
.open.success:not(:disabled) { background: var(--success-color, #43a047); }
.open .open-ic { width: 20px; height: 20px; display: block; }
.open .open-ic svg { width: 100%; height: 100%; display: block; }
.open .open-spin {
  width: 18px; height: 18px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.35);
  border-top-color: currentColor;
  animation: dic-spin 0.8s linear infinite;
}

/* ---------------- toast ---------------- */

.toast {
  position: absolute; left: 50%; bottom: 12px;
  transform: translate(-50%, 6px);
  max-width: 90%;
  background: rgba(18,22,30,0.92);
  color: #fff;
  font-size: 13px; line-height: 1.3; text-align: center;
  padding: 8px 14px;
  border-radius: 999px;
  opacity: 0; pointer-events: none;
  transition: opacity 0.25s ease, transform 0.25s ease;
  z-index: 5;
}
.toast.show { opacity: 1; transform: translate(-50%, 0); }

/* ---------------- empty state ---------------- */

.empty {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 4px; text-align: center;
  color: rgba(255,255,255,0.85);
  padding: 16px;
}
.empty .empty-title { font-size: 15px; font-weight: 600; }
.empty .empty-sub { font-size: 12.5px; opacity: 0.75; max-width: 34ch; }

/* ------------- live mode (only ever rendered inside the popup) ------------- */

/* The browser_mod dialog is the surface: flatten all card chrome. */
.card.live {
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
  overflow: visible;
}

.live-main {
  position: relative;
  display: flex; flex-direction: column;
  gap: 12px;
}

.stream-box { position: relative; }

/* The stream is the hero: full popup width, 16:9, grows with the dialog. */
.stream {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: #10141c;
  aspect-ratio: 16 / 9;
}
.stream > * { width: 100%; height: 100%; }
.stream hui-picture-glance-card { display: block; }
.stream hui-picture-glance-card ha-card {
  --ha-card-border-width: 0px;
  --ha-card-box-shadow: none;
  height: 100%;
}

/* Compact Live badge over the stream — the dialog already shows the title. */
.live-badge {
  position: absolute; top: 10px; left: 10px;
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(13,16,23,0.6);
  -webkit-backdrop-filter: blur(4px); backdrop-filter: blur(4px);
  color: #fff;
  font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
  pointer-events: none;
  z-index: 2;
}
.live-badge .dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--error-color, #db4437);
  animation: dic-pulse 1.6s ease-in-out infinite;
}
@keyframes dic-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

/* View switch: horizontal strip under the stream; scrolls if it overflows. */
.views-row {
  display: flex; gap: 10px;
  overflow-x: auto;
  scrollbar-width: thin;
  padding-bottom: 2px;
}
.view {
  display: block;
  width: clamp(96px, 18%, 168px);
  padding: 0; border: none; background: none;
  cursor: pointer;
  flex: none;
}
.view .thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 8px;
  overflow: hidden;
  background: #171c26;
  border: 2px solid transparent;
  display: grid; place-items: center;
  color: #4e5a70;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.view .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0.72; transition: opacity 0.15s ease; }
.view:hover .thumb img { opacity: 1; }
.view .thumb-ic { width: 20px; height: 20px; display: block; }
.view .thumb-ic svg { width: 100%; height: 100%; display: block; }
.view .view-label {
  display: block;
  margin-top: 3px;
  font-size: 10.5px; line-height: 1.2;
  color: var(--secondary-text-color, #727272);
  text-align: center;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.view.active .thumb {
  border-color: var(--primary-color, #03a9f4);
  box-shadow: 0 0 0 1px var(--primary-color, #03a9f4);
}
.view.active .thumb img { opacity: 1; }
.view.active .view-label { color: var(--primary-text-color, #212121); font-weight: 600; }
.view:focus-visible .thumb { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 1px; }

/* Open in the popup: prominent but constrained, centered when room allows. */
.card.live .open {
  max-width: 340px;
  margin: 0 auto;
  min-height: 52px;
  border-radius: 12px;
  border-top: none;
}

/* ---------------- editor ---------------- */

.editor { display: block; padding: 4px 0 8px; }
.editor .field { margin-bottom: 12px; }
.editor label {
  display: block;
  font-size: 12px; font-weight: 600;
  color: var(--secondary-text-color, #727272);
  margin-bottom: 4px;
}
.editor input, .editor textarea {
  width: 100%; box-sizing: border-box;
  padding: 8px 10px;
  font-size: 14px;
  color: var(--primary-text-color, #212121);
  background: var(--input-fill-background-color, rgba(0,0,0,0.04));
  border: 1px solid var(--input-border-color, rgba(0,0,0,0.22));
  border-radius: 8px;
  font-family: inherit;
}
.editor input:focus, .editor textarea:focus {
  outline: none;
  border-color: var(--primary-color, #03a9f4);
  box-shadow: 0 0 0 1px var(--primary-color, #03a9f4);
}
.editor textarea { resize: vertical; min-height: 74px; }
.editor .hint { font-size: 11.5px; color: var(--secondary-text-color, #9e9e9e); margin-top: 3px; }
.editor details { margin-bottom: 4px; }
.editor summary {
  cursor: pointer;
  font-size: 12px; font-weight: 600;
  color: var(--secondary-text-color, #727272);
  padding: 4px 0 8px;
  user-select: none;
}
`;

/* ------------------------------------------------------------------ card */

class DistrictIntercomCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._views = [];
    this._activeView = 0;
    this._lockFromDevice = undefined; // undefined = unresolved, null = none found
    this._resolvingDevice = false;
    this._refreshing = false;
    this._opening = false;
    this._openSuccess = false;
    this._lastCoverUrl = null; // last known-good cover after a successful refresh
    this._toastTimer = null;
    this._successTimer = null;
    this._els = {};
  }

  /* ------------------------------------------------ Lovelace card API */

  static getStubConfig() {
    return { entity: "", views: [] };
  }

  static async getConfigElement() {
    return document.createElement(EDITOR_TAG);
  }

  getCardSize() {
    return 4;
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid configuration");
    }
    const rawViews = config.views == null ? [] : config.views;
    if (!Array.isArray(rawViews)) {
      throw new Error("`views` must be a list of camera entities");
    }
    const views = [];
    for (const v of rawViews) {
      if (typeof v === "string") {
        const s = v.trim();
        if (s) views.push({ entity: s, label: null });
      } else if (
        v &&
        typeof v === "object" &&
        typeof v.entity === "string" &&
        v.entity.trim()
      ) {
        views.push({
          entity: v.entity.trim(),
          label:
            typeof v.label === "string" && v.label.trim()
              ? v.label.trim()
              : null
        });
      }
    }

    const prevKey = this._views.map((v) => v.entity).join("|");
    this._config = { ...config, views };
    this._views = views;
    if (views.map((v) => v.entity).join("|") !== prevKey) this._activeView = 0;
    if (this._activeView >= views.length) this._activeView = 0;
    this._lastCoverUrl = null;
    this._openSuccess = false;

    this._buildDom();
    if (this._hass) this._afterHassUpdate();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._afterHassUpdate();
  }

  get hass() {
    return this._hass;
  }

  /* ---------------------------------------------------- derived state */

  _isLive() {
    return Boolean(this._config && this._config.live === true);
  }

  _hasLockConfig() {
    const c = this._config || {};
    return Boolean(
      (typeof c.entity === "string" && c.entity.trim()) ||
        (typeof c.device === "string" && c.device.trim())
    );
  }

  _lockEntity() {
    const c = this._config || {};
    if (typeof c.entity === "string" && c.entity.trim()) return c.entity.trim();
    if (typeof this._lockFromDevice === "string") return this._lockFromDevice;
    return null;
  }

  _deviceResolving() {
    const c = this._config || {};
    return (
      typeof c.device === "string" &&
      c.device.trim() &&
      !(typeof c.entity === "string" && c.entity.trim()) &&
      this._lockFromDevice === undefined
    );
  }

  _title() {
    const c = this._config || {};
    if (typeof c.title === "string" && c.title.trim()) return c.title.trim();
    const states = this._hass && this._hass.states;
    if (states) {
      const lock = this._lockEntity();
      const candidates = [lock, ...this._views.map((v) => v.entity)];
      for (const id of candidates) {
        const st = id && states[id];
        if (st && st.attributes && st.attributes.friendly_name) {
          return st.attributes.friendly_name;
        }
      }
    }
    return "";
  }

  _coverUrl() {
    const c = this._config || {};
    if (this._lastCoverUrl) return this._lastCoverUrl;
    if (typeof c.image === "string" && c.image.trim()) return c.image.trim();
    return PLACEHOLDER_URL;
  }

  _activeViewEntry() {
    return (
      this._views[Math.min(this._activeView, Math.max(0, this._views.length - 1))] ||
      null
    );
  }

  /* ------------------------------------------------------------- hass */

  _afterHassUpdate() {
    if (!this._hass) return;
    this._maybeResolveDevice();
    this._updateOpenButton();
    if (this._els.titleEl) {
      const t = this._title();
      if (this._els.titleEl.textContent !== t) {
        this._els.titleEl.textContent = t;
        this._els.titleEl.hidden = !t;
      }
    }
    if (this._isLive()) {
      if (this._els.streamCard) this._els.streamCard.hass = this._hass;
      else if (this._els.streamWrap && !this._streamHadHass)
        this._mountStream().catch(() => {});
      this._updateThumbs();
    }
  }

  /** Resolve `device:` to a lock entity via the entity registry (cached). */
  async _maybeResolveDevice() {
    if (!this._deviceResolving() || this._resolvingDevice) return;
    if (!this._hass || typeof this._hass.callWS !== "function") return;
    this._resolvingDevice = true;
    try {
      const registry = await this._hass.callWS({
        type: "config/entity_registry/list"
      });
      const entry = Array.isArray(registry)
        ? registry.find(
            (e) =>
              e &&
              e.device_id === this._config.device &&
              typeof e.entity_id === "string" &&
              e.entity_id.startsWith("lock.")
          )
        : null;
      this._lockFromDevice = entry ? entry.entity_id : null;
    } catch (_err) {
      // Keep undefined so a later hass update can retry.
    }
    this._resolvingDevice = false;
    if (this._lockFromDevice !== undefined) {
      this._buildDom(); // lock button may appear/disappear
      if (this._hass) {
        if (this._els.streamCard) this._els.streamCard.hass = this._hass;
        this._updateOpenButton();
      }
    }
  }

  /* -------------------------------------------------------------- DOM */

  _buildDom() {
    if (!this._config) return;
    this._els = {}; // drop references into the previous DOM
    const root = this.shadowRoot;
    root.innerHTML = "";
    const style = h("style");
    style.textContent = CSS;
    const card = h("div", { class: "card" + (this._isLive() ? " live" : "") });
    if (this._isLive()) this._buildLive(card);
    else this._buildStatic(card);
    root.append(style, card);
  }

  _buildStatic(card) {
    const views = this._views;
    const interactive = views.length > 0 || this._hasLockConfig();

    const media = h(
      "div",
      {
        class: "media static",
        role: interactive ? "button" : null,
        tabindex: interactive ? "0" : null,
        "aria-label": interactive ? "Open live view" : null,
        onclick: interactive ? (e) => this._onMediaTap(e) : null,
        onkeydown: interactive ? (e) => this._onMediaKey(e) : null
      },
      h("img", { class: "cover", alt: "" }),
      h("div", { class: "scrim" })
    );

    this._els.coverImg = media.querySelector("img.cover");
    this._applyCover(this._els.coverImg);

    const title = h("div", { class: "title" }, this._title());
    title.hidden = !title.textContent;
    media.appendChild(title);
    this._els.titleEl = title;

    if (views.length > 0) {
      const btn = h(
        "button",
        {
          class: "icon-btn",
          title: "Refresh snapshot",
          "aria-label": "Refresh snapshot",
          onclick: (e) => {
            e.stopPropagation();
            this._onRefresh();
          }
        },
        h("span", { class: "ic", html: ICONS.refresh }),
        h("span", { class: "spin", hidden: true })
      );
      media.appendChild(btn);
      this._els.refreshBtn = btn;
    }

    if (!views.length && !this._hasLockConfig()) {
      media.appendChild(
        h(
          "div",
          { class: "empty" },
          h("div", { class: "empty-title" }, "Nothing configured yet"),
          h(
            "div",
            { class: "empty-sub" },
            "Add a door lock or camera views in the card settings."
          )
        )
      );
    }

    const toast = h("div", { class: "toast", role: "status" });
    media.appendChild(toast);
    this._els.toast = toast;

    card.appendChild(media);
    this._buildOpenButton(card);
  }

  _buildLive(card) {
    const views = this._views;

    const main = h("div", { class: "live-main" });

    // Stream is the hero. The dialog already shows the title, so the card
    // only overlays a compact Live badge (no duplicate title row).
    const streamBox = h("div", { class: "stream-box" });
    const streamWrap = h("div", { class: "stream" });
    streamBox.appendChild(streamWrap);
    this._els.streamWrap = streamWrap;
    streamBox.appendChild(
      h("div", { class: "live-badge" }, h("span", { class: "dot" }), "Live")
    );
    const toast = h("div", { class: "toast", role: "status" });
    streamBox.appendChild(toast);
    this._els.toast = toast;
    main.appendChild(streamBox);

    // View-switch strip under the stream — only when there is a choice.
    if (views.length > 1) {
      const row = h("div", { class: "views-row", "aria-label": "Camera views" });
      views.forEach((v, i) => {
        const label = v.label || deriveLabel(v.entity);
        const st = this._hass && this._hass.states && this._hass.states[v.entity];
        const pic = st && st.attributes && st.attributes.entity_picture;
        const thumb = h("div", { class: "thumb" });
        if (pic) thumb.appendChild(h("img", { src: pic, alt: "" }));
        else thumb.appendChild(h("span", { class: "thumb-ic", html: ICONS.video }));
        row.appendChild(
          h(
            "button",
            {
              class: "view" + (i === this._activeView ? " active" : ""),
              title: label,
              "aria-label": "Show " + label,
              onclick: (e) => {
                e.stopPropagation();
                this._switchView(i);
              }
            },
            thumb,
            h("span", { class: "view-label" }, label)
          )
        );
      });
      main.appendChild(row);
      this._els.viewsRow = row;
    }

    this._buildOpenButton(main);
    card.appendChild(main);

    this._mountStream().catch(() => {});
  }

  /** Build the live-stream card element for a view, or null.
   *  HA registers hui-* elements lazily: on a dashboard that never rendered
   *  a picture-glance card, `customElements.get` misses. In that case go
   *  through window.loadCardHelpers() (the pattern browser_mod itself uses),
   *  which triggers the lazy import. */
  async _createStreamCard(entity) {
    const config = {
      type: "picture-glance",
      camera_image: entity,
      camera_view: "live",
      aspect_ratio: "16:9",
      entities: []
    };

    // 1) Element already registered -> plain synchronous path.
    if (customElements.get("hui-picture-glance-card")) {
      try {
        const cam = document.createElement("hui-picture-glance-card");
        cam.setConfig(config);
        return cam;
      } catch (_err) {
        return null;
      }
    }

    // 2) Lazy registration -> let HA's card helpers create it.
    if (typeof window.loadCardHelpers === "function") {
      try {
        const helpers = await window.loadCardHelpers();
        let cam = helpers.createCardElement(config);
        if (cam && typeof cam.then === "function") cam = await cam;
        if (cam && cam.tagName !== "HUI-ERROR-CARD") return cam;
      } catch (_err) {
        /* fall through */
      }
    }

    return null;
  }

  /** Create (or re-create) the live stream element for the active view.
   *  Async: element creation may need the lazy card-helpers import. */
  async _mountStream() {
    const wrap = this._els.streamWrap;
    if (!wrap) return;
    wrap.innerHTML = "";
    this._els.streamCard = null;
    this._streamHadHass = Boolean(this._hass);

    const v = this._activeViewEntry();
    if (!v) {
      wrap.appendChild(h("img", { class: "cover", src: PLACEHOLDER_URL, alt: "" }));
      wrap.appendChild(
        h(
          "div",
          { class: "empty" },
          h("div", { class: "empty-title" }, "No cameras configured"),
          h("div", { class: "empty-sub" }, "Add camera views in the card settings.")
        )
      );
      return;
    }

    const cam = await this._createStreamCard(v.entity);

    // Race guard: the view may have switched, or the DOM may have been
    // rebuilt (setConfig/editor), while we awaited the element. If so, a
    // newer render owns the stream area — do not append stale content.
    const current = this._activeViewEntry();
    if (this._els.streamWrap !== wrap || !current || current.entity !== v.entity) {
      return;
    }

    if (cam) {
      try {
        if (this._hass) cam.hass = this._hass;
        wrap.appendChild(cam);
        this._els.streamCard = cam;
        return;
      } catch (_err) {
        /* fall through to the still-image fallback */
      }
    }

    // Fallback: latest HA snapshot of the camera, else the placeholder.
    const st = this._hass && this._hass.states && this._hass.states[v.entity];
    const pic = st && st.attributes && st.attributes.entity_picture;
    wrap.appendChild(
      h("img", {
        class: "cover",
        src: pic ? cacheBust(pic) : PLACEHOLDER_URL,
        alt: ""
      })
    );
  }

  _switchView(index) {
    if (index === this._activeView || !this._views[index]) return;
    this._activeView = index;
    if (this._els.viewsRow) {
      Array.from(this._els.viewsRow.children).forEach((b, j) =>
        b.classList.toggle("active", j === index)
      );
    }
    this._mountStream().catch(() => {});
  }

  _updateThumbs() {
    if (!this._els.viewsRow || !this._hass) return;
    const states = this._hass.states || {};
    Array.from(this._els.viewsRow.children).forEach((btn, i) => {
      const v = this._views[i];
      if (!v) return;
      const thumb = btn.querySelector(".thumb");
      const pic =
        states[v.entity] &&
        states[v.entity].attributes &&
        states[v.entity].attributes.entity_picture;
      const img = thumb && thumb.querySelector("img");
      if (pic) {
        if (img) {
          if (img.getAttribute("src") !== pic) img.src = pic;
        } else if (thumb) {
          thumb.innerHTML = "";
          thumb.appendChild(h("img", { src: pic, alt: "" }));
        }
      }
    });
  }

  _buildOpenButton(container) {
    const lock = this._lockEntity();
    const resolving = this._deviceResolving();
    this._els.openBtn = null;
    if (!lock && !resolving) return;
    const btn = h(
      "button",
      {
        class: "open",
        onclick: (e) => {
          e.stopPropagation();
          this._onOpen();
        }
      },
      h("span", { class: "open-ic", html: ICONS.unlock }),
      h("span", { class: "open-spin", hidden: true }),
      h("span", { class: "open-text" }, "Open")
    );
    container.appendChild(btn);
    this._els.openBtn = btn;
    this._updateOpenButton();
  }

  _updateOpenButton() {
    const btn = this._els.openBtn;
    if (!btn || !this._config) return;
    const text =
      (typeof this._config.open_text === "string" &&
        this._config.open_text.trim()) ||
      "Open";
    btn.querySelector(".open-text").textContent = text;

    const lock = this._lockEntity();
    const st = this._hass && this._hass.states && this._hass.states[lock];
    const unavailable =
      Boolean(st) && (st.state === "unavailable" || st.state === "unknown");
    const resolving = this._deviceResolving() && this._resolvingDevice;

    btn.disabled = Boolean(this._opening || unavailable || resolving || !lock);
    btn.classList.toggle("success", this._openSuccess && !this._opening);
    btn.setAttribute(
      "aria-label",
      lock ? text + " (" + lock + ")" : text
    );

    const ic = btn.querySelector(".open-ic");
    const spin = btn.querySelector(".open-spin");
    ic.hidden = this._opening || this._openSuccess;
    spin.hidden = !this._opening;
    ic.innerHTML = this._openSuccess ? ICONS.check : ICONS.unlock;
  }

  _applyCover(img) {
    if (!img) return;
    const url = this._coverUrl();
    const done = () => img.classList.remove("dim");
    img.classList.add("dim");
    img.onload = done;
    img.onerror = () => {
      if (img.src !== PLACEHOLDER_URL) {
        this._lastCoverUrl = null; // bad/missing file -> back to placeholder
        img.src = PLACEHOLDER_URL;
      } else {
        done();
      }
    };
    img.src = url;
  }

  /* ---------------------------------------------------------- actions */

  _onMediaTap(_e) {
    this._openPopup();
  }

  _onMediaKey(e) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      this._openPopup();
    }
  }

  async _openPopup() {
    if (!this._hass) return;
    const hasViews = this._views.length > 0;
    if (!hasViews && !this._hasLockConfig()) return; // nothing to show

    const title = this._title();
    const content = Object.assign({}, this._config, {
      type: "custom:" + CARD_TAG,
      live: true
    });

    // browser_mod 3.x registers `browser_mod/popup` (not `show_popup`).
    // Only pass fields from its schema: unknown keys risk rejection.
    // initial_style "wide" = browser_mod's built-in 90vw dialog style; the
    // default 580px dialog is too narrow for a live stream.
    const services = this._hass.services || {};
    const available = Boolean(
      services.browser_mod && services.browser_mod.popup
    );
    if (available) {
      try {
        await this._hass.callService("browser_mod", "popup", {
          title: title || "",
          content,
          initial_style: "wide"
        });
        return;
      } catch (_err) {
        /* fall through to more-info */
      }
    }
    // Fallback: native more-info for the active camera (or the lock).
    const target =
      (this._activeViewEntry() && this._activeViewEntry().entity) ||
      this._lockEntity();
    if (!target) return;
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId: target },
        bubbles: true,
        composed: true
      })
    );
  }

  async _onRefresh() {
    if (this._refreshing || !this._views.length || !this._hass) return;
    const view = this._activeViewEntry() || this._views[0];
    const c = this._config;
    const filename =
      (typeof c.snapshot_file === "string" && c.snapshot_file.trim()) ||
      deriveFilename(view.entity);

    this._refreshing = true;
    this._setRefreshBusy(true);
    try {
      await this._hass.callService(
        "hikcentral_district",
        "refresh_snapshot",
        { entity_id: view.entity, filename }
      );
      const base =
        (typeof c.image === "string" && c.image.trim()) ||
        SNAPSHOT_BASE + filename;
      this._lastCoverUrl = cacheBust(base);
      this._applyCover(this._els.coverImg);
    } catch (_err) {
      this._toast("Couldn't refresh snapshot");
    } finally {
      this._refreshing = false;
      this._setRefreshBusy(false);
    }
  }

  _setRefreshBusy(busy) {
    const btn = this._els.refreshBtn;
    if (!btn) return;
    btn.disabled = busy;
    const ic = btn.querySelector(".ic");
    const spin = btn.querySelector(".spin");
    if (ic) ic.hidden = busy;
    if (spin) spin.hidden = !busy;
  }

  async _onOpen() {
    const lock = this._lockEntity();
    if (!lock || this._opening || !this._hass) return;
    this._opening = true;
    this._updateOpenButton();
    try {
      await this._hass.callService("lock", "open", { entity_id: lock });
      this._openSuccess = true;
      this._updateOpenButton();
      clearTimeout(this._successTimer);
      this._successTimer = setTimeout(() => {
        this._openSuccess = false;
        this._updateOpenButton();
      }, 1400);
    } catch (_err) {
      this._toast("Couldn't open the door");
    } finally {
      this._opening = false;
      this._updateOpenButton();
    }
  }

  _toast(message) {
    const t = this._els.toast;
    if (!t) return;
    t.textContent = message;
    t.classList.add("show");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => t.classList.remove("show"), 3500);
  }
}

/* ---------------------------------------------------------------- editor */

class DistrictIntercomCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._built = false;
    this._inputs = {};
  }

  setConfig(config) {
    this._config = config || {};
    if (!this._built) {
      this._build();
      this._built = true;
    }
    this._populate();
  }

  _build() {
    const style = h("style");
    style.textContent = CSS;

    const mk = (name, label, opts) => {
      const input = h("input", {
        type: "text",
        placeholder: (opts && opts.placeholder) || "",
        oninput: () => this._changed()
      });
      const field = h(
        "div",
        { class: "field" },
        h("label", null, label),
        input
      );
      if (opts && opts.hint)
        field.appendChild(h("div", { class: "hint" }, opts.hint));
      this._inputs[name] = input;
      return field;
    };

    const views = h("textarea", {
      rows: "4",
      placeholder: "camera.gate_1\ncamera.gate_2 | Gate 2",
      oninput: () => this._changed()
    });
    this._inputs.views = views;
    const viewsField = h(
      "div",
      { class: "field" },
      h("label", null, "Camera views (one per line)"),
      views,
      h(
        "div",
        { class: "hint" },
        "One camera entity per line. Optional label after a pipe: camera.x | Label"
      )
    );

    const editor = h(
      "div",
      { class: "editor" },
      mk("title", "Title", { placeholder: "Main Gate" }),
      mk("entity", "Lock entity", { placeholder: "lock.front_door" }),
      viewsField,
      mk("image", "Cover image", {
        placeholder: "/local/snapshots/gate.jpg",
        hint: "Optional. Shown until a snapshot refresh replaces it."
      }),
      mk("snapshot_file", "Snapshot file", {
        placeholder: "gate.jpg",
        hint: "Optional. Defaults to the first view's entity name + .jpg."
      }),
      mk("open_text", "Open button text", { placeholder: "Open" }),
      h(
        "details",
        null,
        h("summary", null, "Advanced"),
        mk("device", "Device ID (instead of lock entity)", {
          placeholder: "1a2b3c4d…",
          hint: "The lock entity is looked up from the device registry."
        })
      )
    );

    this.shadowRoot.append(style, editor);
  }

  _populate() {
    const c = this._config || {};
    const set = (name, value) => {
      const input = this._inputs[name];
      if (input) input.value = typeof value === "string" ? value : "";
    };
    set("title", c.title);
    set("entity", c.entity);
    set("image", c.image);
    set("snapshot_file", c.snapshot_file);
    set("open_text", c.open_text);
    set("device", c.device);

    const views = Array.isArray(c.views) ? c.views : [];
    this._inputs.views.value = views
      .map((v) => {
        if (typeof v === "string") return v;
        if (v && typeof v === "object" && v.entity) {
          return v.label ? v.entity + " | " + v.label : v.entity;
        }
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }

  _changed() {
    const val = (name) => {
      const input = this._inputs[name];
      return input ? input.value.trim() : "";
    };
    const views = this._inputs.views.value
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map((line) => {
        const i = line.indexOf("|");
        if (i === -1) return line;
        const entity = line.slice(0, i).trim();
        const label = line.slice(i + 1).trim();
        if (!entity) return null;
        return label ? { entity, label } : entity;
      })
      .filter(Boolean);

    // Start from the current config so unknown/extra keys survive, always
    // (re-)assert the type (HA rejects config-changed without it and drops
    // to the YAML editor), set/delete the managed fields, and always emit
    // views (empty textarea -> []).
    const config = { ...(this._config || {}) };
    config.type = "custom:" + CARD_TAG;
    for (const key of ["title", "entity", "image", "snapshot_file", "open_text", "device"]) {
      const v = val(key);
      if (v) config[key] = v;
      else delete config[key];
    }
    config.views = views;

    this._config = config;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true
      })
    );
  }
}

/* ------------------------------------------------------------------ boot */

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, DistrictIntercomCard);
}
if (!customElements.get(EDITOR_TAG)) {
  customElements.define(EDITOR_TAG, DistrictIntercomCardEditor);
}

/* ------------------------------------------------- card picker entry */

// The HA card picker lists ONLY types present in window.customCards
// (home-assistant/frontend src/data/lovelace_custom_cards.ts). Always push
// onto the existing array — never reassign — the frontend captures the
// array reference at load. Dedupe guards a double module eval (stale +
// fresh resource URL registered side by side).
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

console.info(
  `%c district-intercom-card %c v${VERSION} `,
  "color:#fff;background:#262c3a;font-weight:700;border-radius:4px 0 0 4px;padding:2px 6px",
  "color:#262c3a;background:#e8eaef;border-radius:0 4px 4px 0;padding:2px 6px"
);
