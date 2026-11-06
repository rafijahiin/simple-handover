"""The client-CSV push skips Kobo when the CSV bytes have not changed.

Every Client save schedules a push that uploads the org's clients CSV and
redeploys its three Kobo forms. Most of those saves do not touch a single
exported column — a service log stamping updated_at, an approval flag, a status
change — so the identical bytes were being re-uploaded all day: 487 uploads and
484 redeploys in a measured 24 hours, the leading explanation for the ~460 MB/day
of billed egress that never appeared in the HTTP logs.

The guard compares a hash of the bytes actually accepted by Kobo. A genuinely
new or edited client changes the CSV, so the field-facing behaviour is
unchanged; only the redundant pushes stop.

Two properties matter more than the saving, and are pinned here:
  * a push that FAILED must not be remembered, or one bad upload would be
    skipped forever. Both halves report failure by RETURNING FALSE rather than
    raising: upload_to_kobo when a media POST is rejected, redeploy_forms when a
    version fetch or PATCH fails. A CSV that uploaded but never got redeployed
    is the "registered, but the form says not in the list" bug itself, so it
    must stay retryable;
  * the cache is per-process and in memory, so a recycled worker re-pushes.
    The guard can only ever make the system less chatty, never more stale.
"""
from django.test import TestCase, override_settings

from programs import signals


class _FakeExport:
    """Stands in for one export_*_clients module."""

    def __init__(self, csv=b'a,b\n1,2\n', upload_ok=True, raise_on_upload=False,
                 redeploy_ok=True):
        self.csv = csv
        self.upload_ok = upload_ok
        self.raise_on_upload = raise_on_upload
        self.redeploy_ok = redeploy_ok
        self.uploads = 0
        self.redeploys = 0

    def build_csv(self):
        return self.csv, 1

    def upload_to_kobo(self, csv_bytes, out):
        self.uploads += 1
        if self.raise_on_upload:
            raise RuntimeError('kobo down')
        return self.upload_ok

    def redeploy_forms(self, out):
        self.redeploys += 1
        return self.redeploy_ok


@override_settings(KOBO_API_TOKEN='test-token')
class ClientCsvPushGuardTest(TestCase):
    def setUp(self):
        signals.reset_push_cache()
        self.addCleanup(signals.reset_push_cache)
        self.mod = _FakeExport()
        self._orig = signals._load_export
        signals._load_export = lambda org: self.mod
        self.addCleanup(lambda: setattr(signals, '_load_export', self._orig))

    def test_first_push_uploads_and_redeploys(self):
        signals._push_org('Bandhu')
        self.assertEqual(self.mod.uploads, 1)
        self.assertEqual(self.mod.redeploys, 1)

    def test_identical_csv_is_not_pushed_again(self):
        signals._push_org('Bandhu')
        signals._push_org('Bandhu')
        signals._push_org('Bandhu')
        self.assertEqual(self.mod.uploads, 1)
        self.assertEqual(self.mod.redeploys, 1)

    def test_a_changed_csv_is_pushed(self):
        signals._push_org('Bandhu')
        self.mod.csv = b'a,b\n1,2\n3,4\n'      # a new client registered
        signals._push_org('Bandhu')
        self.assertEqual(self.mod.uploads, 2)
        self.assertEqual(self.mod.redeploys, 2)

    def test_a_csv_that_reverts_is_pushed_again(self):
        first = self.mod.csv
        signals._push_org('Bandhu')
        self.mod.csv = b'a,b\n1,2\n3,4\n'
        signals._push_org('Bandhu')
        self.mod.csv = first                   # client deleted again
        signals._push_org('Bandhu')
        self.assertEqual(self.mod.uploads, 3)

    def test_a_failed_upload_is_not_remembered(self):
        self.mod.upload_ok = False
        signals._push_org('Bandhu')
        self.assertEqual(self.mod.uploads, 1)
        self.assertEqual(self.mod.redeploys, 0)   # nothing to redeploy
        self.mod.upload_ok = True
        signals._push_org('Bandhu')               # same bytes, must retry
        self.assertEqual(self.mod.uploads, 2)
        self.assertEqual(self.mod.redeploys, 1)

    def test_a_failed_redeploy_is_not_remembered(self):
        # The CSV is attached but Enketo still serves the old transform: the
        # exact "registered, but the form says not in the list" failure. The
        # next save must re-push, not be skipped as unchanged.
        self.mod.redeploy_ok = False
        signals._push_org('Bandhu')
        self.assertEqual(self.mod.uploads, 1)
        self.assertEqual(self.mod.redeploys, 1)
        signals._push_org('Bandhu')               # same bytes, must retry
        self.assertEqual(self.mod.uploads, 2)
        self.assertEqual(self.mod.redeploys, 2)

    def test_a_recovered_redeploy_is_remembered(self):
        self.mod.redeploy_ok = False
        signals._push_org('Bandhu')
        self.mod.redeploy_ok = True
        signals._push_org('Bandhu')               # this one lands
        signals._push_org('Bandhu')               # now it may be skipped
        self.assertEqual(self.mod.uploads, 2)
        self.assertEqual(self.mod.redeploys, 2)

    def test_an_upload_that_raises_is_not_remembered(self):
        self.mod.raise_on_upload = True
        signals._push_org('Bandhu')
        self.mod.raise_on_upload = False
        signals._push_org('Bandhu')
        self.assertEqual(self.mod.uploads, 2)
        self.assertEqual(self.mod.redeploys, 1)

    def test_each_org_is_cached_separately(self):
        bandhu, phd = _FakeExport(b'bandhu\n'), _FakeExport(b'phd\n')
        signals._load_export = lambda org: bandhu if org == 'Bandhu' else phd
        signals._push_org('Bandhu')
        signals._push_org('PHD')
        signals._push_org('Bandhu')
        self.assertEqual(bandhu.uploads, 1)
        self.assertEqual(phd.uploads, 1)

    def test_reset_clears_the_cache_so_a_new_worker_re_pushes(self):
        signals._push_org('Bandhu')
        signals.reset_push_cache()
        signals._push_org('Bandhu')
        self.assertEqual(self.mod.uploads, 2)


@override_settings(KOBO_API_TOKEN='')
class ClientCsvPushNoTokenTest(TestCase):
    def setUp(self):
        signals.reset_push_cache()
        self.addCleanup(signals.reset_push_cache)

    def test_no_token_pushes_nothing_and_caches_nothing(self):
        mod = _FakeExport()
        orig = signals._load_export
        signals._load_export = lambda org: mod
        self.addCleanup(lambda: setattr(signals, '_load_export', orig))
        import os
        old = os.environ.pop('KOBO_TOKEN', None)
        try:
            signals._push_org('Bandhu')
        finally:
            if old is not None:
                os.environ['KOBO_TOKEN'] = old
        self.assertEqual(mod.uploads, 0)
