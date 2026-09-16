"""Product expiry lifecycle runner shared by management and cron entrypoints."""

from apps.products.services.lifecycle_service import ProductLifecycleService


def run_expiry_sweep() -> int:
    """Expire every ACTIVE product whose `expires_at` has passed.

    Returns the number of rows transitioned ACTIVE -> EXPIRED. Kept in `ops`
    (not `apps.products.management`) so the same routine backs both the
    developer-facing management command and the ops/cron entrypoint — the
    scheduled job should never import Django management internals.
    """
    return ProductLifecycleService.sweep_expire()
