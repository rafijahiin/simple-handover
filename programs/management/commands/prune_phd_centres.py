"""
Prune PHD ServiceCenter rows to match SIDA SL8 target (9 brothel-based centres).

The earlier seed created 11 brothels + 1 SUB_DIC, plus the webhook fallback
auto-created stub centres ('AUTO-PHD'). Result: 14 active PHD centres on
Railway, making compute_SL8 return 14/9 = 156%.

This command keeps the 9 real wellness-centre codes (R001..D009) active and
deactivates everything else PHD-tagged — including the old PHD-BROTHEL-NN
placeholders and any AUTO-PHD webhook stubs. Idempotent.

Run on Railway:
    PRUNE_PHD_CENTRES=1 → set in Variables → redeploy → unset.
"""
from django.core.management.base import BaseCommand
from programs.models import ServiceCenter


# The 9 official Wellness Centre IDs (see seed_centers.PHD_BROTHELS).
KEEP_CODES = {'R001', 'J002', 'B003', 'P004', 'F005', 'M006', 'J007', 'T008', 'D009'}


class Command(BaseCommand):
    help = 'Deactivate non-canonical PHD centres so SL8 (target 9) is honest.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm', action='store_true',
            help='Actually deactivate. Without this, only counts are shown.',
        )

    def handle(self, *args, **options):
        confirm = options['confirm']

        active = ServiceCenter.objects.filter(organisation='PHD', is_active=True)
        keep = active.filter(code__in=KEEP_CODES)
        drop = active.exclude(code__in=KEEP_CODES)

        self.stdout.write(f'\nPHD centres — ' + ('PRUNING' if confirm else 'DRY RUN') + '\n')
        self.stdout.write(f'  keep   : {keep.count()} (R001..D009 wellness centres)')
        self.stdout.write(f'  to drop: {drop.count()} (other PHD centres)')
        if drop.exists():
            self.stdout.write('  drop codes:')
            for c in drop.values_list('code', 'center_type'):
                self.stdout.write(f'    - {c[0]:<28}  type={c[1]}')

        if confirm and drop.exists():
            n = drop.update(is_active=False)
            self.stdout.write(self.style.SUCCESS(f'\n  Deactivated {n} rows.\n'))
        elif not confirm:
            self.stdout.write(self.style.WARNING(
                '\n  Run with --confirm to actually deactivate.\n'))
