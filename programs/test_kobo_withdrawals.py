"""The dangerous paths first: a partial read must never look like a deletion."""
from unittest import mock

from django.test import TestCase

from programs import kobo_withdrawals as kw
from programs.models import (Client, ClinicVisit, KoboWithdrawal, ServiceCenter)


def _centre():
    return ServiceCenter.objects.create(
        code='BND-DIC-99', name='Test Centre', organisation='Bandhu',
        district='Habiganj')


def _client(centre, cid, kobo):
    return Client.objects.create(
        client_id=cid, organisation='Bandhu', center=centre, name='A',
        kobo_submission_id=kobo, approval_status=Client.APPROVED)


class FetchGuardTests(TestCase):
    """Absence only means deletion when the read was complete."""

    def test_zero_assets_aborts(self):
        with mock.patch.object(kw, '_get', return_value={'results': []}):
            with self.assertRaises(kw.FetchIncomplete):
                kw.deployed_assets('tok')

    def test_http_error_aborts(self):
        resp = mock.Mock(ok=False, status_code=502)
        with mock.patch.object(kw.requests, 'get', return_value=resp):
            with self.assertRaises(kw.FetchIncomplete):
                kw._get('http://x', 'tok')

    def test_network_error_aborts(self):
        with mock.patch.object(kw.requests, 'get',
                               side_effect=kw.requests.RequestException('down')):
            with self.assertRaises(kw.FetchIncomplete):
                kw._get('http://x', 'tok')

    def test_every_form_empty_aborts(self):
        """A silent token failure returns empty pages, not an error."""
        assets = [{'uid': 'a1', 'name': 'F1', 'asset_type': 'survey',
                   'has_deployment': True}]
        with mock.patch.object(kw, 'deployed_assets', return_value=assets), \
             mock.patch.object(kw, '_get', return_value={'results': []}):
            with self.assertRaises(kw.FetchIncomplete):
                kw.live_submission_ids('tok')

    def test_reconcile_aborts_before_touching_anything(self):
        centre = _centre()
        _client(centre, 'HB-0001', '111')
        with mock.patch.object(kw, 'live_submission_ids',
                               side_effect=kw.FetchIncomplete('boom')):
            with self.assertRaises(kw.FetchIncomplete):
                kw.reconcile(apply=True)
        self.assertEqual(Client.objects.count(), 1)


class DetectionTests(TestCase):
    def setUp(self):
        self.centre = _centre()

    def test_missing_id_is_detected(self):
        _client(self.centre, 'HB-0001', '111')
        rows = kw.find_withdrawn({'222'})
        self.assertEqual([r[1].kobo_submission_id for r in rows], ['111'])

    def test_present_id_is_left_alone(self):
        _client(self.centre, 'HB-0001', '111')
        self.assertEqual(kw.find_withdrawn({'111'}), [])

    def test_records_without_a_kobo_id_are_never_touched(self):
        """Dashboard-entered rows have no Kobo id; Kobo has no opinion on them."""
        Client.objects.create(client_id='HB-0002', organisation='Bandhu',
                              center=self.centre, name='B',
                              kobo_submission_id=None)
        self.assertEqual(kw.find_withdrawn(set()), [])


class WithdrawTests(TestCase):
    def setUp(self):
        self.centre = _centre()

    def test_size_cap_refuses_without_force(self):
        for i in range(3):
            _client(self.centre, 'HB-000%d' % i, str(100 + i))
        rows = kw.find_withdrawn(set())
        with self.assertRaises(kw.FetchIncomplete):
            kw.withdraw(rows, max_delete=2)
        self.assertEqual(Client.objects.count(), 3)

    def test_force_gets_past_the_cap(self):
        for i in range(3):
            _client(self.centre, 'HB-000%d' % i, str(100 + i))
        deleted, blocked = kw.withdraw(kw.find_withdrawn(set()), max_delete=2,
                                       force=True)
        self.assertEqual(len(deleted), 3)
        self.assertEqual(blocked, [])
        self.assertEqual(Client.objects.count(), 0)

    def test_deletion_is_recorded_before_it_happens(self):
        c = _client(self.centre, 'HB-0001', '111')
        kw.withdraw(kw.find_withdrawn(set()), actor='tester')
        entry = KoboWithdrawal.objects.get()
        self.assertEqual(entry.kobo_submission_id, '111')
        self.assertEqual(entry.model_label, 'programs.Client')
        self.assertEqual(entry.approval_status, Client.APPROVED)
        self.assertEqual(entry.actor, 'tester')
        self.assertEqual(entry.snapshot.get('client_id'), 'HB-0001')
        self.assertFalse(Client.objects.filter(pk=c.pk).exists())

    def test_a_client_with_services_is_blocked_not_orphaned(self):
        c = _client(self.centre, 'HB-0001', '111')
        ClinicVisit.objects.create(organisation='Bandhu', center=self.centre,
                                   client=c, visit_date='2026-08-01')
        deleted, blocked = kw.withdraw(kw.find_withdrawn({'999'}))
        self.assertEqual(deleted, [])
        self.assertEqual(len(blocked), 1)
        self.assertTrue(Client.objects.filter(pk=c.pk).exists())
        # The audit row must not survive a rollback and claim a deletion that
        # never happened.
        self.assertEqual(KoboWithdrawal.objects.count(), 0)


class DryRunTests(TestCase):
    def test_dry_run_changes_nothing(self):
        centre = _centre()
        _client(centre, 'HB-0001', '111')
        with mock.patch.object(kw, 'live_submission_ids',
                               return_value=({'222'}, {'F1': 1})):
            r = kw.reconcile(apply=False)
        self.assertEqual(len(r['candidates']), 1)
        self.assertEqual(r['deleted'], [])
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(KoboWithdrawal.objects.count(), 0)


class OrgScopeTests(TestCase):
    """A deletion request from one partner must not sweep another's records."""

    def setUp(self):
        self.bandhu = _centre()
        self.phd = ServiceCenter.objects.create(
            code='PHD-99', name='PHD Centre', organisation='PHD',
            district='Rajbari')

    def test_scope_limits_to_one_organisation(self):
        _client(self.bandhu, 'HB-0001', '111')
        Client.objects.create(client_id='R001-1', organisation='PHD',
                              center=self.phd, name='B',
                              kobo_submission_id='222')
        rows = kw.find_withdrawn(set(), org='Bandhu')
        self.assertEqual([r[1].kobo_submission_id for r in rows], ['111'])

    def test_unscoped_still_finds_everything(self):
        _client(self.bandhu, 'HB-0001', '111')
        Client.objects.create(client_id='R001-1', organisation='PHD',
                              center=self.phd, name='B',
                              kobo_submission_id='222')
        self.assertEqual(len(kw.find_withdrawn(set())), 2)

    def test_models_without_an_organisation_are_skipped_when_scoped(self):
        """MPDSR actions carry no organisation, so a scoped run must not touch
        them rather than guess that they belong to the partner asking."""
        from mpdsr.models import MPDSRAction
        scanned = [m._meta.label for m in kw.submission_models()]
        self.assertIn('mpdsr.MPDSRAction', scanned)
        has_org = 'organisation' in {f.name for f in MPDSRAction._meta.get_fields()}
        rows = kw.find_withdrawn(set(), org='Bandhu')
        self.assertFalse(any(m is MPDSRAction for m, _ in rows) and not has_org)


class CommandOutputTests(TestCase):
    """A blocked row must never be reported as removed."""

    def test_blocked_row_is_not_printed_as_removed(self):
        from io import StringIO
        from django.core.management import call_command
        from programs.models import KoboSyncRun
        centre = _centre()
        c = _client(centre, 'HB-0001', '111')
        ClinicVisit.objects.create(organisation='Bandhu', center=centre,
                                   client=c, visit_date='2026-08-01')
        # A deletion needs two passes to agree, so stand in for the first.
        KoboSyncRun.objects.create(
            org='', candidate_ids=['programs.Client:%s' % c.pk])
        out = StringIO()
        with mock.patch.object(kw, 'live_submission_ids',
                               return_value=({'999'}, {'F1': 1})):
            call_command('sync_kobo_deletions', '--apply', stdout=out)
        text = out.getvalue()
        self.assertIn('BLOCKED', text)
        self.assertNotIn('removed      programs.Client', text)
        self.assertTrue(Client.objects.filter(pk=c.pk).exists())


class SyncDaemonTests(TestCase):
    """The schedule must survive worker recycling and stay switched off by
    default."""

    def setUp(self):
        from programs import kobo_sync_daemon as d
        self.d = d

    def _env(self, **kw):
        return mock.patch.dict('os.environ', kw, clear=False)

    def test_off_unless_configured(self):
        with mock.patch.dict('os.environ', {}, clear=True):
            self.assertEqual(self.d._orgs(), [])
            self.assertFalse(self.d.start())

    def test_named_organisations_are_parsed(self):
        with self._env(KOBO_DELETION_SYNC='Bandhu, PHD'):
            self.assertEqual(self.d._orgs(), ['Bandhu', 'PHD'])

    def test_all_means_unscoped(self):
        with self._env(KOBO_DELETION_SYNC='all'):
            self.assertEqual(self.d._orgs(), [None])

    def test_first_pass_is_due_then_not(self):
        from programs.models import KoboSyncRun
        self.assertTrue(self.d._due('Bandhu', 6))
        KoboSyncRun.objects.create(org='Bandhu')
        self.assertFalse(self.d._due('Bandhu', 6))
        # A different organisation has its own schedule.
        self.assertTrue(self.d._due('PHD', 6))

    def test_abort_is_recorded_not_swallowed(self):
        from programs.models import KoboSyncRun
        with mock.patch.object(kw, 'live_submission_ids',
                               side_effect=kw.FetchIncomplete('kobo down')):
            row = self.d.run_once('Bandhu')
        self.assertIn('kobo down', row.error)
        self.assertEqual(KoboSyncRun.objects.count(), 1)

    def test_unattended_cap_is_tighter_than_the_manual_one(self):
        self.assertLess(self.d.AUTO_MAX_DELETE, kw.MAX_DELETE)

    def test_a_large_removal_is_left_for_a_person(self):
        from programs.models import KoboSyncRun
        centre = _centre()
        made = [_client(centre, 'HB-%04d' % i, str(9000 + i))
                for i in range(self.d.AUTO_MAX_DELETE + 1)]
        # The cap is only reached once a second pass confirms them.
        KoboSyncRun.objects.create(
            org='Bandhu',
            candidate_ids=['programs.Client:%s' % c.pk for c in made])
        with mock.patch.object(kw, 'live_submission_ids',
                               return_value=({'1'}, {'F1': 1})):
            row = self.d.run_once('Bandhu')
        self.assertIn('above the limit', row.error)
        self.assertEqual(row.deleted, 0)
        self.assertEqual(Client.objects.count(), self.d.AUTO_MAX_DELETE + 1)


class TwoPassTests(TestCase):
    """One read is not evidence.

    On 2026-08-26 a single read of KoboToolbox missed 26 live submissions, 22
    of them CIPRB response plan actions, because Kobo pages by offset and new
    submissions arriving mid-read shift the window. Acting on that read would
    have destroyed real programme data. A record now has to be missing from two
    consecutive passes before it is touched.
    """

    def setUp(self):
        self.centre = _centre()
        self.client_row = _client(self.centre, 'HB-0001', '111')

    def _reconcile(self, apply):
        with mock.patch.object(kw, 'live_submission_ids',
                               return_value=({'999'}, {'F1': 1})):
            return kw.reconcile(apply=apply, org='Bandhu')

    def test_first_pass_deletes_nothing(self):
        from programs.models import KoboSyncRun
        r = self._reconcile(apply=True)
        self.assertEqual(len(r['candidates']), 1)
        self.assertEqual(r['confirmed'], [])
        self.assertEqual(r['deleted'], [])
        self.assertTrue(Client.objects.filter(pk=self.client_row.pk).exists())
        self.assertEqual(KoboSyncRun.objects.count(), 0)

    def test_second_pass_deletes_what_both_passes_agree_on(self):
        from programs.models import KoboSyncRun
        first = self._reconcile(apply=True)
        KoboSyncRun.objects.create(org='Bandhu',
                                   candidate_ids=first['candidate_keys'])
        r = self._reconcile(apply=True)
        self.assertEqual(len(r['deleted']), 1)
        self.assertFalse(Client.objects.filter(pk=self.client_row.pk).exists())

    def test_a_record_that_reappears_is_never_touched(self):
        """Exactly the 22 response plan actions: gone from one read, back on
        the next, and so never eligible."""
        from programs.models import KoboSyncRun
        first = self._reconcile(apply=True)
        KoboSyncRun.objects.create(org='Bandhu',
                                   candidate_ids=first['candidate_keys'])
        with mock.patch.object(kw, 'live_submission_ids',
                               return_value=({'111'}, {'F1': 1})):
            r = kw.reconcile(apply=True, org='Bandhu')
        self.assertEqual(r['candidates'], [])
        self.assertEqual(r['deleted'], [])
        self.assertTrue(Client.objects.filter(pk=self.client_row.pk).exists())

    def test_an_aborted_pass_is_not_treated_as_a_first_pass(self):
        from programs.models import KoboSyncRun
        KoboSyncRun.objects.create(org='Bandhu', error='kobo down',
                                   candidate_ids=[])
        r = self._reconcile(apply=True)
        self.assertEqual(r['deleted'], [])

    def test_pages_are_read_in_a_fixed_order(self):
        """Offset paging without a sort is what skipped the rows."""
        import inspect
        src = inspect.getsource(kw.live_submission_ids)
        self.assertIn('sort=', src)
        self.assertIn('_id', src)
