#!/usr/bin/env bash
# HikCentral District — one-command installer for an EXISTING Home Assistant.
#
# Installs everything the "district" experience needs into a HA config dir:
#   1. the hikcentral_district integration (from THIS checkout — no HACS UI
#      round-trip needed; HACS users may skip and keep HACS-managed updates)
#   2. browser_mod v3.2.1 (popups) straight from the GitHub zipball
#   3. the district dashboard: .storage/lovelace.district, GENERATED from
#      dashboards/cameras.json (gitignored; copy from cameras.example.json)
#      + the dashboard entry + /browser_mod.js resource
#   4. (optional, --with-snapshot-automation) the 10-min snapshot refresh:
#      scripts/refresh_district_snapshots.py + shell_command + automation
#
# Merge-only .storage semantics: existing config entries / resources /
# dashboards are never modified or dropped. browser_mod config entry carries
# created_at/modified_at/discovery_keys/subentries/version=2/minor_version=1 —
# without those fields HA crash-loops ("Migration handler not found").
#
# Usage:
#   ./install.sh --config /path/to/ha/config [options]
#   HA_CONFIG=/path/to/config ./install.sh [options]
#
# Options:
#   --config DIR                HA configuration directory (default: auto)
#   --check                     dry run: report, change nothing
#   --stage-only                write artifacts to .install-staging/ inside the
#                               config dir and stop — apply manually later
#   --with-snapshot-automation  patch configuration.yaml/automations.yaml
#   --no-dashboard              skip the dashboard + browser_mod resource
#   --update-components         replace an EXISTING component dir when its
#                               version differs (default: warn and skip)
#   -y, --yes                   skip confirmation
#
# HikCentral credentials (for the seeded config entry; leave unset to skip
# seeding and configure via the HA UI instead):
#   HIK_URL / HIK_USER / HIK_PASS   env vars, or interactive prompt on a TTY
#
# After install: restart Home Assistant, finish onboarding on fresh
# instances, open <ha>/district. See README.md for the full path including
# the optional go2rtc live-stream sidecar (deploy/).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BROWSER_MOD_REPO="thomasloven/hass-browser_mod"
BROWSER_MOD_VERSION="v3.2.1"

CONFIG_DIR=""
DRY_RUN=0 STAGE_ONLY=0 WITH_SNAPSHOTS=0 NO_DASHBOARD=0 ASSUME_YES=0 UPDATE_COMPONENTS=0

log()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mFATAL:\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

CONFIG_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG_DIR="${2:?--config needs a directory}"; shift 2 ;;
    --check)                    DRY_RUN=1; shift ;;
    --stage-only)               STAGE_ONLY=1; shift ;;
    --with-snapshot-automation) WITH_SNAPSHOTS=1; shift ;;
    --no-dashboard)             NO_DASHBOARD=1; shift ;;
    --update-components)        UPDATE_COMPONENTS=1; shift ;;
    --yes|-y)                   ASSUME_YES=1; shift ;;
    -h|--help)                  usage 0 ;;
    -*) die "unknown option: $1" ;;
    *) CONFIG_DIR="$1"; shift ;;
  esac
done

require_cmd() { command -v "$1" >/dev/null 2>&1 || die "$2"; }

# ------------------------------------------------------------- config ------
detect_config_dir() {
  if [[ -n "$CONFIG_DIR" ]]; then
    [[ -d "$CONFIG_DIR" ]] || die "--config dir '$CONFIG_DIR' does not exist"
    return
  fi
  if [[ -n "${HA_CONFIG:-}" ]]; then
    CONFIG_DIR="$HA_CONFIG"
  elif [[ -d "/config" && -f "/config/configuration.yaml" ]]; then
    CONFIG_DIR="/config"     # running inside the HA container / SSH add-on
  elif [[ -d "$SCRIPT_DIR/config" ]]; then
    CONFIG_DIR="$SCRIPT_DIR/config"   # deploy/docker-compose.example.yaml layout
  elif [[ -d "$SCRIPT_DIR/core" ]]; then
    CONFIG_DIR="$SCRIPT_DIR/core"
  else
    die "cannot auto-detect the HA config dir — pass --config /path/to/config (or set HA_CONFIG)"
  fi
  info "auto-detected HA config dir: $CONFIG_DIR"
}

# ------------------------------------------------------------ component ----
component_version() {
  grep -o '"version": *"[^"]*"' "$1/manifest.json" 2>/dev/null | head -1 | sed 's/.*"\(.*\)"$/\1/'
}

# copy_component <src-dir> <dest-dir> <name>  — version-checked, idempotent
copy_component() {
  local src="$1" dest="$2" name="$3"
  local want; want="$(component_version "$src")"

  if (( STAGE_ONLY )) && [[ -d "$dest" ]]; then
    info "SKIP $name — --stage-only never touches components (installed: $(component_version "$dest"))"
    return 0
  fi
  if [[ -d "$dest" ]] && [[ "$(component_version "$dest")" == "$want" ]]; then
    info "SKIP $name — already at $want"
    return 0
  fi
  if [[ -d "$dest" ]]; then
    local cur; cur="$(component_version "$dest")"
    if (( ! UPDATE_COMPONENTS )); then
      warn "$name: installed '${cur:-unknown}' != bundled '$want' — leaving existing dir untouched (HACS owns updates); pass --update-components to force"
      return 0
    fi
    (( DRY_RUN )) && { info "WOULD replace $name '${cur}' -> '$want'"; return 0; }
  fi
  (( DRY_RUN )) && { info "WOULD install $name $want -> $dest"; return 0; }

  log "installing $name $want -> $dest"
  local tmp="$dest.new"
  rm -rf "$tmp"
  mkdir -p "$tmp"
  (cd "$src" && tar cf - --exclude='__pycache__' --exclude='*.pyc' .) | (cd "$tmp" && tar xf -)
  if [[ -d "$dest" ]]; then
    local bak="${dest}.bak-$(date +%Y%m%d-%H%M%S)"
    mv "$dest" "$bak"
    info "previous version kept at $bak"
  fi
  mv "$tmp" "$dest"
}

# ---------------------------------------------------------- browser_mod ----
install_browser_mod() {
  local dest="$CONFIG_DIR/custom_components/browser_mod"
  local ver="${BROWSER_MOD_VERSION#v}"

  if (( STAGE_ONLY )) && [[ -d "$dest" ]]; then
    info "SKIP browser_mod — --stage-only never touches components (installed: $(component_version "$dest"))"
    return 0
  fi
  if [[ -d "$dest" ]] && grep -q "\"version\": *\"$ver\"" "$dest/manifest.json" 2>/dev/null; then
    info "SKIP browser_mod — already at $ver"
    return 0
  fi
  if [[ -d "$dest" ]]; then
    local cur; cur="$(component_version "$dest")"
    if (( ! UPDATE_COMPONENTS )); then
      warn "browser_mod: installed '${cur:-unknown}' != pinned $ver — leaving existing dir untouched; pass --update-components to force"
      return 0
    fi
    (( DRY_RUN )) && { info "WOULD replace browser_mod '${cur}' -> $ver"; return 0; }
  fi
  (( DRY_RUN )) && { info "WOULD install browser_mod $ver -> $dest (GitHub zipball)"; return 0; }

  log "downloading browser_mod $BROWSER_MOD_VERSION"
  local zip="/tmp/browser_mod-$ver.zip"
  curl -fsSL --retry 3 -o "$zip" \
    "https://github.com/$BROWSER_MOD_REPO/archive/refs/tags/$BROWSER_MOD_VERSION.zip"
  mkdir -p "$CONFIG_DIR/custom_components"
  python3 - "$zip" "custom_components/browser_mod" "$CONFIG_DIR/custom_components" <<'PY'
import os, shutil, sys, tempfile, zipfile
zip_path, subdir, cc_dir = sys.argv[1], sys.argv[2], sys.argv[3]
prefix = subdir.strip("/") + "/"
z = zipfile.ZipFile(zip_path)
members = [n for n in z.namelist()
           if "/" in n and (n.split("/", 1)[1].startswith(prefix))
           and "__pycache__" not in n and not n.endswith(".pyc")]
if not members:
    sys.exit(f"{subdir!r} not found in zipball")
tmp = tempfile.mkdtemp(dir=cc_dir)
try:
    for n in members:
        rel = n.split("/", 1)[1]
        out = os.path.join(tmp, rel)
        if n.endswith("/"):
            os.makedirs(out, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as src, open(out, "wb") as fh:
                shutil.copyfileobj(src, fh)
    dest = os.path.join(cc_dir, "browser_mod")
    if os.path.exists(dest):
        shutil.rmtree(dest)  # replaced wholesale from the pinned release
    shutil.move(os.path.join(tmp, subdir.strip("/")), dest)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print(f"    browser_mod files -> {dest}")
PY
}

# ------------------------------------------------------------- storage -----
stage_storage() {
  (( DRY_RUN )) && { info "WOULD stage .storage (config entry, resource, dashboard, lovelace.district)"; return 0; }
  log "staging .storage files (merge-only) in $CONFIG_DIR/.install-staging"
  local district_json=""
  if [[ -f "$SCRIPT_DIR/dashboards/cameras.json" ]]; then
    district_json=$(mktemp)
    python3 "$SCRIPT_DIR/dashboards/generate_district.py" --create "$district_json" \
      --cameras "$SCRIPT_DIR/dashboards/cameras.json" >/dev/null || district_json=""
  fi
  (( ${#district_json} )) || info "no dashboards/cameras.json -> dashboard staging skipped"
  python3 - "$CONFIG_DIR" "$district_json" <<'PY'
import copy, json, os, sys
from datetime import datetime, timezone
from uuid import uuid4

config_dir, district_json = sys.argv[1], sys.argv[2]
storage_dir = os.path.join(config_dir, ".storage")
stage_dir = os.path.join(config_dir, ".install-staging")
os.makedirs(stage_dir, exist_ok=True)
os.chmod(stage_dir, 0o700)

def now():
    return datetime.now(timezone.utc).isoformat()

def load(name, default):
    try:
        with open(os.path.join(storage_dir, name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return copy.deepcopy(default)

def envelope(key, data):
    return {"version": 1, "minor_version": 1, "key": key, "data": data}

def save(name, doc):
    with open(os.path.join(stage_dir, name), "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")

# --- core.config_entries: browser_mod (+ hikcentral_district if creds) ----
doc = load("core.config_entries", envelope("core.config_entries", {"entries": []}))
entries = doc.setdefault("data", {}).setdefault("entries", [])

def add_entry(domain, title, version, data, options):
    if any(e["domain"] == domain for e in entries):
        print(f"    SKIP config entry {domain} (already present)")
        return
    # All fields required — HA crash-loops without created_at & friends.
    entries.append({
        "created_at": now(), "data": data, "disabled_by": None,
        "discovery_keys": {}, "domain": domain, "entry_id": uuid4().hex,
        "minor_version": 1, "modified_at": now(), "options": options,
        "pref_disable_new_entities": False, "pref_disable_polling": False,
        "source": "user", "subentries": [], "title": title,
        "unique_id": None, "version": version,
    })
    print(f"    + config entry {domain}")

add_entry("browser_mod", "Browser Mod", 2, {}, {})
url, user, password = (os.environ.get(f"HIK_{k}") for k in ("URL", "USER", "PASS"))
if url and user and password:
    add_entry(
        "hikcentral_district", "HikCentral District", 1,
        {"url": url, "username": user, "password": password,
         "scan_interval": 30, "verify_ssl": False},
        {"live_snapshots": True,
         "stream_url_template": "rtsp://127.0.0.1:18556/hik_cam_{id}"},
    )
else:
    print("    SKIP hikcentral_district config entry (no HIK_URL/HIK_USER/HIK_PASS — configure in the HA UI)")
save("core.config_entries", doc)

# --- lovelace_resources + dashboards + the dashboard itself ---------------
doc = load("lovelace_resources", envelope("lovelace_resources", {"items": []}))
items = doc.setdefault("data", {}).setdefault("items", [])
if not any(str(i.get("url", "")).startswith("/browser_mod.js") for i in items):
    items.append({"url": "/browser_mod.js", "type": "module", "id": uuid4().hex})
    print("    + lovelace_resources /browser_mod.js")
else:
    print("    SKIP lovelace_resources /browser_mod.js (already present)")
save("lovelace_resources", doc)

doc = load("lovelace_dashboards", envelope("lovelace_dashboards", {"items": []}))
items = doc.setdefault("data", {}).setdefault("items", [])
if not any(i.get("id") == "district" for i in items):
    items.append({"id": "district", "mode": "storage",
                  "title": "Район: замки и въезды", "icon": "mdi:shield-home",
                  "url_path": "district", "show_in_sidebar": True,
                  "require_admin": False})
    print("    + lovelace_dashboards district")
else:
    print("    SKIP lovelace_dashboards district (already present)")
save("lovelace_dashboards", doc)

if district_json and os.path.isfile(district_json):
    with open(district_json) as f:
        save("lovelace.district", json.load(f))
    print("    lovelace.district generated from cameras.json")
PY
}

apply_storage() {
  local name changed=0
  local bak="$CONFIG_DIR/.install-staging/backups-$(date +%Y%m%d-%H%M%S)"
  for name in core.config_entries lovelace_resources lovelace_dashboards lovelace.district; do
    (( DRY_RUN )) && { info "WOULD apply $name -> $CONFIG_DIR/.storage/"; continue; }
    [[ -f "$CONFIG_DIR/.install-staging/$name" ]] || continue
    if ! cmp -s "$CONFIG_DIR/.install-staging/$name" "$CONFIG_DIR/.storage/$name"; then
      log "applying $name"
      mkdir -p "$CONFIG_DIR/.storage" "$bak"
      [[ -f "$CONFIG_DIR/.storage/$name" ]] && cp "$CONFIG_DIR/.storage/$name" "$bak/$name"
      cp "$CONFIG_DIR/.install-staging/$name" "$CONFIG_DIR/.storage/$name"
      changed=1
    else
      info "SKIP $name — already matches staging"
    fi
  done
  if (( changed )); then
    warn ".storage changed — RESTART Home Assistant to load it"
  fi
}

# ------------------------------------------------- snapshot automation -----
snapshot_automation() {
  local cfg="$CONFIG_DIR/configuration.yaml" aut="$CONFIG_DIR/automations.yaml"
  local script_src="$SCRIPT_DIR/scripts/refresh_district_snapshots.py"
  local script_dst="$CONFIG_DIR/scripts/refresh_district_snapshots.py"

  (( DRY_RUN )) && { info "WOULD copy the snapshot script + patch configuration.yaml/automations.yaml"; return 0; }

  mkdir -p "$CONFIG_DIR/scripts" "$CONFIG_DIR/www/snapshots"
  if [[ -f "$script_dst" ]] && cmp -s "$script_src" "$script_dst"; then
    info "SKIP snapshot script (identical copy present)"
  else
    log "copying scripts/refresh_district_snapshots.py -> $CONFIG_DIR/scripts/"
    cp "$script_src" "$script_dst"
  fi

  if [[ ! -f "$cfg" ]]; then
    log "creating minimal configuration.yaml"
    cat > "$cfg" <<'YAML'
# Loads default set of integrations. Do not remove.
default_config:

automation: !include automations.yaml
script: !include scripts.yaml
scene: !include scenes.yaml

# Static jpg snapshots for the district dashboard camera cards.
shell_command:
  refresh_district_snapshots: python3 /config/scripts/refresh_district_snapshots.py
YAML
    : > "$CONFIG_DIR/scripts.yaml"
    : > "$CONFIG_DIR/scenes.yaml"
  elif grep -q "refresh_district_snapshots" "$cfg"; then
    info "SKIP configuration.yaml shell_command (already present)"
  elif grep -qE "^shell_command:" "$cfg"; then
    die "configuration.yaml has a shell_command: block without our key — add refresh_district_snapshots manually"
  else
    log "appending shell_command block to configuration.yaml"
    cat >> "$cfg" <<'YAML'

# Static jpg snapshots for the district dashboard camera cards.
shell_command:
  refresh_district_snapshots: python3 /config/scripts/refresh_district_snapshots.py
YAML
  fi

  [[ -f "$aut" ]] || : > "$aut"
  if grep -q "district_snapshots_refresh_20260816" "$aut"; then
    info "SKIP automations.yaml (district snapshots refresh already present)"
  else
    log "appending 'district snapshots refresh' automation"
    cat >> "$aut" <<'YAML'
# Static jpg snapshots for the district dashboard camera cards (10 min)
- id: district_snapshots_refresh_20260816
  alias: district snapshots refresh
  description: Refreshes /config/www/snapshots/*.jpg used by the district dashboard
  trigger:
  - platform: time_pattern
    minutes: /10
  condition: []
  action:
  - service: shell_command.refresh_district_snapshots
  mode: single
YAML
  fi
}

# --------------------------------------------------------------- main ------
require_cmd python3 "python3 is required"
require_cmd curl "curl is required"
detect_config_dir
[[ -f "$CONFIG_DIR/configuration.yaml" || -d "$CONFIG_DIR/.storage" ]] \
  || warn "'$CONFIG_DIR' has no configuration.yaml/.storage — is it really a HA config dir?"
(( DRY_RUN )) && log "CHECK MODE (dry run — nothing will be written)"

if (( ! (DRY_RUN || STAGE_ONLY) && ! ASSUME_YES )); then
  warn "about to modify Home Assistant config at: $CONFIG_DIR"
  read -r -p "Continue? [y/N] " reply
  [[ "$reply" == y || "$reply" == Y ]] || die "aborted"
fi

copy_component "$SCRIPT_DIR/custom_components/hikcentral_district" \
               "$CONFIG_DIR/custom_components/hikcentral_district" \
               "hikcentral_district"
install_browser_mod

if (( ! NO_DASHBOARD )); then
  stage_storage
  if (( STAGE_ONLY )); then
    log "stage-only: artifacts in $CONFIG_DIR/.install-staging — copy them into .storage/ manually, then restart HA"
    exit 0
  fi
  apply_storage
else
  info "--no-dashboard: skipping .storage staging"
fi

if (( WITH_SNAPSHOTS )); then
  snapshot_automation
fi

log "done. Next steps:"
echo "  1. restart Home Assistant"
echo "  2. fresh instance: finish onboarding at http://<host>:8123"
echo "  3. configure hikcentral_district (Settings > Devices > Add Integration"
echo "     'HikCentral District') unless the installer seeded it from HIK_* env"
echo "  4. open http://<host>:8123/district — if popups do not open, enable"
echo "     'Register' once in the Browser Mod panel"
echo "  5. live streams (optional): see deploy/ for the go2rtc sidecar"
