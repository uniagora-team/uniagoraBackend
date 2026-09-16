#!/usr/bin/env python
"""Cron entrypoint: product expiry sweep.

Standalone (no Django management plumbing) so a scheduler can run it inside
the app container without `manage.py`. Requires DJANGO_SETTINGS_MODULE and
the standard Django env vars. Exits non-zero on failure so the scheduler can
alert on it.

    DJANGO_SETTINGS_MODULE=config.settings.production python ops/cron.py sweep
"""

import os
import sys
from pathlib import Path

# Running as a script puts ops/ on sys.path, not the project root; add the
# project root so `config` and the apps are importable.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _fail(message: str) -> "NoReturn":  # noqa: F821
    print(message, file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) >= 2 else 2)

    job = sys.argv[1]

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
    import django

    django.setup()

    if job == "sweep":
        import ops.product_lifecycle

        count = ops.product_lifecycle.run_expiry_sweep()
        print(f"Expired {count} product{'s' if count != 1 else ''}.")
        return

    _fail(f"Unknown job: {job!r}. Available: sweep")


if __name__ == "__main__":
    main()
