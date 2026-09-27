"""Future Unfold 2026 tenant seed order."""

from app.seed.tenants.future_unfold import seed_app_config, seed_program

ordered_seeds = [
    seed_app_config.run,
    seed_program.run,
]
