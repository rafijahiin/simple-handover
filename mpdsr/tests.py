import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from submissions.models import FormType, KoboSubmission, SubmissionStatus
from .models import DeathType, MPDSRCase, ReviewStatus

BASE_URL = '/api/mpdsr/cases/'


def make_user(email, org, role):
    return User.objects.create_user(
        email=email, password='pass', full_name='Test', organisation=org, role=role,
    )


def _rows(resp):
    """Return list of rows whether the response is paginated or a plain list."""
    data = resp.data
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


def make_submission(partner='PHD', kobo_id='m001', death_type='maternal'):
    # MPDSR sub-form raw_data keys are F1–F6 specific (see
    # MPDSRCaseManager.get_or_create_from_submission). Use the F2 form
    # shape so the manager populates cause_of_death + age_years from
    # the right keys.
    return KoboSubmission.objects.create(
        kobo_id=kobo_id,
        form_type=FormType.MPDSR,
        partner=partner,
        worker_name='Rina',
        district='Dhaka',
        region='Dhaka',
        submitted_at=timezone.now(),
        raw_data={
            'form_type': 'f2',
            'f2_death_type': death_type,
            'f2_cause_of_death': 'Hemorrhage',
            'f2_mother_age': '28',
        },
        status=SubmissionStatus.PENDING,
    )


def make_case(partner='PHD', status=ReviewStatus.REPORTED, death_type=DeathType.MATERNAL,
              committee_date=None, kobo_id=None):
    return MPDSRCase.objects.create(
        partner=partner,
        district='Dhaka',
        region='Dhaka',
        date_of_death=datetime.date.today(),
        death_type=death_type,
        cause_of_death='Hemorrhage',
        status=status,
        committee_date=committee_date,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class MPDSRCaseModelTest(TestCase):

    def test_case_hash_auto_generated_maternal(self):
        case = make_case()
        self.assertTrue(case.case_hash.startswith('MPDSR-PHD-MAT-'))

    def test_case_hash_perinatal(self):
        case = make_case(death_type=DeathType.PERINATAL)
        self.assertIn('-PER-', case.case_hash)

    def test_bondhu_hash_prefix(self):
        case = make_case(partner='Bandhu')
        self.assertIn('BON', case.case_hash)

    def test_str_contains_case_hash(self):
        case = make_case()
        self.assertIn('MPDSR-', str(case))

    def test_is_overdue_committee_past_date(self):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        case = make_case(status=ReviewStatus.COMMITTEE_REVIEW, committee_date=yesterday)
        self.assertTrue(case.is_overdue_committee)

    def test_is_overdue_committee_future_date(self):
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        case = make_case(committee_date=tomorrow)
        self.assertFalse(case.is_overdue_committee)

    def test_is_overdue_committee_no_date(self):
        case = make_case()
        self.assertFalse(case.is_overdue_committee)

    def test_closed_never_overdue(self):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        case = make_case(status=ReviewStatus.CLOSED, committee_date=yesterday)
        self.assertFalse(case.is_overdue_committee)


# ---------------------------------------------------------------------------
# get_or_create_from_submission
# ---------------------------------------------------------------------------

class FromSubmissionTest(TestCase):

    def test_creates_case_from_submission(self):
        sub = make_submission()
        case, created = MPDSRCase.objects.get_or_create_from_submission(sub)
        self.assertTrue(created)
        self.assertEqual(case.partner, 'PHD')
        self.assertEqual(case.district, 'Dhaka')
        self.assertEqual(case.status, ReviewStatus.REPORTED)
        self.assertEqual(case.cause_of_death, 'Hemorrhage')
        self.assertEqual(case.age_years, 28)

    def test_idempotent_get_or_create(self):
        sub = make_submission(kobo_id='m002')
        _, created1 = MPDSRCase.objects.get_or_create_from_submission(sub)
        _, created2 = MPDSRCase.objects.get_or_create_from_submission(sub)
        self.assertTrue(created1)
        self.assertFalse(created2)

    def test_perinatal_death_type_detected(self):
        sub = make_submission(kobo_id='m003', death_type='perinatal')
        case, _ = MPDSRCase.objects.get_or_create_from_submission(sub)
        self.assertEqual(case.death_type, DeathType.PERINATAL)

    def test_missing_fields_handled_gracefully(self):
        sub = make_submission(kobo_id='m004')
        sub.raw_data = {}
        sub.save()
        case, _ = MPDSRCase.objects.get_or_create_from_submission(sub)
        self.assertEqual(case.cause_of_death, '')
        self.assertIsNone(case.age_years)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class MPDSRCaseAPITest(TestCase):
    """MPDSR is CIPRB-owned per the IDMS handoff — PHD/Bandhu managers
    receive 403 from CanAccessMPDSR. Tests that exercise the read/write
    paths therefore use a UNFPA supervisor (full cross-org access)."""

    def setUp(self):
        self.client = APIClient()
        self.supervisor = make_user('s@unfpa.org', Organisation.UNFPA, Role.SUPERVISOR)
        self.phd_mgr = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)
        self.bondhu_mgr = make_user('bm@bandhu.org', Organisation.BANDHU, Role.MANAGER)

    def test_unauthenticated_returns_403(self):
        resp = self.client.get(BASE_URL)
        self.assertEqual(resp.status_code, 403)

    def test_phd_manager_blocked_from_mpdsr(self):
        # MPDSR is CIPRB-owned — partner managers get 403.
        make_case(partner='PHD', kobo_id='a1')
        self.client.force_authenticate(user=self.phd_mgr)
        resp = self.client.get(BASE_URL)
        self.assertEqual(resp.status_code, 403)

    def test_bondhu_manager_blocked_from_mpdsr(self):
        self.client.force_authenticate(user=self.bondhu_mgr)
        resp = self.client.get(BASE_URL)
        self.assertEqual(resp.status_code, 403)

    def test_supervisor_sees_all_cases(self):
        make_case(partner='PHD', kobo_id='a1')
        make_case(partner='Bandhu', kobo_id='a2')
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.get(BASE_URL)
        self.assertEqual(resp.status_code, 200)
        rows = _rows(resp)
        self.assertEqual(len(rows), 2)

    def test_patch_updates_status(self):
        case = make_case(partner='PHD')
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.patch(
            f'{BASE_URL}{case.id}/',
            {'status': ReviewStatus.UNDER_REVIEW},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        case.refresh_from_db()
        self.assertEqual(case.status, ReviewStatus.UNDER_REVIEW)

    def test_patch_past_committee_date_rejected(self):
        case = make_case(partner='PHD')
        yesterday = str(datetime.date.today() - datetime.timedelta(days=1))
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.patch(
            f'{BASE_URL}{case.id}/',
            {'committee_date': yesterday},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_not_allowed(self):
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.post(BASE_URL, {}, format='json')
        self.assertEqual(resp.status_code, 405)

    def test_delete_not_allowed(self):
        case = make_case(partner='PHD')
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.delete(f'{BASE_URL}{case.id}/')
        self.assertEqual(resp.status_code, 405)


# ---------------------------------------------------------------------------
# Stats endpoint
# ---------------------------------------------------------------------------

class StatsEndpointTest(TestCase):
    """MPDSR is CIPRB-owned (CanAccessMPDSR). Stats endpoint is exercised
    via a UNFPA supervisor with cross-org visibility."""

    def setUp(self):
        self.client = APIClient()
        self.supervisor = make_user('s@unfpa.org', Organisation.UNFPA, Role.SUPERVISOR)

    def test_stats_keys_present(self):
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.get(f'{BASE_URL}stats/')
        self.assertEqual(resp.status_code, 200)
        for key in ('total', 'by_status', 'by_death_type', 'overdue_committee', 'this_month'):
            self.assertIn(key, resp.data)

    def test_stats_counts_correctly(self):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        make_case(partner='PHD', status=ReviewStatus.REPORTED, kobo_id='s1')
        make_case(partner='PHD', status=ReviewStatus.CLOSED, kobo_id='s2')
        make_case(
            partner='PHD',
            status=ReviewStatus.COMMITTEE_REVIEW,
            committee_date=yesterday,
            kobo_id='s3',
        )
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.get(f'{BASE_URL}stats/')
        self.assertEqual(resp.data['total'], 3)
        self.assertEqual(resp.data['by_status']['reported'], 1)
        self.assertEqual(resp.data['by_status']['closed'], 1)
        self.assertEqual(resp.data['overdue_committee'], 1)

    def test_stats_org_isolated(self):
        # Supervisor has cross-org access — applying ?partner=PHD filter
        # restricts the dataset; a Bandhu-only record is excluded.
        make_case(partner='Bandhu')
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.get(f'{BASE_URL}stats/?partner=PHD')
        self.assertEqual(resp.data['total'], 0)


class MaternalReportingRateTest(TestCase):
    """RCH's ask (Dr Tanjina, 6 Sep 2026): each district's reported maternal
    deaths against the 2026 projection.

    The numerator has to be the notification slip. A death commonly carries
    both a community and a facility review, so counting reviews would put
    districts over a hundred per cent for a reason that has nothing to do with
    reporting performance."""

    def setUp(self):
        import datetime
        from mpdsr.ciprb_models import MPDSRDeathNotification
        from mpdsr.models import MPDSRDistrictDenominator
        self.dod = datetime.date(2026, 3, 4)
        self.client = APIClient()
        self.user = make_user('rate@unfpa.org', Organisation.UNFPA, Role.SUPERVISOR)
        self.client.force_authenticate(user=self.user)

        MPDSRDistrictDenominator.objects.create(district='Sunamganj',
                                                project_deaths_md=99)
        MPDSRDistrictDenominator.objects.create(district='Bhola',
                                                project_deaths_md=46)
        # A CIPRB district that is expected to see deaths and has reported none.
        MPDSRDistrictDenominator.objects.create(district='Barguna',
                                                project_deaths_md=34)
        # Bogura is in RCH's projection file but is not a CIPRB working
        # district, so it must not appear as a reporting failure.
        MPDSRDistrictDenominator.objects.create(district='Bogura',
                                                project_deaths_md=97)

        for i in range(3):
            MPDSRDeathNotification.objects.create(
                case_serial='S%d' % i, district='Sunamganj',
                death_kind='maternal', approval_status='APPROVED',
                date_of_death=self.dod)
        MPDSRDeathNotification.objects.create(
            case_serial='B1', district='Bhola', death_kind='maternal',
            approval_status='APPROVED', date_of_death=self.dod)
        # Neither of these should reach the maternal panel.
        MPDSRDeathNotification.objects.create(
            case_serial='N1', district='Sunamganj', death_kind='neonatal',
            approval_status='APPROVED', date_of_death=self.dod)
        MPDSRDeathNotification.objects.create(
            case_serial='P1', district='Sunamganj', death_kind='maternal',
            approval_status='PENDING', date_of_death=self.dod)

    def _rows(self):
        r = self.client.get('/api/mpdsr/aggregates/')
        self.assertEqual(r.status_code, 200)
        return {x['district']: x for x in r.json()['maternal_reporting']['rows']}

    def test_counts_maternal_slips_only(self):
        rows = self._rows()
        self.assertEqual(rows['Sunamganj']['reported'], 3)
        self.assertEqual(rows['Bhola']['reported'], 1)

    def test_percentage_is_reported_over_projected(self):
        rows = self._rows()
        self.assertEqual(rows['Sunamganj']['projected'], 99)
        self.assertEqual(rows['Sunamganj']['pct'], round(3 / 99 * 100, 1))
        self.assertEqual(rows['Bhola']['pct'], round(1 / 46 * 100, 1))

    def test_a_district_that_reported_nothing_is_still_listed(self):
        rows = self._rows()
        self.assertIn('Barguna', rows)
        self.assertEqual(rows['Barguna']['reported'], 0)
        self.assertEqual(rows['Barguna']['pct'], 0.0)

    def test_districts_outside_the_ciprb_footprint_are_excluded(self):
        # RCH's file covers districts CIPRB does not work in. Listing them at
        # zero would read as a reporting failure rather than an absence of
        # programme.
        self.assertNotIn('Bogura', self._rows())

    def test_the_mirrored_district_list_matches_the_kobo_forms(self):
        # The list the API filters on is a mirror of the one the field forms
        # offer. If they drift, a district silently vanishes from this panel.
        from mpdsr.ciprb_districts import CIPRB_DISTRICTS as MIRROR
        from programs.management.commands.build_ciprb_forms import CIPRB_DISTRICTS
        self.assertEqual(list(MIRROR), list(CIPRB_DISTRICTS))

    def test_totals_match_the_rows(self):
        r = self.client.get('/api/mpdsr/aggregates/').json()['maternal_reporting']
        self.assertEqual(r['reported_total'], sum(x['reported'] for x in r['rows']))
        self.assertEqual(r['projected_total'],
                         sum(x['projected'] or 0 for x in r['rows']))
