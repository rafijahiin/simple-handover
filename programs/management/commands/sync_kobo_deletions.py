"""Remove Spondon records whose KoboToolbox submission has been deleted.

Kobo has no deletion webhook, so this compares what Kobo still holds against
what we stored. Read programs/kobo_withdrawals.py for why every guard is there.

    python manage.py sync_kobo_deletions            # dry run, changes nothing
    python manage.py sync_kobo_deletions --apply    # remove them
    python manage.py sync_kobo_deletions --apply --force   # past the size cap
"""
from django.core.management.base import BaseCommand, CommandError

from programs.kobo_withdrawals import MAX_DELETE, FetchIncomplete, reconcile


class Command(BaseCommand):
    help = 'Delete records that were deleted in KoboToolbox.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='actually remove them (default is a dry run)')
        parser.add_argument('--force', action='store_true',
                            help='proceed even above --max-delete')
        parser.add_argument('--max-delete', type=int, default=MAX_DELETE,
                            help='refuse to remove more than this in one run')
        parser.add_argument('--actor', default='sync_kobo_deletions',
                            help='who or what triggered this run')
        parser.add_argument('--org', default=None,
                            help='limit to one organisation, e.g. Bandhu')

    def handle(self, *args, **o):
        try:
            r = reconcile(apply=o['apply'], actor=o['actor'],
                          max_delete=o['max_delete'], force=o['force'],
                          org=o['org'], stdout=self.stdout.write)
        except FetchIncomplete as exc:
            # Never fall through to "nothing came back, so delete everything".
            raise CommandError('Aborted without changing anything: %s' % exc)

        if o['apply']:
            # Report what actually happened. Printing "removed" for every
            # candidate said a blocked row had been deleted when it had not.
            for label, sid in r['deleted']:
                self.stdout.write('  removed      %-38s kobo=%s' % (label, sid))
        else:
            for label, pk, sid in r['candidates']:
                self.stdout.write('  would remove %-38s kobo=%s' % (label, sid))
        for label, pk, why in r['blocked']:
            self.stdout.write(self.style.WARNING(
                '  BLOCKED %s %s: a service record still points at it. %s'
                % (label, pk, why)))
        if r['blocked']:
            self.stdout.write(
                'Blocked rows were left alone on purpose: deleting them would '
                'orphan service history. Remove the dependent records first.')
