"""
Verbatim-form handler tests for the rebuilt CIPRB-6 Social Autopsy (and, later,
the notification slips). Confirms the meeting-report shape maps correctly onto
MPDSRCase sa_md without the death-date requirement the death-review path imposes.
"""
import datetime
from django.test import TestCase

from mpdsr.models import MPDSRCase, DeathType
from mpdsr.ciprb_models import MPDSRDeathNotification
from programs.ciprb_handlers import (handle_ciprb_social_autopsy,
                                     handle_ciprb_notification_slip_01,
                                     handle_ciprb_notification_slip_02)


def _sa_payload(**over):
    p = {
        'organisation': 'CIPRB',
        'sa_death_type': '1',
        'meeting_date': '2026-06-20',
        'district': 'dhaka',
        'upazila': 'Dhamrai',
        'union': 'Kushura',
        'ward': '3',
        'village': 'Boyra',
        'slip_number': 'SL-100',
        'deceased_name': 'Rahima',
        'age_years': '27',
        'age_months': '0',
        'age_days': '0',
        'sa_sex': '',
        'death_narrative': 'Bled heavily after home delivery; reached facility late.',
        'prevention_1': 'Earlier referral',
        'prevention_2': 'Skilled birth attendant',
        'decision_1': 'Orient TBAs',
        'members_male': '4',
        'members_female': '6',
        'pregnant_women': '2',
        'collector_name': 'Karim',
        'collector_designation': 'FWV',
        '_id': 'SA1',
        '_submitted_by': 'kobo',
    }
    p.update(over)
    return p


class SocialAutopsyHandlerTest(TestCase):
    def test_meeting_report_maps_to_mpdsr_case(self):
        r = handle_ciprb_social_autopsy(_sa_payload(), 23.7, 90.4)
        self.assertEqual(r.status_code, 200)
        c = MPDSRCase.objects.get(sub_form_type='sa_md')
        self.assertEqual(c.district, 'Dhaka')
        self.assertEqual(c.approval_status, 'PENDING')
        self.assertEqual(c.date_of_death, datetime.date(2026, 6, 20))   # meeting date stands in
        self.assertEqual(c.committee_date, datetime.date(2026, 6, 20))
        self.assertEqual(c.death_type, DeathType.MATERNAL)
        self.assertEqual(c.age_years, 27)
        self.assertIn('Bled heavily', c.notes)
        self.assertIn('Earlier referral', c.action_plan)
        self.assertIn('Decisions:', c.action_plan)
        self.assertIn('Orient TBAs', c.action_plan)
        # full submission preserved (name is PII-minimised out of columns)
        self.assertEqual(c.raw_payload['deceased_name'], 'Rahima')
        self.assertEqual(c.raw_payload['members_female'], '6')

    def test_stillbirth_code_maps_to_perinatal(self):
        handle_ciprb_social_autopsy(_sa_payload(sa_death_type='3', slip_number='SL-200', _id='SA2'), None, None)
        c = MPDSRCase.objects.get(case_hash='sa:SL-200')
        self.assertEqual(c.death_type, DeathType.PERINATAL)

    def test_resubmit_same_slip_updates_one_row(self):
        handle_ciprb_social_autopsy(_sa_payload(_id='SA1'), None, None)
        handle_ciprb_social_autopsy(_sa_payload(_id='SA1b', death_narrative='Revised narrative'), None, None)
        rows = MPDSRCase.objects.filter(sub_form_type='sa_md', case_hash='sa:SL-100')
        self.assertEqual(rows.count(), 1)
        self.assertIn('Revised narrative', rows.first().notes)

    def test_missing_meeting_date_rejected(self):
        r = handle_ciprb_social_autopsy(_sa_payload(meeting_date=''), None, None)
        self.assertEqual(r.status_code, 400)


def _slip01_payload(**over):
    p = {
        'organisation': 'CIPRB', 'case_serial': 'S-1', 'slip_date': '2026-06-19',
        'mother_reg_no': 'MR-1', 'dhis2_newborn_reg': 'NB-1',
        'death_kind': 'maternal', 'sex': '', 'mother_name': 'Rahima',
        'mother_age': '27', 'father_husband_name': 'Karim', 'para': 'X',
        'village': 'Boyra', 'union': 'Kushura', 'upazila': 'Dhamrai',
        'district': 'dhaka', 'family_mobile': '017xxxxxxxx',
        'death_date': '2026-06-18', 'death_time': '14:30',
        'delivery_date': '2026-06-18', 'delivery_time': '08:00',
        'place_of_death': 'govt_facility', 'place_of_delivery': 'home',
        'delivery_attendant': 'dai', 'collector_name': 'Sumi',
        'collector_designation': 'CHCP', 'collector_mobile': '018xxxxxxxx',
        'cc_name': 'Boyra CC', 'cc_code': 'CC-99',
        '_id': 'NS01', '_submitted_by': 'kobo',
    }
    p.update(over)
    return p


class NotificationSlip01Test(TestCase):
    def test_community_slip_maps_fields(self):
        r = handle_ciprb_notification_slip_01(_slip01_payload(), 23.7, 90.4)
        self.assertEqual(r.status_code, 200)
        n = MPDSRDeathNotification.objects.get(slip_variant=MPDSRDeathNotification.SLIP_01)
        self.assertEqual(n.district, 'Dhaka')
        self.assertEqual(n.deceased_name, 'Rahima')         # mother is the recorded subject
        self.assertEqual(n.deceased_age, 27)
        self.assertEqual(n.date_of_death, datetime.date(2026, 6, 18))
        self.assertEqual(n.notification_date, datetime.date(2026, 6, 19))
        self.assertEqual(n.death_kind, MPDSRDeathNotification.KIND_MATERNAL)
        self.assertEqual(n.place_of_death, MPDSRDeathNotification.PLACE_FACILITY)  # govt_facility→facility
        self.assertEqual(n.approval_status, 'PENDING')
        self.assertEqual(n.reporter_name, 'Sumi')
        # rich verbatim fields preserved in raw_payload
        self.assertEqual(n.raw_payload['cc_code'], 'CC-99')
        self.assertEqual(n.raw_payload['delivery_attendant'], 'dai')
        self.assertEqual(n.raw_payload['dhis2_newborn_reg'], 'NB-1')

    def test_on_the_way_maps_to_transit(self):
        handle_ciprb_notification_slip_01(_slip01_payload(place_of_death='on_the_way', _id='NS01b'), None, None)
        n = MPDSRDeathNotification.objects.get(slip_variant=MPDSRDeathNotification.SLIP_01)
        self.assertEqual(n.place_of_death, MPDSRDeathNotification.PLACE_TRANSIT)

    def test_missing_death_date_rejected(self):
        r = handle_ciprb_notification_slip_01(_slip01_payload(death_date=''), None, None)
        self.assertEqual(r.status_code, 400)


class NotificationSlip02Test(TestCase):
    def test_hospital_slip_maps_cause_and_variant(self):
        p = {
            'organisation': 'CIPRB', 'case_serial': 'H-1', 'slip_date': '2026-06-19',
            'hospital_reg_no': 'HR-1', 'ward_no': '3', 'bed_no': '12',
            'death_kind': 'neonatal', 'sex': 'boy', 'mother_name': 'Salma',
            'mother_age': '24', 'district': 'dhaka',
            'hospital_name': 'DMCH', 'admission_date': '2026-06-17',
            'admission_time': '09:00', 'diagnosis_admission': 'Sepsis',
            'death_date': '2026-06-18', 'death_time': '03:15',
            'cause_of_death': 'Neonatal sepsis', 'collector_name': 'Nipa',
            '_id': 'NS02', '_submitted_by': 'kobo',
        }
        r = handle_ciprb_notification_slip_02(p, None, None)
        self.assertEqual(r.status_code, 200)
        n = MPDSRDeathNotification.objects.get(slip_variant=MPDSRDeathNotification.SLIP_02)
        self.assertEqual(n.death_kind, MPDSRDeathNotification.KIND_NEONATAL)
        self.assertEqual(n.cause_brief, 'Neonatal sepsis')
        self.assertEqual(n.raw_payload['diagnosis_admission'], 'Sepsis')
        self.assertEqual(n.raw_payload['ward_no'], '3')
