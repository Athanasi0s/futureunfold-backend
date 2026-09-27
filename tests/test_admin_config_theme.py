"""Phase 13 Plan 08 — AppConfig theme-key round-trip + validation (THME-01..03).

Validates the 5 new AppConfig keys introduced in Plan 13-08:
- active_theme_preset_id  (slug, ^[a-z0-9_-]{1,40}$)
- theme_color_1..4        (6-digit hex, ^#[0-9a-fA-F]{6}$)

The backend exposes:
- PUT  /admin/config/{key}   (admin-only write; per-key whitelist)
- GET  /config               (public read; returns all theme keys with defaults)
The admin endpoint uses PUT {key} (not PATCH), so tests hit each key individually.
"""
import pytest

from app.core.enums import UserRole
from app.core.deps import require_admin
from app.main import app


@pytest.fixture()
def admin_client(client, db_session, test_user):
    test_user.role = UserRole.admin
    db_session.commit()
    app.dependency_overrides[require_admin] = lambda: test_user
    yield client
    app.dependency_overrides.pop(require_admin, None)


def test_put_valid_theme_keys(admin_client):
    # Set all 5 theme keys via individual PUTs
    keys_values = {
        "active_theme_preset_id": "ocean",
        "theme_color_1": "#194ff0",
        "theme_color_2": "#0a0e27",
        "theme_color_3": "#22d3ee",
        "theme_color_4": "#1e293b",
    }
    for key, value in keys_values.items():
        r = admin_client.put(f"/admin/config/{key}", json={"value": value})
        assert r.status_code == 200, f"{key} → {r.status_code}: {r.text}"

    # GET /config should expose the 5 theme keys with the values we set
    r = admin_client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert body["active_theme_preset_id"] == "ocean"
    assert body["theme_color_1"] == "#194ff0"
    assert body["theme_color_2"] == "#0a0e27"
    assert body["theme_color_3"] == "#22d3ee"
    assert body["theme_color_4"] == "#1e293b"


def test_put_invalid_hex_rejected(admin_client):
    r = admin_client.put(
        "/admin/config/theme_color_1", json={"value": "rgba(0,0,0,1)"}
    )
    assert r.status_code == 422
    assert "theme_color_1" in r.json()["detail"]


def test_put_invalid_hex_shorthand_rejected(admin_client):
    # 3-digit shorthand not allowed; the regex requires exactly 6 hex digits.
    r = admin_client.put("/admin/config/theme_color_2", json={"value": "#abc"})
    assert r.status_code == 422


def test_put_invalid_preset_id_rejected(admin_client):
    r = admin_client.put(
        "/admin/config/active_theme_preset_id", json={"value": "Ocean!<script>"}
    )
    assert r.status_code == 422


def test_put_null_value_resets_theme_key(admin_client):
    # First set a value, then clear it via null — GET /config should fall back to default.
    r1 = admin_client.put(
        "/admin/config/theme_color_3", json={"value": "#22d3ee"}
    )
    assert r1.status_code == 200
    r2 = admin_client.put("/admin/config/theme_color_3", json={"value": None})
    assert r2.status_code == 200
    r3 = admin_client.get("/config")
    assert r3.status_code == 200
    assert r3.json()["theme_color_3"] is None


def test_get_config_exposes_theme_keys_with_defaults(admin_client):
    # Without any PUT, the 5 theme keys must still appear on GET /config (null default).
    r = admin_client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert "active_theme_preset_id" in body
    assert "theme_color_1" in body
    assert "theme_color_2" in body
    assert "theme_color_3" in body
    assert "theme_color_4" in body
