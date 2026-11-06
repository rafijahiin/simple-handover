"""Read-path contract for the CIPRB reconciliation health strip.

The heavy part of reconciliation — replaying live Kobo payloads and counting how
many rows the handlers must create — is verified against the real DB on Railway
(mpdsr/reconcile.py, `manage.py reconcile_ciprb`). What runs anywhere, and what
the dashboard depends on every page load, is the READ path:

  - the endpoint returns a truthful "not run yet" shape when there is no
    snapshot (it must NOT imply health),
  - it returns the NEWEST snapshot when several exist,
  - it is gated so only CIPRB-dashboard viewers can read it.

These tests lock that contract so a refactor can't silently turn "unknown" into
"all good" — the exact failure mode this whole guard exists to prevent.
"""
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from mpdsr.models import CIPRBReconSnapshot

URL = '/api/mpdsr/reconciliation/'


def _snapshot(run_at, *, stranded=0, crashes=0, all_ok=True, forms=None):
    return CIPRBReconSnapshot.objects.create(
        run_at=run_at,
        data={
            'forms': forms if forms is not None else [],
            'total_stranded': stranded,
            'total_crashes': crashes,
            'all_ok': all_ok,
        },
    )


class ReconciliationReadPathTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.ciprb = User.objects.create_user(
            email='recon@ciprb.org', password='p', full_name='Recon',
            organisation=Organisation.CIPRB, role=Role.ORG_LEAD)

    def test_no_snapshot_is_reported_as_unavailable_not_healthy(self):
        self.client.force_authenticate(self.ciprb)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        # The critical invariant: absence of data must never read as health.
        self.assertFalse(body['available'])
        self.assertFalse(body.get('all_ok', False))
        self.assertEqual(body['forms'], [])

    def test_returns_newest_snapshot_when_several_exist(self):
        now = timezone.now()
        _snapshot(now - timedelta(hours=2), stranded=9, all_ok=False)
        _snapshot(now - timedelta(hours=1), stranded=3, all_ok=False)
        newest = _snapshot(now, stranded=0, all_ok=True, forms=[
            {'slug': 'ciprb_near_miss_v1', 'kobo_count': 5, 'app_rows': 5,
             'stranded': 0, 'crashes': 0, 'hook_active': True},
        ])

        self.client.force_authenticate(self.ciprb)
        body = self.client.get(URL).json()
        self.assertTrue(body['available'])
        self.assertEqual(body['run_at'], newest.run_at.isoformat())
        self.assertEqual(body['total_stranded'], 0)
        self.assertTrue(body['all_ok'])
        self.assertEqual(len(body['forms']), 1)

    def test_drift_snapshot_surfaces_the_affected_form(self):
        _snapshot(timezone.now(), stranded=4, crashes=1, all_ok=False, forms=[
            {'slug': 'ciprb_mpdsr_community_maternal_v1', 'kobo_count': 20,
             'app_rows': 16, 'stranded': 4, 'crashes': 1, 'hook_active': True},
        ])
        self.client.force_authenticate(self.ciprb)
        body = self.client.get(URL).json()
        self.assertTrue(body['available'])
        self.assertEqual(body['total_stranded'], 4)
        self.assertEqual(body['total_crashes'], 1)
        self.assertEqual(body['forms'][0]['slug'],
                         'ciprb_mpdsr_community_maternal_v1')

    def test_unauthenticated_is_denied(self):
        res = self.client.get(URL)
        self.assertIn(res.status_code, (401, 403))

    def test_non_ciprb_manager_is_denied(self):
        phd = User.objects.create_user(
            email='m@phd.org', password='p', full_name='PHD Mgr',
            organisation=Organisation.PHD, role=Role.MANAGER)
        self.client.force_authenticate(phd)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 403)


# ── Partner (PHD + Bandhu) coverage ─────────────────────────────────────────

import re as _re
from unittest import mock

from django.db import transaction as _tx

from mpdsr import reconcile as R


class HookSlugParsing(TestCase):
    def test_slug_is_read_from_the_programs_webhook_endpoint(self):
        hooks = [{'endpoint': 'https://web-production-091fa.up.railway.app'
                              '/webhook/programs/form/phd_registration_v1/'}]
        self.assertEqual(R._slug_from_hooks(hooks), 'phd_registration_v1')

    def test_non_programs_endpoints_yield_nothing(self):
        self.assertIsNone(R._slug_from_hooks(
            [{'endpoint': 'https://example.com/other/'}, {'endpoint': None}]))


class PartnerCounterCoversEveryHandlerModel(TestCase):
    """If a PHD/Bandhu handler learns to create a model that the partner
    counter does not sum, a stranded submission creating only that model
    would look healthy. Scan the handler sources so the list cannot rot."""

    EXEMPT = {'Partner'}          # looked up, never created by a handler

    def test_every_created_model_is_counted(self):
        import inspect
        import programs.phd_handlers as ph
        import programs.bandhu_handlers as bh
        pattern = _re.compile(
            r'([A-Z]\w+)\.objects\.(?:get_or_create|update_or_create|create)\(')
        created = set()
        for modsrc in (inspect.getsource(ph), inspect.getsource(bh)):
            created |= set(pattern.findall(modsrc))
        missing = created - self.EXEMPT - set(R.PARTNER_COUNTER_MODELS)
        self.assertEqual(missing, set(),
                         'handler-created models missing from '
                         'PARTNER_COUNTER_MODELS: %s' % sorted(missing))


class PartnerReplayDetectsStranded(TestCase):
    """End to end on the real handler: a PHD registration that exists in Kobo
    but not in the app must count as stranded; once ingested it must not."""

    def setUp(self):
        from programs.models import ServiceCenter
        ServiceCenter.objects.create(
            code='R001', name='Test Wellness Center', organisation='PHD',
            center_type='KP_CLINIC', district='Rajbari', is_active=True)
        self.sub = {
            '_id': 900901,
            '_submission_time': '2026-07-15T10:00:00',
            'id_no': '9-0001',
            'name': 'Recon Fixture',
        }
        self.form = {'slug': 'phd_registration_v1', 'uid': 'uidPHD1',
                     'name': 'PHD 1', 'org': 'PHD',
                     'hook': {'hook_active': True, 'hook_endpoint_ok': True,
                              'failed_lifetime': 0, 'pending': 0}}

    def _run(self):
        with mock.patch.object(R, 'discover_partner_forms',
                               return_value=[self.form]), \
             mock.patch.object(R, '_fetch', return_value=[self.sub]), \
             mock.patch.dict('programs.ciprb_replay.CIPRB_SLUG_TO_UID',
                             {}, clear=True):
            with _tx.atomic():
                return R.reconcile_ciprb('token')

    def test_missing_submission_is_stranded_and_nothing_persists(self):
        from programs.models import Client
        res = self._run()
        self.assertEqual(len(res), 1)
        rec = res[0]
        self.assertEqual(rec['org'], 'PHD')
        self.assertEqual(rec['kobo_count'], 1)
        self.assertEqual(rec['stranded'], 1)
        self.assertFalse(rec['ok'])
        self.assertEqual(rec['crashes'], 0, rec.get('crash_detail'))
        self.assertEqual(
            Client.objects.filter(organisation__iexact='PHD').count(), 0,
            'the replay must roll back, never ingest')

    def test_ingested_submission_reconciles_clean(self):
        from programs.webhook import FORM_HANDLERS, _flatten_group_keys
        FORM_HANDLERS['phd_registration_v1'](
            _flatten_group_keys(self.sub), None, None)
        res = self._run()
        self.assertEqual(res[0]['stranded'], 0)
        self.assertTrue(res[0]['ok'])


class FetchFollowsPagination(TestCase):
    """Kobo caps a page at 1,000. The reconciliation must see EVERY
    submission, or the newest records of the big partner forms silently
    escape the guard - which is exactly how 8 stranded Bandhu logbook
    entries stayed invisible until the first partner-covered run."""

    def test_fetch_walks_next_links(self):
        from programs import ciprb_replay as CR
        pages = {
            'first': {'results': [{'_id': i} for i in range(1000)],
                      'next': 'https://kf/next2'},
            'https://kf/next2': {'results': [{'_id': 'tail'}], 'next': None},
        }

        class FakeResp:
            def __init__(self, payload):
                self._p = payload
            def raise_for_status(self):
                pass
            def json(self):
                return self._p

        def fake_get(url, headers=None, timeout=None):
            key = 'first' if '/assets/' in url else url
            return FakeResp(pages[key])

        with mock.patch.object(CR.requests, 'get', side_effect=fake_get):
            out = CR._fetch('uidX', 'token')
        self.assertEqual(len(out), 1001, 'the second page must be fetched')
        self.assertEqual(out[-1]['_id'], 'tail')

    def test_limit_still_caps_for_smoke_runs(self):
        from programs import ciprb_replay as CR

        class FakeResp:
            def raise_for_status(self):
                pass
            def json(self):
                return {'results': [{'_id': i} for i in range(50)], 'next': None}

        with mock.patch.object(CR.requests, 'get',
                               return_value=FakeResp()):
            out = CR._fetch('uidX', 'token', limit=30)
        self.assertEqual(len(out), 30)
