import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from .duplicate_detector import check_new_survey, flag_duplicates_for_partner
from .models import BaselineSurvey, SurveyType

BASE_URL = '/api/baseline/surveys/'


def make_user(email, org, role):
    return User.objects.create_user(
        email=email, password='pass', full_name='Test', organisation=org, role=role,
    )


def make_survey(partner='PHD', survey_type=SurveyType.BASELINE,
                participant_code='P001', district='Dhaka', date=None):
    if date is None:
        date = datetime.date.today()
    return BaselineSurvey.objects.create(
        partner=partner,
        district=district,
        region='Dhaka',
        survey_type=survey_type,
        participant_code=participant_code,
        survey_date=date,
        raw_data={},
    )


def _rows(resp):
    """Return list of rows whether the response is paginated or a plain list."""
    data = resp.data
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


# ---------------------------------------------------------------------------
# Duplicate detection unit tests
# ---------------------------------------------------------------------------

class DuplicateDetectorTest(TestCase):

    def test_no_duplicates_when_unique(self):
        make_survey(participant_code='P001')
        make_survey(participant_code='P002')
        flagged = flag_duplicates_for_partner('PHD')
        self.assertEqual(flagged, 0)

    def test_flags_duplicate_same_participant(self):
        make_survey(participant_code='P001')
        make_survey(participant_code='P001')
        flagged = flag_duplicates_for_partner('PHD')
        self.assertEqual(flagged, 1)

    def test_different_survey_types_not_duplicate(self):
        make_survey(participant_code='P001', survey_type=SurveyType.BASELINE)
        make_survey(participant_code='P001', survey_type=SurveyType.ENDLINE)
        flagged = flag_duplicates_for_partner('PHD')
        self.assertEqual(flagged, 0)

    def test_check_new_survey_marks_duplicate(self):
        original = make_survey(participant_code='P001')
        new_survey = make_survey(participant_code='P001')
        is_dup = check_new_survey(new_survey)
        self.assertTrue(is_dup)
        new_survey.refresh_from_db()
        self.assertTrue(new_survey.is_duplicate)
        self.assertEqual(new_survey.duplicate_of, original)

    def test_empty_participant_code_never_flagged(self):
        make_survey(participant_code='')
        make_survey(participant_code='')
        flagged = flag_duplicates_for_partner('PHD')
        self.assertEqual(flagged, 0)


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class BaselineSurveyAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)
        self.bondhu = make_user('bm@bandhu.org', Organisation.BANDHU, Role.MANAGER)

    def test_unauthenticated_returns_403(self):
        resp = self.client.get(BASE_URL)
        self.assertEqual(resp.status_code, 403)

    def test_org_isolation(self):
        make_survey(partner='PHD')
        make_survey(partner='Bandhu')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(BASE_URL)
        self.assertEqual(len(_rows(resp)), 1)

    def test_filter_by_survey_type(self):
        make_survey(partner='PHD', survey_type=SurveyType.BASELINE, participant_code='P1')
        make_survey(partner='PHD', survey_type=SurveyType.ENDLINE, participant_code='P2')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}?survey_type=endline')
        self.assertEqual(len(_rows(resp)), 1)

    def test_stats_endpoint(self):
        make_survey(partner='PHD', survey_type=SurveyType.BASELINE, participant_code='P1')
        make_survey(partner='PHD', survey_type=SurveyType.ENDLINE, participant_code='P2')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}stats/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['total'], 2)
        self.assertEqual(resp.data['baseline'], 1)
        self.assertEqual(resp.data['endline'], 1)

    def test_scan_duplicates_action(self):
        make_survey(partner='PHD', participant_code='P001')
        make_survey(partner='PHD', participant_code='P001')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.post(f'{BASE_URL}scan_duplicates/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['flagged'], 1)


class DeriveFromKoboPayloadTest(TestCase):
    """Guards the three bugs that made the whole baseline dashboard read wrong:
    nested Kobo keys, a guessed population, and a dedup key pointing at a field
    the live forms never collect."""

    HIJRA = 'aBT7aCL9p4FGcW4WwXZcr6'
    FSW = 'aVsJ7VJ35k8GshpQpnXygC'

    def _payload(self, asset, **fields):
        # Exactly how Kobo serialises a grouped answer.
        raw = {'_xform_id_string': asset, '_id': 1}
        raw.update({f'grp_admin/{k}': v for k, v in fields.items()})
        return raw

    def test_population_comes_from_the_form_not_a_substring_guess(self):
        from .derive import derive_fields
        self.assertEqual(derive_fields(self._payload(self.FSW))['population'], 'fsw')
        self.assertEqual(derive_fields(self._payload(self.HIJRA))['population'], 'hijra')

    def test_unknown_form_yields_no_population_rather_than_a_default(self):
        from .derive import derive_fields
        self.assertIsNone(derive_fields({'_xform_id_string': 'someone_elses_form'})['population'])

    def test_grouped_fields_are_read_not_dropped(self):
        from .derive import derive_fields
        raw = self._payload(self.FSW, district='Khulna', site_code='S3')
        raw['grp_module9/c3'] = '1'
        raw['grp_fsw_a2/s1_age'] = 31
        d = derive_fields(raw)
        self.assertEqual(d['district'], 'Khulna')
        self.assertEqual(d['site_code'], 'S3')
        self.assertEqual(d['interview_outcome'], '1')
        self.assertEqual(d['age'], 31)

    def test_serial_uses_submission_id_the_field_the_forms_actually_collect(self):
        from .derive import derive_fields
        d = derive_fields(self._payload(self.HIJRA, submission_id='HJ-DHK-007'))
        self.assertEqual(d['serial'], 'HJ-DHK-007')

    def test_serial_falls_back_to_legacy_questionnaire_serial(self):
        from .derive import derive_fields
        d = derive_fields(self._payload(self.HIJRA, questionnaire_serial='OLD-1'))
        self.assertEqual(d['serial'], 'OLD-1')


class InterviewDurationTest(TestCase):
    """Duration is measured consent -> Submit. An enumerator who leaves the form
    open submits hours later, so the raw mean describes their working session,
    not the interview. The headline figure must exclude those."""

    class _Sub:
        status = 'approved'
        district = 'Dhaka'
        latitude = None
        longitude = None
        submitted_at = None

        def __init__(self, raw):
            self.raw_data = raw

    def _sub(self, start, end, dc='1'):
        return self._Sub({
            '_xform_id_string': 'aBT7aCL9p4FGcW4WwXZcr6',
            'grp_admin/population': 'hijra', 'grp_admin/dc_code': dc,
            'grp_admin/district': 'Dhaka', 'grp_module9/c3': '1',
            'interview_start': start, 'interview_end': end,
        })

    def setUp(self):
        self.subs = [
            self._sub('2026-07-10T09:00:00', '2026-07-10T09:50:00'),  # 50m
            self._sub('2026-07-10T11:00:00', '2026-07-10T11:54:00'),  # 54m
            self._sub('2026-07-10T09:00:00', '2026-07-10T18:00:00'),  # 540m, left open
        ]

    def test_headline_average_excludes_forms_left_open(self):
        from .monitoring import compute_monitoring
        d = compute_monitoring(self.subs)['duration']
        self.assertEqual(d['interview_avg_min'], 52.0)   # (50 + 54) / 2
        self.assertEqual(d['interview_n'], 2)

    def test_raw_average_is_kept_so_the_exclusion_stays_inspectable(self):
        from .monitoring import compute_monitoring
        self.assertEqual(compute_monitoring(self.subs)['duration']['avg_min'], 214.7)

    def test_enumerator_average_excludes_their_left_open_forms(self):
        from .monitoring import compute_monitoring
        m = compute_monitoring(self.subs)
        row = m['collectors'][0]
        self.assertEqual(row['avg_min'], 52.0)
        self.assertEqual(row['long'], 1)
        self.assertEqual(row['n'], 3)


class InterviewEndSourceTest(TestCase):
    """The end of the interview is stamped at the outcome question
    (interview_end_actual), NOT at Submit. A form left in draft for hours must
    still read its real length; only rows lacking the stamp fall back to submit
    time and can be flagged 'left open'."""

    class _Sub:
        status = 'approved'; district = 'Dhaka'; latitude = 23.8; longitude = 90.4
        submitted_at = None

        def __init__(self, raw):
            self.raw_data = raw

    def _row(self, start, actual, submit):
        raw = {'_xform_id_string': 'aBT7aCL9p4FGcW4WwXZcr6',
               'grp_admin/population': 'hijra', 'grp_admin/dc_code': '1',
               'grp_admin/district': 'Dhaka', 'grp_module9/c3': '1',
               'interview_start': start, 'interview_end': submit}
        if actual:
            raw['interview_end_actual'] = actual
        return self._Sub(raw)

    def test_draft_lag_is_ignored_when_the_true_end_is_present(self):
        from .monitoring import compute_monitoring
        # 50m interview, submitted 8 hours later.
        d = compute_monitoring([
            self._row('2026-07-11T09:00:00', '2026-07-11T09:50:00', '2026-07-11T17:50:00'),
        ])['duration']
        self.assertEqual(d['interview_avg_min'], 50.0)
        self.assertEqual(d['true_end_n'], 1)

    def test_true_end_row_is_not_flagged_left_open(self):
        from .monitoring import compute_monitoring
        m = compute_monitoring([
            self._row('2026-07-11T09:00:00', '2026-07-11T09:50:00', '2026-07-11T17:50:00'),
        ])
        self.assertEqual(m['quality']['long_interviews'], 0)

    def test_legacy_row_without_true_end_falls_back_and_can_flag(self):
        from .monitoring import compute_monitoring
        m = compute_monitoring([
            self._row('2026-07-11T09:00:00', None, '2026-07-11T18:00:00'),  # 9h, no stamp
        ])
        self.assertEqual(m['duration']['true_end_n'], 0)
        self.assertEqual(m['quality']['long_interviews'], 1)
        self.assertIsNone(m['duration']['interview_avg_min'])  # excluded, nothing left


class MonitoringFilterAndTimingTest(TestCase):
    """Server-side monitoring filters + the valid-timing/median contract:
    missing end stays in the denominator, never becomes a duration; the median
    uses valid, non-extreme records only."""

    class _Sub:
        status = 'approved'
        district = 'Dhaka'
        latitude = None
        longitude = None
        submitted_at = None

        def __init__(self, raw):
            self.raw_data = raw

    def _sub(self, pop='hijra', dc='1', start='2026-07-10T09:00:00',
             actual='2026-07-10T09:50:00', site='S1', ver='vNEW'):
        uid = 'aBT7aCL9p4FGcW4WwXZcr6' if pop == 'hijra' else 'aVsJ7VJ35k8GshpQpnXygC'
        raw = {'_xform_id_string': uid, '__version__': ver,
               'grp_admin/population': pop, 'grp_admin/dc_code': dc,
               'grp_admin/district': 'Dhaka', 'grp_admin/site_code': site,
               'grp_module9/c3': '1',
               'interview_start': start, 'interview_end': '2026-07-10T20:00:00'}
        if actual:
            raw['interview_end_actual'] = actual
        return self._Sub(raw)

    def setUp(self):
        self.subs = [
            self._sub(),                                          # 50m valid
            self._sub(start='2026-07-11T10:00:00',
                      actual='2026-07-11T10:40:00'),              # 40m valid
            self._sub(start='2026-07-11T12:00:00',
                      actual='2026-07-11T18:40:00'),              # 400m valid-but-extreme
            self._sub(actual=None, ver='vOLD'),                   # missing end
            self._sub(pop='fsw', dc='1', site='S9'),              # 50m valid, FSW
        ]

    def test_valid_timing_keeps_missing_end_in_denominator(self):
        from .monitoring import compute_monitoring
        d = compute_monitoring(self.subs)['duration']
        self.assertEqual(d['valid_timing_n'], 4)       # 4 of 5 have usable start+end
        self.assertEqual(d['valid_timing_pct'], 80.0)  # denominator = ALL 5
        self.assertEqual(d['valid_median_n'], 3)       # extreme excluded from median
        self.assertEqual(d['valid_median_min'], 50.0)

    def test_population_filter(self):
        from .monitoring import compute_monitoring
        m = compute_monitoring(self.subs, filters={'population': 'fsw'})
        self.assertEqual(m['total'], 1)

    def test_enumerator_filter_uses_roster_name(self):
        from .monitoring import compute_monitoring
        m = compute_monitoring(self.subs,
                               filters={'enumerator': 'Md. Abdullah-Al-Mahbub'})
        self.assertEqual(m['total'], 4)   # the 4 hijra rows (dc 1)

    def test_date_and_version_filters(self):
        from .monitoring import compute_monitoring
        m = compute_monitoring(self.subs, filters={'date_from': '2026-07-11',
                                                   'date_to': '2026-07-11'})
        self.assertEqual(m['total'], 2)
        m2 = compute_monitoring(self.subs, filters={'version': 'vOLD'})
        self.assertEqual(m2['total'], 1)

    def test_collector_rows_carry_valid_timing_and_median(self):
        from .monitoring import compute_monitoring
        row = [c for c in compute_monitoring(self.subs)['collectors']
               if c['code'] == 'Md. Abdullah-Al-Mahbub'][0]
        self.assertEqual(row['n'], 4)
        self.assertEqual(row['valid_timing'], 3)
        self.assertEqual(row['valid_timing_pct'], 75)
        self.assertEqual(row['median_min'], 45.0)      # median of 50, 40
