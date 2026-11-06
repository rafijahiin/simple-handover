"""
One-shot command to bulk-approve all PENDING Bandhu Client records that got
stranded when registration was briefly made PENDING (2026-06-30) before being
reverted to auto-approved.

Run once on prod:
    railway run python manage.py approve_pending_bandhu_clients
"""
from django.core.management.base import BaseCommand
from programs.models import Client


class Command(BaseCommand):
    help = 'Approve all PENDING Bandhu client registrations (stranded from brief approval gate).'

    def handle(self, *args, **options):
        qs = Client.objects.filter(organisation='Bandhu', approval_status=Client.PENDING)
        count = qs.count()
        if count == 0:
            self.stdout.write('No pending Bandhu clients found — nothing to do.')
            return
        updated = qs.update(approval_status=Client.APPROVED)
        self.stdout.write(self.style.SUCCESS(
            f'Approved {updated} Bandhu client(s) that were stuck in PENDING.'
        ))
