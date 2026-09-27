"""Tenant-agnostic seed data — runs for every tenant before tenant-specific seeds.

`seed_ticket_packages` used to live here but was moved to
`app/seed/tenants/panathenea/` because the rows carry hardcoded Stripe price
IDs specific to Panathenea's Stripe account. New tenants that need ticketing
should ship their own tenant-specific seed with their own Stripe price IDs.
"""

from app.seed.generic import (
    seed_goals,
    seed_interests,
    seed_user_theme_options,
)

# Order is loose — these seeds don't depend on each other — but kept stable for
# predictable log output.
ordered_seeds = [
    seed_interests.run,
    seed_goals.run,
    seed_user_theme_options.run,
]
