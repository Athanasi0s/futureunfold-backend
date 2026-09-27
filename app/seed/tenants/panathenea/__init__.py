"""Panathenea tenant seed order. Run via app/seed/bootstrap.py."""

from app.seed.tenants.panathenea import (
    seed_density,
    seed_dummy_map,
    seed_exhibitor_whitelist,
    seed_friend_locations,
    seed_groups,
    seed_matching_users,
    seed_messages,
    seed_outdoor_map,
    seed_scheduling,
    seed_sessions,
    seed_ticket_packages,
    seed_users,
)

# Order matters. Dependencies (derived from in-file comments + grep of required rows):
#   dummy_map          → venues/floors/rooms (foundational)
#   outdoor_map        → outdoor venue geometry
#   users              → speakers + test users (needed by sessions, scheduling, messages, density, friend_locations)
#   groups             → needs `interests` (from generic)
#   sessions           → needs venues (rooms) + users (speakers)
#   matching_users     → test users; needs `interests` + `goals` (from generic)
#   scheduling         → needs venues, users, sessions
#   messages           → needs users
#   density            → needs venues, users, groups
#   friend_locations   → needs users, matching_users, groups
#   exhibitor_whitelist → independent
#   ticket_packages    → independent; carries Panathenea-specific Stripe price IDs
#                        (moved out of generic/ so new tenants don't inherit them)
ordered_seeds = [
    seed_dummy_map.run,
    seed_outdoor_map.run,
    seed_users.run,
    seed_groups.run,
    seed_sessions.run,
    seed_matching_users.run,
    seed_scheduling.run,
    seed_messages.run,
    seed_density.run,
    seed_friend_locations.run,
    seed_exhibitor_whitelist.run,
    seed_ticket_packages.run,
]
