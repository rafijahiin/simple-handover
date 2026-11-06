import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from .models import TrainingAttendance, TrainingSession, ParticipantRole

BASE_URL = '/api/training/sessions/'


def make_user(email, org, role):
    return User.objects.create_user(
        email=email, password='pass', full_name='Test', organisation=org, role=role,
    )


def make_session(partner='PHD', topic='MPDSR Training', expected=10):
    return TrainingSession.objects.create(
        partner=partner,
        district='Dhaka',
        region='Dhaka',
        topic=topic,
        facilitator='Dr. Rahman',
        date=datetime.date.today(),
        expected_participants=expected,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TrainingSessionModelTest(TestCase):

    def test_actual_participants_counts_attended(self):
        session = make_session()
        TrainingAttendance.objects.create(
            session=session, participant_name='Rina', role=ParticipantRole.COMMUNITY_WORKER, attended=True)
        TrainingAttendance.objects.create(
            session=session, participant_name='Mita', role=ParticipantRole.COMMUNITY_WORKER, attended=False)
        self.assertEqual(session.actual_participants, 1)

    def test_attendance_rate_calculated(self):
        session = make_session(expected=10)
        for i in range(8):
            TrainingAttendance.objects.create(
                session=session, participant_name=f'P{i}',
                role=ParticipantRole.COMMUNITY_WORKER, attended=True)
        self.assertEqual(session.attendance_rate, 80.0)

    def test_attendance_rate_none_when_no_expected(self):
        session = make_session(expected=0)
        self.assertIsNone(session.attendance_rate)

    def test_str_contains_topic(self):
        session = make_session(topic='Fistula Awareness')
        self.assertIn('Fistula Awareness', str(session))


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class TrainingSessionAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)
        self.bondhu = make_user('bm@bandhu.org', Organisation.BANDHU, Role.MANAGER)

    def test_unauthenticated_returns_403(self):
        resp = self.client.get(BASE_URL)
        self.assertEqual(resp.status_code, 403)

    def test_org_isolation(self):
        make_session(partner='PHD')
        make_session(partner='Bandhu')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(BASE_URL)
        rows = resp.data if isinstance(resp.data, list) else resp.data['results']
        self.assertEqual(len(rows), 1)

    def test_create_session(self):
        self.client.force_authenticate(user=self.phd)
        resp = self.client.post(BASE_URL, {
            'partner': 'PHD',
            'district': 'Dhaka',
            'region': 'Dhaka',
            'topic': 'Safe Motherhood',
            'date': str(datetime.date.today()),
            'expected_participants': 15,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(TrainingSession.objects.count(), 1)

    def test_add_attendance(self):
        session = make_session(partner='PHD')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.post(f'{BASE_URL}{session.id}/add_attendance/', {
            'participant_name': 'Rina Begum',
            'role': ParticipantRole.COMMUNITY_WORKER,
            'attended': True,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(session.attendances.count(), 1)

    def test_stats_endpoint(self):
        session = make_session(partner='PHD', expected=10)
        TrainingAttendance.objects.create(
            session=session, participant_name='P1',
            role=ParticipantRole.COMMUNITY_WORKER, attended=True)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}stats/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total_sessions'], 1)
        self.assertEqual(resp.data['total_participants_attended'], 1)
