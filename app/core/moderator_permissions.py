"""Moderator permission registry and AppConfig read/write helpers.

Mirrors the `feature_flags.py` pattern: DB overrides are stored as a flat
boolean map under AppConfig key `moderator_permissions`. Callers merge
stored values over `MODERATOR_PERMISSION_DEFAULTS` so a missing row (or
a partial map) always resolves to a secure-by-default all-False state.

`set_moderator_permissions` does NOT call `db.commit()` — the caller
owns the transaction and commits after also writing an audit log row,
matching the `log_admin_action` + `db.commit()` pattern used elsewhere
in admin routes.
"""

MODERATOR_PERMISSION_DEFAULTS: dict[str, bool] = {
    "validate_ticket": False,
    "ticket_packages": False,
    "user_reports": False,
    "manage_sessions": False,
}


def get_moderator_permissions(db) -> dict[str, bool]:
    """Read merged moderator_permissions from AppConfig, secure-default all-False.

    Returns a dict with exactly the three keys in MODERATOR_PERMISSION_DEFAULTS.
    Unknown keys in the stored row are ignored. Missing keys fall back to False.
    """
    from app.models.app_config import AppConfig

    row = db.get(AppConfig, "moderator_permissions")
    stored = row.value if row and isinstance(row.value, dict) else {}

    merged: dict[str, bool] = {}
    for key, default in MODERATOR_PERMISSION_DEFAULTS.items():
        merged[key] = bool(stored.get(key, default))
    return merged


def set_moderator_permissions(db, new_perms: dict[str, bool]) -> dict[str, bool]:
    """Write the moderator_permissions map to AppConfig (without committing).

    Only the three known keys are written. Any extra keys in `new_perms` are
    dropped. Missing keys fall back to their current stored value (or default).
    Caller is responsible for calling `db.commit()`.
    """
    from app.models.app_config import AppConfig

    # Merge over current state so a partial payload doesn't wipe other keys
    current = get_moderator_permissions(db)
    merged: dict[str, bool] = {}
    for key in MODERATOR_PERMISSION_DEFAULTS.keys():
        if key in new_perms:
            merged[key] = bool(new_perms[key])
        else:
            merged[key] = current[key]

    row = db.get(AppConfig, "moderator_permissions")
    if row:
        row.value = merged
    else:
        db.add(AppConfig(key="moderator_permissions", value=merged))
    return merged
