# Primer Festival — tenant seed scripts

This folder holds event-specific seed scripts for the `primer` tenant.

Each seed module must export a `run` callable. Add the callable to
`ordered_seeds` in `__init__.py` to include it in the bootstrap order.

Generic defaults (interests / goals / theme options / ticket packages) come
from `app/seed/generic/` and are always applied before these.

Seed scripts MUST be idempotent — they are re-runnable via
`python -m app.seed.bootstrap`. See `app/seed/tenants/panathenea/` for
reference implementations (note: panathenea's scripts are legacy and not fully
idempotent; new tenants should do better).
