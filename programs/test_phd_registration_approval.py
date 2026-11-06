"""PHD FSW registration now requires manager approval, WITHOUT blocking field
service logging.

Spec (Rafi, 2026-06-29):
  - An FSW registration must land PENDING so a PHD manager approves the
    registration record in the website queue (it no longer auto-approves).
  - But the field must be able to log services for that FSW immediately —
    she flows into phd_clients.csv while still PENDING, so the Service Log's
    pulldata() finds her before the manager acts.
  - A REJECTED registration drops back out of the CSV (stops being loggable).
"""
from django.test import TestCase

from programs.phd_handlers import handle_phd_registration
from programs.models import ServiceCenter, Client
from programs.management.commands.export_phd_clients import build_csv


def _phd_center():
    return ServiceCenter.objects.create(
        organisation='PHD', name='PHD Center 1', code='PHD-001',
        center_type=ServiceCenter.DIC, district='Dhaka', is_active=True,
    )


def _register(id_no, name, kobo_id):
    payload = {
        'center_code': 'PHD-001',
        'id_no': id_no,
        'name': name,
        '_id': kobo_id,
        '_submitted_by': 'phd_field_worker',
    }
    return handle_phd_registration(payload, lat=23.7, lng=90.4)


class PhdRegistrationApprovalTest(TestCase):
    def setUp(self):
        self.center = _phd_center()

    def test_registration_lands_pending(self):
        # Act
        resp = _register('1-0001', 'Rina', '5001')
        # Assert
        self.assertEqual(resp.status_code, 201)
        c = Client.objects.get(client_id='1-0001')
        self.assertEqual(c.approval_status, Client.PENDING)
        self.assertEqual(c.name, 'Rina')

    def test_pending_client_is_loggable_immediately(self):
        # Arrange / Act — register, do NOT approve
        _register('1-0001', 'Rina', '5001')
        csv_bytes, count = build_csv()
        # Assert — she is in the Service Log lookup even while PENDING
        self.assertIn('1-0001', csv_bytes.decode('utf-8'))
        self.assertEqual(count, 1)

    def test_rejected_client_drops_out_of_csv(self):
        # Arrange
        _register('1-0001', 'Rina', '5001')
        c = Client.objects.get(client_id='1-0001')
        # Act — manager rejects the registration
        c.approval_status = Client.REJECTED
        c.save()
        # Assert — she stops being loggable
        csv_bytes, count = build_csv()
        self.assertNotIn('1-0001', csv_bytes.decode('utf-8'))
        self.assertEqual(count, 0)

    def test_stub_upgrade_also_lands_pending(self):
        # Arrange — a service log arrived first and made a nameless, auto-approved stub
        Client.objects.create(
            organisation='PHD', center=self.center, client_id='2-0002',
            name='', approval_status=Client.APPROVED,
        )
        # Act — the real registration upgrades the stub
        resp = _register('2-0002', 'Mita', '5002')
        # Assert — upgraded in place, now PENDING (manager must review), and loggable
        self.assertEqual(resp.status_code, 200)
        c = Client.objects.get(client_id='2-0002')
        self.assertEqual(c.name, 'Mita')
        self.assertEqual(c.approval_status, Client.PENDING)
        self.assertIn('2-0002', build_csv()[0].decode('utf-8'))
