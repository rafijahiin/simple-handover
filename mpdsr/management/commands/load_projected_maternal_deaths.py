"""Load the district projected maternal deaths for 2026.

Source: "Projected Maternal death year 2026.xlsx", sent by Dr Tanjina Pervin
(RCH, CIPRB) on 6 September 2026, so that the dashboard can show each
district's reported maternal deaths against what the year is expected to
produce.

The figures live here rather than in a spreadsheet on someone's laptop because
the dashboard has to be able to rebuild them on any deployment. When RCH sends
a revised file, edit this table, note the date, and run the command again; it
upserts by district and never deletes.

Three districts came through blank in the file and are deliberately absent
rather than guessed at: Moulvibazar, Habiganj and Dhaka. Two came through
misspelled and are recorded under the spelling the rest of the system uses,
with the original kept beside it.
"""
from django.core.management.base import BaseCommand

from mpdsr.models import MPDSRDistrictDenominator

SOURCE = 'RCH CIPRB, Projected Maternal death year 2026, received 2026-09-06'

# district -> projected maternal deaths, 2026 full year.
PROJECTED_MD_2026 = {
    'Sunamganj': 99,
    'Sylhet': 34,
    'Bhola': 46,
    'Bagerhat': 42,
    'Sherpur': 36,
    'Jamalpur': 78,
    'Khagrachari': 19,
    'Bandarban': 10,
    'Kurigram': 67,
    'Rangpur': 74,        # written "Ragnpur" in the source file
    'Gaibandha': 86,
    'Bogura': 97,
    'Sirajganj': 87,
    'Rajshahi': 75,
    'Noakhali': 86,
    'Chandpur': 68,
    'Patuakhali': 99,     # written "Patuakahli" in the source file
    'Barguna': 34,
}

# Named in the file with no figure against them. Listed so that a reader of
# this file knows they were considered and left out on purpose.
BLANK_IN_SOURCE = ('Moulvibazar', 'Habiganj', 'Dhaka')


class Command(BaseCommand):
    help = 'Upsert district projected maternal deaths for 2026 (RCH figures).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would change without writing.')

    def handle(self, *args, **opts):
        created = updated = unchanged = 0
        for district, md in sorted(PROJECTED_MD_2026.items()):
            row = MPDSRDistrictDenominator.objects.filter(district=district).first()
            if row and row.project_deaths_md == md:
                unchanged += 1
                continue
            self.stdout.write('  %-14s %s -> %s'
                              % (district,
                                 'none' if not row else row.project_deaths_md, md))
            if opts['dry_run']:
                created += 0 if row else 1
                updated += 1 if row else 0
                continue
            _, was_new = MPDSRDistrictDenominator.objects.update_or_create(
                district=district, defaults={'project_deaths_md': md})
            created += 1 if was_new else 0
            updated += 0 if was_new else 1

        self.stdout.write(self.style.SUCCESS(
            '%s: %d created, %d updated, %d already correct.%s'
            % (SOURCE, created, updated, unchanged,
               ' (dry run, nothing written)' if opts['dry_run'] else '')))
        self.stdout.write('Blank in the source file, not loaded: %s'
                          % ', '.join(BLANK_IN_SOURCE))
