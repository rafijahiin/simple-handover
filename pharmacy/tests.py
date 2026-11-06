"""
Pharmacy module tests — Step 6.

Verifies the hard-coded drug-quantity caps at every enforcement layer:
  - PrescriptionRecord.clean() / .save() — model
  - PrescriptionRecordSerializer.validate() — API
  - Bulk parametric sweep over every (drug, condition) pair so a future
    re-tune of DRUG_LIMITS keeps the matrix in sync with this test.
"""
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from partners.models import Partner
from programs.models import ServiceCenter
from pharmacy.models import (
    ApprovalStatus, ConditionType, Drug, DRUG_LIMITS,
    PrescriptionRecord, max_quantity_for,
)
from pharmacy.serializers import PrescriptionRecordSerializer


def _make_user(email, org, role):
    return User.objects.create_user(
        email=email, password='x', full_name='T',
        organisation=org, role=role,
    )


class DrugLimitsLookupTest(TestCase):
    """max_quantity_for() returns the spec'd cap for every drug pairing."""

    def test_metronidazole_caps(self):
        self.assertEqual(max_quantity_for(Drug.METRONIDAZOLE, ConditionType.STI),
                         (14, 'tablets'))
        self.assertEqual(max_quantity_for(Drug.METRONIDAZOLE, ConditionType.GENERAL),
                         (10, 'tablets'))

    def test_doxycycline_caps(self):
        self.assertEqual(max_quantity_for(Drug.DOXYCYCLINE, ConditionType.STI),
                         (20, 'capsules'))
        self.assertEqual(max_quantity_for(Drug.DOXYCYCLINE, ConditionType.GENERAL),
                         (10, 'capsules'))

    def test_single_limit_drugs(self):
        for drug in (Drug.B_COMPLEX, Drug.IBUPROFEN, Drug.PARACETAMOL,
                     Drug.RANITIDINE, Drug.ANTACID):
            self.assertEqual(max_quantity_for(drug, ConditionType.STI),
                             (10, 'tablets'))
            self.assertEqual(max_quantity_for(drug, ConditionType.GENERAL),
                             (10, 'tablets'))

    def test_ors_caps(self):
        self.assertEqual(max_quantity_for(Drug.ORS, ConditionType.GENERAL),
                         (3, 'sachets'))
        self.assertEqual(max_quantity_for(Drug.ORS, ConditionType.SEVERE),
                         (5, 'sachets'))

    def test_unknown_drug_raises(self):
        with self.assertRaises(ValidationError):
            max_quantity_for('bogus_drug', ConditionType.GENERAL)


class PrescriptionRecordModelTest(TestCase):

    def setUp(self):
        self.partner = Partner.objects.get(code='PHD')
        self.center = ServiceCenter.objects.create(
            organisation='PHD', name='Daulatdia Brothel Centre', code='PHD-001',
            center_type='BROTHEL', district='Rajbari', upazila='Goalondo',
        )
        self.user = _make_user('p@phd.org', Organisation.PHD, Role.MANAGER)

    def _rx(self, drug, qty, condition=ConditionType.GENERAL):
        return PrescriptionRecord(
            client_id='C-001',
            partner=self.partner,
            center=self.center,
            prescribed_by=self.user,
            date=date.today(),
            drug=drug,
            quantity=qty,
            condition_type=condition,
        )

    def test_under_cap_saves(self):
        rx = self._rx(Drug.METRONIDAZOLE, 14, ConditionType.STI)
        rx.save()
        self.assertEqual(PrescriptionRecord.objects.count(), 1)

    def test_over_cap_raises_metronidazole_general(self):
        rx = self._rx(Drug.METRONIDAZOLE, 11, ConditionType.GENERAL)
        with self.assertRaises(ValidationError) as cm:
            rx.save()
        self.assertIn('quantity', cm.exception.message_dict)
        self.assertIn('capped at 10', str(cm.exception))

    def test_over_cap_raises_metronidazole_sti(self):
        rx = self._rx(Drug.METRONIDAZOLE, 15, ConditionType.STI)
        with self.assertRaises(ValidationError):
            rx.save()

    def test_over_cap_raises_doxycycline_sti(self):
        rx = self._rx(Drug.DOXYCYCLINE, 21, ConditionType.STI)
        with self.assertRaises(ValidationError):
            rx.save()

    def test_doxycycline_general_capped_at_10(self):
        rx_ok = self._rx(Drug.DOXYCYCLINE, 10, ConditionType.GENERAL)
        rx_ok.save()
        rx_bad = self._rx(Drug.DOXYCYCLINE, 11, ConditionType.GENERAL)
        with self.assertRaises(ValidationError):
            rx_bad.save()

    def test_single_limit_drugs_capped_at_10(self):
        for drug in (Drug.B_COMPLEX, Drug.IBUPROFEN, Drug.PARACETAMOL,
                     Drug.RANITIDINE, Drug.ANTACID):
            self._rx(drug, 10).save()  # cap = exactly OK
            with self.assertRaises(ValidationError, msg=f'{drug} over cap'):
                self._rx(drug, 11).save()

    def test_ors_severe_allows_5(self):
        self._rx(Drug.ORS, 5, ConditionType.SEVERE).save()

    def test_ors_severe_blocks_6(self):
        with self.assertRaises(ValidationError):
            self._rx(Drug.ORS, 6, ConditionType.SEVERE).save()

    def test_ors_general_caps_at_3(self):
        with self.assertRaises(ValidationError):
            self._rx(Drug.ORS, 4, ConditionType.GENERAL).save()

    def test_zero_quantity_rejected(self):
        with self.assertRaises(ValidationError):
            self._rx(Drug.PARACETAMOL, 0).save()


class PrescriptionRecordSerializerTest(TestCase):
    """Serializer layer applies the same cap as the model."""

    def setUp(self):
        self.partner = Partner.objects.get(code='Bandhu')
        self.center = ServiceCenter.objects.create(
            organisation='Bandhu', name='Dhaka KP DIC', code='BAN-001',
            center_type='DIC', district='Dhaka', upazila='Dhanmondi',
        )

    def _payload(self, **overrides):
        base = {
            'client_id': 'KP-9001',
            'partner': self.partner.id,
            'center': self.center.id,
            'date': str(date.today()),
            'drug': Drug.METRONIDAZOLE,
            'quantity': 10,
            'condition_type': ConditionType.GENERAL,
        }
        base.update(overrides)
        return base

    def test_under_cap_valid(self):
        ser = PrescriptionRecordSerializer(data=self._payload())
        self.assertTrue(ser.is_valid(), msg=str(ser.errors))

    def test_over_cap_invalid_message_mentions_cap(self):
        ser = PrescriptionRecordSerializer(data=self._payload(quantity=11))
        self.assertFalse(ser.is_valid())
        self.assertIn('quantity', ser.errors)
        self.assertIn('capped at 10', str(ser.errors['quantity']))

    def test_doxycycline_sti_20_ok(self):
        ser = PrescriptionRecordSerializer(data=self._payload(
            drug=Drug.DOXYCYCLINE, condition_type=ConditionType.STI, quantity=20,
        ))
        self.assertTrue(ser.is_valid(), msg=str(ser.errors))

    def test_doxycycline_sti_21_rejected(self):
        ser = PrescriptionRecordSerializer(data=self._payload(
            drug=Drug.DOXYCYCLINE, condition_type=ConditionType.STI, quantity=21,
        ))
        self.assertFalse(ser.is_valid())
        self.assertIn('quantity', ser.errors)

    def test_zero_quantity_rejected(self):
        ser = PrescriptionRecordSerializer(data=self._payload(quantity=0))
        self.assertFalse(ser.is_valid())


class PrescriptionRecordAPITest(TestCase):
    """End-to-end API exercise — the cap holds via the live URL route."""

    def setUp(self):
        self.client = APIClient()
        self.partner = Partner.objects.get(code='PHD')
        self.center = ServiceCenter.objects.create(
            organisation='PHD', name='Brothel Centre A', code='PHD-A',
            center_type='BROTHEL', district='Rajbari', upazila='Goalondo',
        )
        self.user = _make_user('phd-mgr@phd.org', Organisation.PHD, Role.MANAGER)
        self.client.force_authenticate(user=self.user)

    def _payload(self, **overrides):
        base = {
            'client_id': 'FSW-101',
            'partner': str(self.partner.id),
            'center': str(self.center.id),
            'date': str(date.today()),
            'drug': Drug.METRONIDAZOLE,
            'condition_type': ConditionType.STI,
            'quantity': 14,
        }
        base.update(overrides)
        return base

    def test_post_at_cap_succeeds(self):
        resp = self.client.post(
            '/api/pharmacy/prescriptions/',
            self._payload(quantity=14),
            format='json',
        )
        self.assertEqual(resp.status_code, 201, msg=str(resp.data))

    def test_post_over_cap_returns_400(self):
        resp = self.client.post(
            '/api/pharmacy/prescriptions/',
            self._payload(quantity=15),
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('quantity', resp.data)
