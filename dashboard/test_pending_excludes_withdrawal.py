"""The pending-approval banner must NOT count KoboWithdrawal tombstones.

KoboWithdrawal logs records deleted in KoboToolbox and carries an
approval_status snapshot, so the field-triple heuristic used to miscount it as
a live submission awaiting approval. Real pending = live submissions only."""
from datetime import date

from django.test import TestCase

from programs.models import ServiceCenter, StockEntry
from programs.models.withdrawal import KoboWithdrawal
from dashboard.views import _partner_programs_counts


class PendingExcludesWithdrawalTest(TestCase):
    def test_withdrawal_tombstones_not_counted_as_pending(self):
        center = ServiceCenter.objects.create(
            code='R001', organisation='PHD', name='WC',
            center_type=ServiceCenter.BROTHEL, district='Rajbari', is_active=True,
        )
        # One genuine pending submission.
        StockEntry.objects.create(
            organisation='PHD', center=center, reporting_month=date(2026, 9, 1),
            item_name='Condom', quantity_issued=10, approval_status='PENDING',
        )
        # Fourteen deletion tombstones that must be ignored.
        for i in range(14):
            KoboWithdrawal.objects.create(
                model_label='programs.ClinicVisit', record_pk=str(i),
                kobo_submission_id=f'k{i}', organisation='PHD',
                approval_status='PENDING',
            )
        _, pending = _partner_programs_counts(
            'PHD', date(2026, 9, 1), date(2026, 10, 1))
        self.assertEqual(pending, 1)   # the StockEntry only, not the 14 tombstones
