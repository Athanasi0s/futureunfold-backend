"""
Feature flag registry and cascade logic.

Each feature has a default (True = enabled), optional dependencies,
and a human-readable label.  DB overrides live in AppConfig("feature_flags").
"""

FEATURE_REGISTRY: dict[str, dict] = {
    "schedule":         {"label": "Program & Schedule",     "default": True,  "depends_on": []},
    "map":              {"label": "Venue Map",              "default": True,  "depends_on": []},
    "digital_id":       {"label": "Digital Badge / QR",     "default": True,  "depends_on": []},
    "networking":       {"label": "Networking & Matching",   "default": True,  "depends_on": []},
    "groups":           {"label": "Groups",                 "default": True,  "depends_on": []},
    "group_chat":       {"label": "Group Chat",             "default": True,  "depends_on": ["groups"]},
    "direct_messages":  {"label": "Direct Messages",        "default": True,  "depends_on": []},
    "rewards":          {"label": "Points & Rewards",       "default": True,  "depends_on": []},
    "leaderboard":      {"label": "Leaderboard",            "default": True,  "depends_on": ["rewards"]},
    "certificates":     {"label": "Certificates & Wrapup",  "default": True,  "depends_on": ["rewards"]},
    "tickets":          {"label": "Ticketing",              "default": True,  "depends_on": []},
    "polls":            {"label": "Polls & Voting",         "default": True,  "depends_on": []},
    "exhibitors":       {"label": "Exhibitors",             "default": True,  "depends_on": []},
    "exhibitor_chat":   {"label": "Exhibitor Chat",         "default": True,  "depends_on": ["exhibitors"]},
    "session_chat":     {"label": "Session Live Chat",      "default": True,  "depends_on": ["schedule"]},
    "session_qa":       {"label": "Session Q&A",            "default": True,  "depends_on": ["schedule"]},
    "location_sharing": {"label": "Location Sharing",       "default": True,  "depends_on": ["groups", "map"]},
    "density":          {"label": "Venue Density",          "default": True,  "depends_on": ["map"]},
    "notifications":    {"label": "Push Notifications",     "default": True,  "depends_on": []},
    "recommendations":  {"label": "Recommendations",        "default": True,  "depends_on": []},
    "scheduling":       {"label": "Meeting Scheduling",     "default": True,  "depends_on": ["networking"]},
    "festival_stats":   {"label": "Festival Stats",         "default": True,  "depends_on": []},  # No backend route yet — mobile-only gate
}


def get_merged_flags(db) -> dict[str, bool]:
    """Merge registry defaults with DB overrides. Apply cascade rules."""
    from app.models.app_config import AppConfig

    row = db.get(AppConfig, "feature_flags")
    overrides = row.value if row else {}

    merged: dict[str, bool] = {}
    for key, meta in FEATURE_REGISTRY.items():
        merged[key] = bool(overrides.get(key, meta["default"]))

    # Cascade: if any parent is OFF, child must be OFF
    for key, meta in FEATURE_REGISTRY.items():
        if meta["depends_on"]:
            if any(not merged.get(dep, True) for dep in meta["depends_on"]):
                merged[key] = False

    return merged


def apply_cascade(flags: dict[str, bool], db=None) -> dict[str, bool]:
    """Apply cascade rules before saving to DB. Merges with current state to handle partial payloads."""
    if db:
        base = get_merged_flags(db)
    else:
        base = {k: m["default"] for k, m in FEATURE_REGISTRY.items()}
    result = {**base, **flags}
    for key, meta in FEATURE_REGISTRY.items():
        if meta["depends_on"]:
            if any(not result.get(dep, True) for dep in meta["depends_on"]):
                result[key] = False
    return result
