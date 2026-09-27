# reworks -- tenant seed scripts

Event-specific seed scripts for the `reworks` tenant.

Each seed module must export a `run` callable. Add it to `ordered_seeds`
in `__init__.py` to include it in the bootstrap order.

Generic defaults (interests / goals / theme options) come from
`app/seed/generic/` and are always applied first.

Seed scripts MUST be idempotent -- re-runnable safely.
