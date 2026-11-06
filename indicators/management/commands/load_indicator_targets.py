"""
Deprecated: IndicatorTarget seeding now happens in the data migration
indicators/migrations/0004_load_target_fixtures.py.

This command is a no-op for backwards compatibility with deploy scripts
that still invoke it. Remove the call from your deploy pipeline at your
convenience.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Deprecated. IndicatorTarget rows are seeded via migration 0004.'

    def handle(self, *args, **options):
        self.stdout.write(
            'load_indicator_targets is deprecated. IndicatorTarget rows '
            'are now seeded by migration 0004_load_target_fixtures and '
            'refreshed via the Target Config screen at /admin/targets. '
            'This command does nothing.'
        )
