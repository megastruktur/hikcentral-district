"""Test sync_frontend_js — idempotent copy of the Lovelace card into www/."""

from hikcentral_district import FRONTEND_JS_NAME, sync_frontend_js


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
