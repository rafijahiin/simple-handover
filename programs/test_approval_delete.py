"""Deleting from the approval queue: same authorisation, with a trail.

Bandhu asked for a delete alongside approve and reject (2026-08-26) so a record
that should never have been submitted can be removed without going into
KoboToolbox and leaving the row here still counted.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from programs.models import (Client, ClinicVisit, KoboWithdrawal, OutreachSession,
                             ServiceCenter)

User = get_user_model()
URL = '/api/programs/pending-approvals/'


def _centre(code='BND-DIC-08', org='Bandhu', district='Manikganj'):
    c, _ = ServiceCenter.objects.get_or_create(
        code=code, defaults={'name': 'WC', 'organisation': org,
                             'district': district})
    return c


def _user(name, org, role='manager'):
    """The user model logs in by email and has no username field."""
    return User.objects.create_user(email='%s@example.org' % name,
                                    password='x', full_name=name.title(),
                                    organisation=org, role=role)


def _outreach(centre, org='Bandhu'):
    return OutreachSession.objects.create(
        organisation=org, center=centre, session_date='2026-08-01',
        kobo_submission_id='555')


class DeleteFromQueueTests(TestCase):
    def setUp(self):
        self.centre = _centre()
        self.mgr = _user('bmgr', 'Bandhu')
        self.api = APIClient()
        self.api.force_authenticate(self.mgr)

    def _post(self, obj, action='delete', reason='duplicate entry'):
        return self.api.post(URL, {'id': str(obj.id),
                                   'model_type': 'outreach_session',
                                   'action': action, 'reason': reason},
                             format='json')

    def test_manager_can_delete_own_org_record(self):
        o = _outreach(self.centre)
        r = self._post(o)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(OutreachSession.objects.filter(pk=o.pk).exists())

    def test_deletion_is_recorded(self):
        o = _outreach(self.centre)
        self._post(o)
        e = KoboWithdrawal.objects.get()
        self.assertEqual(e.model_label, 'programs.OutreachSession')
        self.assertEqual(e.kobo_submission_id, '555')
        self.assertEqual(e.organisation, 'Bandhu')
        self.assertEqual(e.actor, 'bmgr@example.org')
        self.assertEqual(e.reason, 'duplicate entry')

    def test_another_orgs_record_is_refused(self):
        phd_centre = _centre('PHD-01', 'PHD', 'Rajbari')
        o = _outreach(phd_centre, org='PHD')
        r = self._post(o)
        self.assertEqual(r.status_code, 403)
        self.assertTrue(OutreachSession.objects.filter(pk=o.pk).exists())

    def test_field_staff_cannot_delete(self):
        o = _outreach(self.centre)
        api = APIClient()
        api.force_authenticate(_user('fs', 'Bandhu', role='field_staff'))
        r = api.post(URL, {'id': str(o.id), 'model_type': 'outreach_session',
                           'action': 'delete', 'reason': 'test'}, format='json')
        self.assertIn(r.status_code, (403, 404))
        self.assertTrue(OutreachSession.objects.filter(pk=o.pk).exists())

    def test_a_record_with_service_history_is_refused_not_orphaned(self):
        c = Client.objects.create(client_id='08-9001', organisation='Bandhu',
                                  center=self.centre, name='A',
                                  kobo_submission_id='777')
        ClinicVisit.objects.create(organisation='Bandhu', center=self.centre,
                                   client=c, visit_date='2026-08-01')
        r = self.api.post(URL, {'id': str(c.id), 'model_type': 'client_reg',
                                'action': 'delete', 'reason': 'test'},
                          format='json')
        self.assertEqual(r.status_code, 409)
        self.assertIn('service records', r.data['detail'])
        self.assertTrue(Client.objects.filter(pk=c.pk).exists())
        # A refusal must not leave a trail claiming the record was removed.
        self.assertEqual(KoboWithdrawal.objects.count(), 0)

    def test_it_works_for_every_partner_not_just_bandhu(self):
        """The rule is the approval rule: a manager acts on their own org."""
        phd_centre = _centre('PHD-01', 'PHD', 'Rajbari')
        o = _outreach(phd_centre, org='PHD')
        api = APIClient()
        api.force_authenticate(_user('pmgr', 'PHD'))
        r = api.post(URL, {'id': str(o.id), 'model_type': 'outreach_session',
                           'action': 'delete', 'reason': 'test'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(OutreachSession.objects.filter(pk=o.pk).exists())

    def test_a_developer_may_delete_any_org(self):
        phd_centre = _centre('PHD-01', 'PHD', 'Rajbari')
        o = _outreach(phd_centre, org='PHD')
        api = APIClient()
        api.force_authenticate(_user('dev', 'UNFPA', role='developer'))
        r = api.post(URL, {'id': str(o.id), 'model_type': 'outreach_session',
                           'action': 'delete', 'reason': 'test'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_a_reason_is_required(self):
        """Without it the trail says a record vanished but not why."""
        o = _outreach(self.centre)
        r = self._post(o, reason='   ')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(OutreachSession.objects.filter(pk=o.pk).exists())
        self.assertEqual(KoboWithdrawal.objects.count(), 0)

    def test_unknown_action_is_rejected(self):
        o = _outreach(self.centre)
        r = self._post(o, action='destroy')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(OutreachSession.objects.filter(pk=o.pk).exists())


class SimpleOnlyTests(TestCase):
    """The button removes the record from SIMPLE and nothing else.

    Rafi, 2026-08-26: the delete button works for SIMPLE only, not for Kobo.
    The KoboToolbox submission is the raw evidence of what was removed, and
    nothing re-imports it, so it stays. This test exists so that a later change
    cannot quietly add a Kobo deletion to this path.
    """

    def setUp(self):
        self.centre = _centre()
        self.api = APIClient()
        self.api.force_authenticate(_user('bmgr2', 'Bandhu'))

    def test_no_request_leaves_the_server(self):
        from unittest import mock
        o = _outreach(self.centre)
        with mock.patch('requests.request') as req, \
             mock.patch('requests.delete') as dele, \
             mock.patch('requests.post') as post:
            r = self.api.post(URL, {'id': str(o.id),
                                    'model_type': 'outreach_session',
                                    'action': 'delete', 'reason': 'wrong entry'},
                              format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(OutreachSession.objects.filter(pk=o.pk).exists())
        req.assert_not_called()
        dele.assert_not_called()
        post.assert_not_called()

    def test_the_kobo_id_is_kept_on_the_trail(self):
        """Kobo still holds the submission, so the trail records which one."""
        o = _outreach(self.centre)
        self.api.post(URL, {'id': str(o.id), 'model_type': 'outreach_session',
                            'action': 'delete', 'reason': 'wrong entry'},
                      format='json')
        self.assertEqual(KoboWithdrawal.objects.get().kobo_submission_id, '555')
