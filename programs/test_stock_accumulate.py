"""StockEntry now SUMS quantity across the many per-issue submissions for the
same (centre, month, item) instead of keeping only the last one, and is
idempotent against Kobo retries. Regression guard for the PHD SL5 undercount."""
from datetime import date

from django.test import TestCase

from programs.models import ServiceCenter, StockEntry
from programs.webhook import _accumulate_stock


class StockAccumulateTest(TestCase):
    def setUp(self):
        self.center = ServiceCenter.objects.create(
            code='R001', organisation='PHD', name='Daulatdia WC',
            center_type=ServiceCenter.BROTHEL, district='Rajbari', is_active=True,
        )
        self.month = date(2026, 9, 1)

    def _add(self, sid, issued, received=0):
        _accumulate_stock(
            center=self.center, reporting_month=self.month, item_name='Condom',
            org='PHD', submission_id=sid,
            quantity_issued=issued, quantity_received=received,
        )

    def test_sums_across_submissions(self):
        self._add('k1', 100)
        self._add('k2', 50)
        self._add('k3', 25)
        row = StockEntry.objects.get(center=self.center, reporting_month=self.month,
                                     item_name='Condom')
        self.assertEqual(row.quantity_issued, 175)          # 100 + 50 + 25, not 25
        self.assertEqual(StockEntry.objects.count(), 1)      # one row, not three
        self.assertEqual(sorted(row.source_submission_ids), ['k1', 'k2', 'k3'])

    def test_retry_is_idempotent(self):
        self._add('k1', 100)
        self._add('k1', 100)   # same Kobo _id delivered twice
        row = StockEntry.objects.get(item_name='Condom')
        self.assertEqual(row.quantity_issued, 100)           # not 200
        self.assertEqual(row.source_submission_ids, ['k1'])

    def test_opening_balance_from_first_only(self):
        _accumulate_stock(center=self.center, reporting_month=self.month,
                          item_name='Condom', org='PHD', submission_id='k1',
                          opening_balance=500, quantity_issued=10)
        _accumulate_stock(center=self.center, reporting_month=self.month,
                          item_name='Condom', org='PHD', submission_id='k2',
                          opening_balance=999, quantity_issued=10)
        row = StockEntry.objects.get(item_name='Condom')
        self.assertEqual(row.opening_balance, 500)           # first wins, not additive
        self.assertEqual(row.quantity_issued, 20)
