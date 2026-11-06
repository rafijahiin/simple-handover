"""Bandhu two-stage approval: manager -> UNFPA, and a developer/super CANNOT
bypass the UNFPA stage-2 gate (regression for the 2026-06 self-approve bug)."""
import datetime

from django.test import TestCase

from accounts.models import Organisation, Role, User
from programs.models import ServiceCenter, OutreachSession
from programs.views import _apply_decision


def _user(email, org, role):
    return User.objects.create_user(
        email=email, password='x', full_name='T', organisation=org, role=role)


class TwoStageApprovalTest(TestCase):
    def setUp(self):
        self.centre = ServiceCenter.objects.create(
            organisation='Bandhu', name='DIC', code='BND-DIC-TS',
            center_type='DIC', district='Dhaka')
        self.mgr = _user('m@bandhu', Organisation.BANDHU, Role.MANAGER)
        self.unfpa = _user('u@unfpa', Organisation.UNFPA, Role.SUPERVISOR)
        self.dev = _user('d@dev', Organisation.UNFPA, Role.DEVELOPER)

    def _outreach(self):
        return OutreachSession.objects.create(
            organisation='Bandhu', center=self.centre,
            session_date=datetime.date.today(), peer_educator_name='PE')

    def test_full_two_stage_flow(self):
        o = self._outreach()
        self.assertEqual(o.approval_status, 'PENDING')
        self.assertIsNone(_apply_decision(o, self.mgr, 'approve', ''))   # stage 1
        self.assertEqual(o.approval_status, 'MANAGER_APPROVED')
        self.assertIsNone(_apply_decision(o, self.unfpa, 'approve', ''))  # stage 2
        self.assertEqual(o.approval_status, 'APPROVED')

    def test_developer_cannot_finalise_bandhu(self):
        # THE FIX: a developer may do stage 1 but must NOT close stage 2.
        o = self._outreach()
        _apply_decision(o, self.mgr, 'approve', '')          # -> MANAGER_APPROVED
        resp = _apply_decision(o, self.dev, 'approve', '')   # tries stage 2
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(o.approval_status, 'MANAGER_APPROVED')  # NOT approved

    def test_developer_can_do_stage1(self):
        o = self._outreach()
        self.assertIsNone(_apply_decision(o, self.dev, 'approve', ''))
        self.assertEqual(o.approval_status, 'MANAGER_APPROVED')

    def test_unfpa_cannot_do_stage1(self):
        o = self._outreach()
        resp = _apply_decision(o, self.unfpa, 'approve', '')
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(o.approval_status, 'PENDING')
