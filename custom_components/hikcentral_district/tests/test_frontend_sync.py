"""Test frontend sync — JS copy into www/ + Lovelace resource ?v= upkeep."""

from types import SimpleNamespace

from hikcentral_district import (
    FRONTEND_JS_NAME,
    FRONTEND_RESOURCE_URL_BASE,
    async_sync_frontend_resource,
    sync_frontend_js,
)


def _config_path(tmp_path):
    """A hass.config.path replacement rooted at tmp_path/'config'."""
    return lambda *parts: str(tmp_path.joinpath("config", *parts))


class TestSyncFrontendJs:
    """Test the module-level sync_frontend_js helper."""

    def test_copies_when_dest_missing(self, hass, tmp_path):
        """Missing destination: file is copied and True returned."""
        src = tmp_path / "card.js"
        src.write_text("console.log('v1');")
        hass.config.path = _config_path(tmp_path)

        assert sync_frontend_js(hass, src=src) is True

        dest = tmp_path / "config" / "www" / "district" / FRONTEND_JS_NAME
        assert dest.read_text() == "console.log('v1');"
        # Atomic write leaves no temp files behind
        assert not list(dest.parent.glob(".*.tmp"))

    def test_skips_when_identical(self, hass, tmp_path):
        """Identical destination content: nothing written, False returned."""
        src = tmp_path / "card.js"
        src.write_text("console.log('v1');")
        hass.config.path = _config_path(tmp_path)

        assert sync_frontend_js(hass, src=src) is True
        assert sync_frontend_js(hass, src=src) is False

    def test_overwrites_when_changed(self, hass, tmp_path):
        """Changed source content replaces the destination, True returned."""
        src = tmp_path / "card.js"
        src.write_text("console.log('v1');")
        hass.config.path = _config_path(tmp_path)

        assert sync_frontend_js(hass, src=src) is True

        src.write_text("console.log('v2');")
        assert sync_frontend_js(hass, src=src) is True

        dest = tmp_path / "config" / "www" / "district" / FRONTEND_JS_NAME
        assert dest.read_text() == "console.log('v2');"

    def test_source_missing_returns_false(self, hass, tmp_path):
        """Missing source: warning path — False returned, nothing written."""
        hass.config.path = _config_path(tmp_path)

        assert sync_frontend_js(hass, src=tmp_path / "does-not-exist.js") is False

        dest = tmp_path / "config" / "www" / "district" / FRONTEND_JS_NAME
        assert not dest.exists()

    def test_default_src_missing_returns_false(self, hass, tmp_path, monkeypatch):
        """Default package frontend/ path absent: graceful False (no raise)."""
        import hikcentral_district as integration

        # Point the package at an empty dir so the default src cannot exist.
        monkeypatch.setattr(
            integration, "__file__", str(tmp_path / "pkg" / "__init__.py")
        )
        hass.config.path = _config_path(tmp_path)

        assert sync_frontend_js(hass) is False

    def test_default_src_copies_from_package_frontend(self, hass, tmp_path, monkeypatch):
        """Default src resolves to <package>/frontend/district-intercom-card.js."""
        import hikcentral_district as integration

        pkg = tmp_path / "pkg"
        (pkg / "frontend").mkdir(parents=True)
        (pkg / "frontend" / FRONTEND_JS_NAME).write_text("card-js")
        monkeypatch.setattr(integration, "__file__", str(pkg / "__init__.py"))
        hass.config.path = _config_path(tmp_path)

        assert sync_frontend_js(hass) is True

        dest = tmp_path / "config" / "www" / "district" / FRONTEND_JS_NAME
        assert dest.read_text() == "card-js"


# ---------------------------------------------------------------------
# async_sync_frontend_resource — Lovelace resource ?v= cache-buster
# ---------------------------------------------------------------------


class FakeResourceCollection:
    """Minimal stand-in for lovelace ResourceStorageCollection (storage mode)."""

    def __init__(self, items=None):
        self.items = list(items or [])
        self.created = []
        self.updated = []

    def async_items(self):
        return self.items

    async def async_create_item(self, data):
        self.created.append(data)
        item = {"id": f"new-{len(self.created)}", **data}
        self.items.append(item)
        return item

    async def async_update_item(self, item_id, updates):
        self.updated.append((item_id, updates))
        for item in self.items:
            if item.get("id") == item_id:
                item.update(updates)
                return item
        raise KeyError(item_id)


class FakeYamlCollection:
    """Read-only stand-in for ResourceYAMLCollection (YAML mode)."""

    def __init__(self, items=None):
        self.items = list(items or [])

    def async_items(self):
        return self.items


def _fake_package_version(tmp_path, monkeypatch, version="9.9.9"):
    """Point the package __file__ at a tmp dir whose manifest.json has `version`."""
    import hikcentral_district as integration

    pkg = tmp_path / "pkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "manifest.json").write_text(f'{{"version": "{version}"}}')
    monkeypatch.setattr(integration, "__file__", str(pkg / "__init__.py"))
    return version


class TestSyncFrontendResource:
    """Test async_sync_frontend_resource — merge-only ?v= maintenance."""

    async def test_updates_stale_resource_url(self, hass, tmp_path, monkeypatch):
        """A registered resource with a stale ?v= gets its URL updated in place."""
        version = _fake_package_version(tmp_path, monkeypatch, "0.6.4")
        collection = FakeResourceCollection(
            [
                {
                    "id": "r1",
                    "url": f"{FRONTEND_RESOURCE_URL_BASE}?v=0.5.0",
                    "type": "module",
                },
                {"id": "r2", "url": "/local/other-card.js?v=1", "type": "module"},
            ]
        )
        hass.data["lovelace"] = SimpleNamespace(resources=collection)

        assert await async_sync_frontend_resource(hass) is True

        desired = f"{FRONTEND_RESOURCE_URL_BASE}?v={version}"
        assert collection.updated == [("r1", {"url": desired})]
        assert collection.created == []
        # URL bumped, resource type kept, unrelated resources untouched
        assert collection.items[0]["url"] == desired
        assert collection.items[0]["type"] == "module"
        assert collection.items[1]["url"] == "/local/other-card.js?v=1"

    async def test_creates_resource_when_absent(self, hass, tmp_path, monkeypatch):
        """Without any matching resource it is created as a module."""
        version = _fake_package_version(tmp_path, monkeypatch, "0.6.4")
        collection = FakeResourceCollection(
            [{"id": "r2", "url": "/local/other-card.js?v=1", "type": "module"}]
        )
        hass.data["lovelace"] = SimpleNamespace(resources=collection)

        assert await async_sync_frontend_resource(hass) is True

        desired = f"{FRONTEND_RESOURCE_URL_BASE}?v={version}"
        assert collection.updated == []
        assert collection.created == [{"url": desired, "res_type": "module"}]

    async def test_noop_when_url_current(self, hass, tmp_path, monkeypatch):
        """A resource already carrying the current ?v= is left alone."""
        version = _fake_package_version(tmp_path, monkeypatch, "0.6.4")
        collection = FakeResourceCollection(
            [
                {
                    "id": "r1",
                    "url": f"{FRONTEND_RESOURCE_URL_BASE}?v={version}",
                    "type": "module",
                }
            ]
        )
        hass.data["lovelace"] = SimpleNamespace(resources=collection)

        assert await async_sync_frontend_resource(hass) is False

        assert collection.updated == []
        assert collection.created == []

    async def test_no_crash_when_lovelace_missing(self, hass, tmp_path, monkeypatch):
        """No lovelace data in hass.data (tests/CI): graceful False."""
        _fake_package_version(tmp_path, monkeypatch)
        assert "lovelace" not in hass.data

        assert await async_sync_frontend_resource(hass) is False

    async def test_yaml_mode_stale_resource_is_not_touched(
        self, hass, tmp_path, monkeypatch
    ):
        """YAML-mode collections are read-only: warn and return False."""
        _fake_package_version(tmp_path, monkeypatch, "0.6.4")
        collection = FakeYamlCollection(
            [{"url": f"{FRONTEND_RESOURCE_URL_BASE}?v=0.1.0", "type": "module"}]
        )
        hass.data["lovelace"] = SimpleNamespace(resources=collection)

        assert await async_sync_frontend_resource(hass) is False

        assert collection.items[0]["url"] == (
            f"{FRONTEND_RESOURCE_URL_BASE}?v=0.1.0"
        )

    async def test_dict_shape_lovelace_data_supported(
        self, hass, tmp_path, monkeypatch
    ):
        """A dict-shaped hass.data['lovelace'] is tolerated (fallback path)."""
        version = _fake_package_version(tmp_path, monkeypatch, "0.6.4")
        collection = FakeResourceCollection([])
        hass.data["lovelace"] = {"resources": collection}

        assert await async_sync_frontend_resource(hass) is True

        assert collection.created == [
            {"url": f"{FRONTEND_RESOURCE_URL_BASE}?v={version}", "res_type": "module"}
        ]

    async def test_version_unreadable_returns_false(self, hass, tmp_path, monkeypatch):
        """Without a readable manifest version nothing is touched."""
        import hikcentral_district as integration

        pkg = tmp_path / "pkg"
        pkg.mkdir(exist_ok=True)  # no manifest.json inside
        monkeypatch.setattr(integration, "__file__", str(pkg / "__init__.py"))
        collection = FakeResourceCollection([])
        hass.data["lovelace"] = SimpleNamespace(resources=collection)

        assert await async_sync_frontend_resource(hass) is False

        assert collection.updated == []
        assert collection.created == []
