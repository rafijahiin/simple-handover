"""Repair BaselineResponse.population misfiled by the old guessing fallback.

`_xform_id_string` carries the ASSET UID, which contains no 'fsw', so the old
`'fsw' if 'fsw' in xf else 'hijra'` filed every FSW interview as Hijra. This
recomputes each stored response's population from its own raw_data using the
authoritative resolver (baseline/populations.py) and fixes the mismatches.

Baseline only. Dry-run by default; pass --commit to write.
Runs via the Dockerfile boot gate BACKFILL_BASELINE_POPULATION=1 (prod DB is
internal-only), then unset it.
"""
from collections import Counter

from django.core.management.base import BaseCommand

from baseline.models import BaselineResponse
from baseline.populations import resolve_population


class Command(BaseCommand):
    help = 'Recompute BaselineResponse.population from the source form; fix misfiled rows.'

    def add_arguments(self, parser):
        parser.add_argument('--commit', action='store_true',
                            help='Actually write (default is a dry run).')

    def handle(self, *args, **opts):
        rows = list(BaselineResponse.objects.all().only('id', 'population', 'raw_data'))
        before = Counter(r.population for r in rows)

        fixes, unresolved = [], 0
        for r in rows:
            truth = resolve_population(r.raw_data)
            if truth is None:
                unresolved += 1
                continue
            if truth != r.population:
                fixes.append((r, truth))

        after = Counter()
        for r in rows:
            truth = resolve_population(r.raw_data) or r.population
            after[truth] += 1

        self.stdout.write(f'BaselineResponse rows: {len(rows)}')
        self.stdout.write(f'  stored population : {dict(before)}')
        self.stdout.write(f'  resolved from form: {dict(after)}')
        self.stdout.write(f'  MISFILED          : {len(fixes)}   unresolved: {unresolved}')

        if not fixes:
            self.stdout.write('Nothing to fix.')
            return
        if not opts['commit']:
            self.stdout.write('Dry run — pass --commit to write.')
            return

        for r, truth in fixes:
            r.population = truth
        BaselineResponse.objects.bulk_update([r for r, _ in fixes], ['population'], batch_size=200)
        self.stdout.write(f'Fixed {len(fixes)} row(s).')
        self.stdout.write(f'  now: {dict(Counter(BaselineResponse.objects.values_list("population", flat=True)))}')
