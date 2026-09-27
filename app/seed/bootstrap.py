"""Idempotent seed bootstrap — called by release_command on every deploy.

Runs tenant-agnostic "generic" seeds first, then the current tenant's
ordered seeds (as declared in app/seed/tenants/<TENANT_KEY>/__init__.py).

Exit early with a log line if SKIP_SEEDS=1 is set — emergency redeploy escape
hatch. Every individual seed module is expected to be idempotent.

Invoked by Phase A.5 via:
    alembic upgrade head && python -m app.seed.bootstrap

Locally:
    TENANT_KEY=panathenea python -m app.seed.bootstrap
"""
from __future__ import annotations

import importlib
import os

from app.core.config import TENANT_KEY
from app.seed import generic


def main() -> None:
    if os.getenv("SKIP_SEEDS") == "1":
        print("SKIP_SEEDS=1 → bootstrap skipped")
        return

    print(f"== seed bootstrap: tenant={TENANT_KEY!r} ==")

    print("-- generic seeds --")
    for fn in generic.ordered_seeds:
        print(f"   running {fn.__module__}.{fn.__name__}()")
        fn()

    # Deployment slugs may contain hyphens, while Python packages use
    # underscores (for example TENANT_KEY=future-unfold).
    tenant_module_key = TENANT_KEY.replace("-", "_")
    tenant_pkg_path = f"app.seed.tenants.{tenant_module_key}"
    try:
        tenant_pkg = importlib.import_module(tenant_pkg_path)
    except ModuleNotFoundError as e:
        raise RuntimeError(
            f"No seed package found for TENANT_KEY={TENANT_KEY!r}. "
            f"Expected module: {tenant_pkg_path}"
        ) from e

    tenant_seeds = getattr(tenant_pkg, "ordered_seeds", [])
    print(f"-- tenant seeds ({TENANT_KEY}) --")
    if not tenant_seeds:
        print("   (none)")
    for fn in tenant_seeds:
        print(f"   running {fn.__module__}.{fn.__name__}()")
        fn()

    print("== seed bootstrap: done ==")


if __name__ == "__main__":
    main()
