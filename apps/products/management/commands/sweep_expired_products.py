"""The expiry-sweep management command.

Delegates to the shared `ops` runner (see ops/product_lifecycle.py). Intended
to be invoked by a scheduler — cron/systemd timer/celery-beat — every few
minutes, e.g.:

    python manage.py sweep_expired_products
"""

from django.core.management.base import BaseCommand

import ops.product_lifecycle


class Command(BaseCommand):
    help = (
        "Expire every ACTIVE product whose expires_at has passed "
        "(ACTIVE -> EXPIRED). Idempotent; safe to run on a frequent schedule."
    )

    def handle(self, *args, **options):
        count = ops.product_lifecycle.run_expiry_sweep()
        suffix = "" if count == 1 else "s"
        self.stdout.write(
            self.style.SUCCESS(f"Expired {count} product{suffix}.")
        )
