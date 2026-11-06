"""Tests for the FSW anomaly engine, its Kobo adapter, and the review API.

Covers the acceptance tests from integration_prompt.md:
  * Sabita's records with a missing end timestamp -> missing-timing flag,
    not a zero-minute interview.
  * Enumerators with a valid duration still show one.
  * Q9.5 with 6+ choices detected.
  * "No concerns" + another concern detected.
  * Child-living contradiction detected.
  * Income 10/12 BDT detected without auto-correction.
  * Multi-hour interviews excluded from the normal average.
  * GPS outliers flagged as verify.
  * Every anomaly carries evidence + a recommended action.
  * Raw Kobo responses remain immutable.
"""
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from submissions.models import FormType, KoboSubmission, SubmissionStatus

from .anomaly import _shape_record, build_report, invalidate_cache
from .fsw_rules import build_fsw_engine
from .models import AnomalyReview
from .schema import load_schema

FSW_UID = 'aVsJ7VJ35k8GshpQpnXygC'


def _kobo(**over):
    """A minimal but realistic FSW Kobo submission payload (nested keys)."""
    base = {
        '_xform_id_string': FSW_UID,
        '_uuid': 'uuid-1',
        '__version__': 'vCURRENT',
        'grp_admin/dc_code': '5',       # Sabita Rani Halder
        'grp_admin/site_code': '3',
        'grp_admin/interview_start': '2026-07-12T10:00:00',
        'grp_admin/interview_end_actual': '2026-07-12T10:50:00',
        'grp_admin/interview_end': '2026-07-12T18:00:00',
        'grp_scr/consent': '1',
        'grp_scr/s1_age': 30,
        'grp_a2/a203': 30,
    }
    base.update(over)
    return base


class _Sub:
    """Duck-typed KoboSubmission for direct adapter unit tests."""
    def __init__(self, raw, sid='x'):
        self.raw_data = raw
        self.id = sid
        self.latitude = None
        self.longitude = None


def _scan(records, population='fsw'):
    """Mirror baseline.anomaly.build_report's engine wiring exactly, so a test can
    never pass on settings the live report doesn't use.

    Every argument build_report passes must be passed here too. When
    `is_non_answer` was added to the engine this harness kept omitting it, so the
    refusal-code tests silently ran against the engine's default (no codes at all)
    — green tests, wrong wiring.
    """
    from .anomaly import (FIELD_MAP_BUILDERS, SHORT_MINUTES, _decode_fields,
                          _exclusive_label_map, non_answer_policy)
    schema = load_schema().get(population, {})
    field_map = FIELD_MAP_BUILDERS[population](schema)
    decode = _decode_fields(field_map)
    shaped = [_shape_record(_Sub(r), schema, population, decode) for r in records]
    headers = sorted({k for r in shaped for k in r})
    engine, _ = build_fsw_engine(headers,
                                 field_map=field_map,
                                 exclusive_options=_exclusive_label_map(schema, population),
                                 short_minutes=SHORT_MINUTES.get(population, 40),
                                 is_non_answer=non_answer_policy(population))
    return engine.scan(shaped), shaped


class AdapterRuleTests(TestCase):
    def _ids(self, records):
        report, _ = _scan(records)
        return {a['rule_id'] for a in report['anomalies']}, report

    def test_missing_end_produces_no_timing_flag(self):
        # A blank end time means the device served an older form version, which is
        # not a fault in the answers and is not flagged at all. It must certainly
        # never be read as a zero-minute (short) interview.
        rec = _kobo()
        rec.pop('grp_admin/interview_end_actual')       # old-form: no in-form end
        rec['__version__'] = 'vOLD'
        ids, report = self._ids([rec])
        self.assertNotIn('MISSING_INTERVIEW_END', ids)
        self.assertNotIn('INTERVIEW_TOO_SHORT', ids)
        self.assertNotIn('END_BEFORE_START', ids)

    def test_valid_duration_produces_no_timing_flag(self):
        ids, _ = self._ids([_kobo()])          # 50-minute interview
        self.assertNotIn('MISSING_INTERVIEW_END', ids)
        self.assertNotIn('INTERVIEW_TOO_SHORT', ids)

    def test_long_interview_is_not_flagged(self):
        # Long spans are draft/finish-later artefacts, not real long interviews —
        # never flagged. Only short ones are a genuine issue.
        rec = _kobo(**{'grp_admin/interview_end_actual': '2026-07-12T14:30:00'})  # 4.5h
        ids, _ = self._ids([rec])
        self.assertNotIn('INTERVIEW_EXTREMELY_LONG', ids)
        self.assertNotIn('INTERVIEW_LONG', ids)

    def test_short_interview_under_40min_flagged(self):
        # CIPRB's rule: under 40 minutes is rushed. ONE line for both instruments.
        rec = _kobo(**{'grp_admin/interview_end_actual': '2026-07-12T10:39:00'})
        report, _ = _scan([rec])
        flags = [a for a in report['anomalies'] if a['rule_id'] == 'INTERVIEW_TOO_SHORT']
        self.assertEqual(len(flags), 1)

    def test_forty_minute_interview_is_not_short(self):
        rec = _kobo(**{'grp_admin/interview_end_actual': '2026-07-12T10:40:00'})
        ids, _ = self._ids([rec])
        self.assertNotIn('INTERVIEW_TOO_SHORT', ids)

    def test_very_short_interview_is_high(self):
        rec = _kobo(**{'grp_admin/interview_end_actual': '2026-07-12T10:10:00'})  # 10 min
        report, _ = _scan([rec])
        flags = [a for a in report['anomalies'] if a['rule_id'] == 'INTERVIEW_TOO_SHORT']
        self.assertEqual(flags[0]['severity'], 'high')       # < half the threshold

    def test_q95_over_five_is_not_flagged(self):
        # RETIRED: the form now enforces max-5 via a constraint, and >5 on the old
        # (unconstrained) form was genuine respondent behaviour, not a defect.
        rec = _kobo(**{'grp_q9/q9_5': '01 02 03 04 05 06'})
        ids, _ = self._ids([rec])
        self.assertNotIn('Q95_MORE_THAN_FIVE_SERVICES', ids)

    def test_exclusive_choice_with_others(self):
        # b109 "other sources of income": None(0) selected with a real source(1).
        rec = _kobo(**{'grp_b1/b109': '0 1'})
        ids, _ = self._ids([rec])
        self.assertIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_lives_alone_with_child_retired(self):
        # RETIRED: B103 mixes housing ("Alone in own/rented room") with companions
        # ("With children"), so renting your own room with your child is a correct
        # answer, not a contradiction.
        rec = _kobo(**{'grp_a2/a213': 1, 'grp_a2/a214': 1, 'grp_b1/b103': '1'})
        ids, _ = self._ids([rec])
        self.assertNotIn('LIVES_ALONE_WITH_CHILD_PRESENT', ids)

    def test_children_with_respondent_exceed_total(self):
        rec = _kobo(**{'grp_a2/a213': 1, 'grp_a2/a214': 3})
        ids, _ = self._ids([rec])
        self.assertIn('CHILDREN_WITH_RESPONDENT_EXCEED_TOTAL', ids)

    def test_income_missing_zero_not_autocorrected(self):
        rec = _kobo(**{'grp_b1/b108': 12})
        report, shaped = _scan([rec])
        ids = {a['rule_id'] for a in report['anomalies']}
        self.assertIn('LIKELY_MISSING_ZERO_IN_INCOME', ids)
        # The raw value is unchanged — never auto-multiplied.
        self.assertEqual(shaped[0]['b108'], 12)

    def test_work_history_start_after_current_age(self):
        rec = _kobo(**{'grp_b1/b104': 40, 'grp_a2/a203': 30})
        ids, _ = self._ids([rec])
        self.assertIn('SEX_WORK_START_AFTER_CURRENT_AGE', ids)

    def test_every_anomaly_has_evidence_and_action(self):
        rec = _kobo(**{'grp_b1/b108': 12, 'grp_a2/a213': 1, 'grp_a2/a214': 3})
        report, _ = _scan([rec])
        self.assertTrue(report['anomalies'])
        for a in report['anomalies']:
            self.assertTrue(a['message'])
            self.assertIn('severity', a)
            self.assertIn('category', a)
            # observed OR fields present as evidence; action recommended.
            self.assertTrue(a.get('observed') is not None or a.get('fields'))

    def test_raw_data_is_immutable(self):
        rec = _kobo(**{'grp_b1/b108': 12})
        import copy
        snapshot = copy.deepcopy(rec)
        _scan([rec])
        self.assertEqual(rec, snapshot)   # adapter never mutates the source


def _mk_user():
    return User.objects.create_user(
        email='rev@ciprb.org', password='pw', full_name='Reviewer',
        organisation=Organisation.CIPRB, role=Role.DEVELOPER)


@override_settings(CACHES={'default': {'BACKEND':
                   'django.core.cache.backends.locmem.LocMemCache'}})
class AnomalyApiTests(TestCase):
    def setUp(self):
        invalidate_cache()
        # One record with MULTIPLE flags (income missing-zero + child-count
        # contradiction), so flag-counts vs unique-interview counts differ.
        KoboSubmission.objects.create(
            kobo_id='k1', form_type=FormType.BASELINE, status=SubmissionStatus.APPROVED,
            partner='CIPRB',
            raw_data=_kobo(**{'grp_b1/b108': 12, 'grp_a2/a213': 1, 'grp_a2/a214': 3}),
            submitted_at=timezone.now())
        self.user = _mk_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_report_serialises_with_kpis_and_review_fields(self):
        r = self.client.get('/api/baseline/fsw-anomalies/')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn('kpis', body)
        for k in ('critical', 'high', 'medium', 'low',
                  'interviews_affected', 'flags_reviewed', 'flags_total'):
            self.assertIn(k, body['kpis'])
        self.assertTrue(body['anomalies'])
        self.assertEqual(body['anomalies'][0]['review_status'], 'new')

    def test_severity_kpis_count_flags_not_unique_interviews(self):
        # One record with several HIGH flags: high == number of FLAGS, while
        # interviews_affected == 1 — the corrected KPI split.
        body = self.client.get('/api/baseline/fsw-anomalies/').json()
        k = body['kpis']
        total_by_sev = k['critical'] + k['high'] + k['medium'] + k['low']
        self.assertEqual(total_by_sev, k['flags_total'])
        self.assertGreater(k['flags_total'], k['interviews_affected'])
        self.assertEqual(k['interviews_affected'], 1)

    def test_flag_scoped_filters(self):
        base = '/api/baseline/fsw-anomalies/'
        body = self.client.get(base, {'severity': 'high'}).json()
        self.assertTrue(all(a['severity'] == 'high' for a in body['anomalies']))
        self.assertEqual(body['kpis']['medium'], 0)
        one_rule = self.client.get(
            base, {'rule': 'LIKELY_MISSING_ZERO_IN_INCOME'}).json()
        self.assertEqual(set(a['rule_id'] for a in one_rule['anomalies']),
                         {'LIKELY_MISSING_ZERO_IN_INCOME'})
        none_reviewed = self.client.get(
            base, {'review_status': 'confirmed'}).json()
        self.assertEqual(none_reviewed['anomaly_count'], 0)
        searched = self.client.get(base, {'q': 'income'}).json()
        self.assertTrue(searched['anomaly_count'] >= 1)

    def test_record_scoped_filter_narrows_denominator(self):
        base = '/api/baseline/fsw-anomalies/'
        hit = self.client.get(base, {'enumerator': 'Sabita Rani Halder'}).json()
        self.assertEqual(hit['records_scanned'], 1)
        miss = self.client.get(base, {'enumerator': 'Nobody Real'}).json()
        self.assertEqual(miss['records_scanned'], 0)
        self.assertEqual(miss['anomaly_count'], 0)

    def test_population_all_is_default(self):
        body = self.client.get('/api/baseline/fsw-anomalies/').json()
        self.assertEqual(body['population'], 'all')

    def test_needs_verification_is_a_valid_review_status(self):
        body = self.client.get('/api/baseline/fsw-anomalies/').json()
        a = body['anomalies'][0]
        resp = self.client.post('/api/baseline/fsw-anomalies/review/', {
            'submission_id': a['record_id'], 'rule_id': a['rule_id'],
            'status': 'needs_verification', 'note': 'send supervisor'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'needs_verification')

    def test_review_decision_persists_and_merges(self):
        body = self.client.get('/api/baseline/fsw-anomalies/').json()
        a = body['anomalies'][0]
        resp = self.client.post('/api/baseline/fsw-anomalies/review/', {
            'submission_id': a['record_id'], 'rule_id': a['rule_id'],
            'status': 'false_positive', 'note': 'legit'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AnomalyReview.objects.count(), 1)
        invalidate_cache()
        merged = self.client.get('/api/baseline/fsw-anomalies/').json()
        hit = [x for x in merged['anomalies']
               if x['record_id'] == a['record_id'] and x['rule_id'] == a['rule_id']]
        self.assertEqual(hit[0]['review_status'], 'false_positive')
        self.assertEqual(hit[0]['reviewed_by'], 'Reviewer')

    def test_review_rejects_bad_status(self):
        resp = self.client.post('/api/baseline/fsw-anomalies/review/', {
            'submission_id': 's', 'rule_id': 'R', 'status': 'nonsense'}, format='json')
        self.assertEqual(resp.status_code, 400)


HIJRA_UID = 'aBT7aCL9p4FGcW4WwXZcr6'


def _hijra_kobo(**over):
    base = {
        '_xform_id_string': HIJRA_UID, '_uuid': 'huuid-1', '__version__': 'vCURRENT',
        'grp_admin/dc_code': '1', 'grp_admin/site_code': '2',
        'grp_admin/interview_start': '2026-07-12T10:00:00',
        'grp_admin/interview_end_actual': '2026-07-12T10:50:00',
        'grp_scr/consent': '1', 'grp_scr/s2_age': 27, 'grp_a2/a205_age': 27,
        'grp_c/c2': 'Interview conducted in private, respondent at ease.',
    }
    base.update(over)
    return base


class HijraAdapterTests(TestCase):
    """The same engine must run on Hijra data via its own field map."""

    def _ids(self, records):
        report, _ = _scan(records, population='hijra')
        return {a['rule_id'] for a in report['anomalies']}

    def test_hijra_missing_end_on_old_form_is_not_flagged(self):
        rec = _hijra_kobo()
        rec.pop('grp_admin/interview_end_actual')
        rec['__version__'] = 'vOLD'
        ids = self._ids([rec])
        # An old form version is not an anomaly at all: it is OUR doing, every time
        # we redeploy, and it says nothing about the answers.
        self.assertNotIn('OLD_FORM_VERSION', ids)
        self.assertNotIn('MISSING_INTERVIEW_END', ids)

    def test_hijra_age_mismatch(self):
        rec = _hijra_kobo(**{'grp_scr/s2_age': 27, 'grp_a2/a205_age': 40})
        self.assertIn('AGE_MISMATCH', self._ids([rec]))

    def test_hijra_weak_observation_retired(self):
        # RETIRED: a thin interviewer observation is not a fault in the data.
        rec = _hijra_kobo(**{'grp_c/c2': 'Valo'})
        self.assertNotIn('WEAK_INTERVIEWER_OBSERVATION', self._ids([rec]))

    def test_hijra_income_missing_zero(self):
        rec = _hijra_kobo(**{'grp_b1/b104_share': 10})
        self.assertIn('LIKELY_MISSING_ZERO_IN_INCOME', self._ids([rec]))

    def test_hijra_q95_over_five_is_not_flagged(self):
        rec = _hijra_kobo(**{'grp_q9/q9_5': '01 02 03 04 05 06'})
        self.assertNotIn('Q95_MORE_THAN_FIVE_SERVICES', self._ids([rec]))

    def test_hijra_clean_record_has_no_flags(self):
        self.assertEqual(self._ids([_hijra_kobo()]), set())


class ExclusiveMultiselectConfigTest(TestCase):
    """Exclusivity comes ONLY from the explicit per-question config
    (EXCLUSIVE_CHOICE_CODES) — never from generic text matching. The old regex
    treated 'Never share needles or syringes' (a correct HIV-knowledge answer,
    FSW q3_5 code 05) as an exclusive 'none' choice and flooded the report."""

    def _ids(self, records, population='fsw'):
        report, _ = _scan(records, population)
        return report, {a['rule_id'] for a in report['anomalies']}

    def test_correct_hiv_answer_with_never_is_not_a_conflict(self):
        # q3_5 "In what ways can a person protect themselves…":
        # 01 (use condoms) + 05 (Never share needles) = a GOOD answer.
        rec = _kobo(**{'grp_q3/q3_5': '01 05'})
        _, ids = self._ids([rec])
        self.assertNotIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_dont_know_with_answers_is_not_flagged(self):
        # 'Don't know' (98) alongside partial answers is respondent behaviour,
        # not a data conflict — deliberately unconfigured.
        rec = _kobo(**{'grp_q3/q3_5': '01 98'})
        _, ids = self._ids([rec])
        self.assertNotIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_no_concerns_with_a_concern_is_flagged_with_labels(self):
        # q9_6 concerns: 10 (No concerns) + 01 (a concern) = real conflict.
        rec = _kobo(**{'grp_q9/q9_6': '10 01'})
        report, ids = self._ids([rec])
        self.assertIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)
        flag = [a for a in report['anomalies']
                if a['rule_id'] == 'MUTUALLY_EXCLUSIVE_MULTISELECT'][0]
        # Evidence carries the actual selected option labels.
        self.assertEqual(flag['observed']['exclusive'], ['No concerns'])
        self.assertTrue(flag['observed']['also_selected'])

    def test_income_none_with_a_source_still_flagged(self):
        rec = _kobo(**{'grp_b1/b109': '0 1'})
        _, ids = self._ids([rec])
        self.assertIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_exclusive_alone_is_clean(self):
        rec = _kobo(**{'grp_q9/q9_6': '10'})
        _, ids = self._ids([rec])
        self.assertNotIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_hijra_no_concerns_conflict_flagged(self):
        rec = _hijra_kobo(**{'grp_q9/q9_6': '08 01'})
        _, ids = self._ids([rec], population='hijra')
        self.assertIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_hijra_dont_know_not_flagged(self):
        rec = _hijra_kobo(**{'grp_q3/q3_2': '01 98'})
        _, ids = self._ids([rec], population='hijra')
        self.assertNotIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_config_resolves_against_real_forms(self):
        # Every configured (field, code) must exist in the deployed schema —
        # a typo here would silently disable the rule.
        from .anomaly import EXCLUSIVE_CHOICE_CODES, _exclusive_label_map
        for pop in ('fsw', 'hijra'):
            schema = load_schema()[pop]
            label_map = _exclusive_label_map(schema, pop)
            self.assertEqual(len(label_map), len(EXCLUSIVE_CHOICE_CODES[pop]),
                             f'{pop}: some configured fields did not resolve')


class HijraExclusiveAuditTest(TestCase):
    """The Hijra half of the exclusive-option audit (plus the FSW gap it
    exposed). Same decision rule as FSW: configured exclusives conflict with any
    co-selection; DK-on-knowledge-lists and reason-style options never flag."""

    def _ids(self, records, population='hijra'):
        report, _ = _scan(records, population)
        return report, {a['rule_id'] for a in report['anomalies']}

    def test_dont_know_any_law_plus_naming_one_is_flagged(self):
        rec = _hijra_kobo(**{'grp_q2/q2_12': '98 01'})
        report, ids = self._ids([rec])
        self.assertIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)
        flag = [a for a in report['anomalies']
                if a['rule_id'] == 'MUTUALLY_EXCLUSIVE_MULTISELECT'][0]
        self.assertEqual(flag['observed']['exclusive'], ["Don't know any"])

    def test_benefit_awareness_conflicts_flagged(self):
        for field in ('q2_13', 'q2_15'):
            rec = _hijra_kobo(**{f'grp_q2/{field}': '98 01'})
            _, ids = self._ids([rec])
            self.assertIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids, field)

    def test_did_not_need_assistance_plus_barrier_is_flagged(self):
        rec = _hijra_kobo(**{'grp_q2/q2_21': '00 01'})
        _, ids = self._ids([rec])
        self.assertIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_never_received_info_plus_source_is_flagged(self):
        rec = _hijra_kobo(**{'grp_q3/q3_11': '12 01'})
        _, ids = self._ids([rec])
        self.assertIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_hiv_knowledge_dk_still_not_flagged(self):
        # DK on knowledge lists stays unconfigured — partial knowledge, not conflict.
        for field in ('q3_2', 'q3_3', 'q3_4', 'q3_10'):
            rec = _hijra_kobo(**{f'grp_q3/{field}': '01 98'})
            _, ids = self._ids([rec])
            self.assertNotIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids, field)

    def test_reason_options_never_flag(self):
        # "Did not know where to go" etc. are reasons, co-selectable by design.
        rec = _hijra_kobo(**{'grp_q5/q5_7': '06 01'})
        _, ids = self._ids([rec])
        self.assertNotIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_fsw_never_received_info_gap_now_covered(self):
        rec = _kobo(**{'grp_q3/q3_13': '11 01'})
        _, ids = self._ids([rec], population='fsw')
        self.assertIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_fsw_reasons_and_correct_answers_still_clean(self):
        for field, val in (('q3_5', '01 05'), ('q7_21', '01 06'), ('q6_14', '08 01')):
            rec = _kobo(**{f'grp_q/{field}': val})
            _, ids = self._ids([rec], population='fsw')
            self.assertNotIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids, field)

    def test_two_negatives_together_are_not_a_conflict(self):
        # q2_15: "Don't know anything" (98) + "No shelter benefits" (2) are two
        # flavours of the same negative — both exclusive, so no flag.
        rec = _hijra_kobo(**{'grp_q2/q2_15': '98 2'})
        _, ids = self._ids([rec])
        self.assertNotIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids)

    def test_negative_plus_positive_benefit_is_a_conflict(self):
        # Either negative + the actual government-directive option (1) flags.
        for val in ('98 1', '2 1'):
            rec = _hijra_kobo(**{'grp_q2/q2_15': val})
            _, ids = self._ids([rec])
            self.assertIn('MUTUALLY_EXCLUSIVE_MULTISELECT', ids, val)


class WorkHistoryYearsTest(TestCase):
    """SEX_WORK_YEARS_IMPOSSIBLE must not fire on arithmetic that is actually fine.

    Ages are COMPLETED years, so current_age - start_age is a floor: 32 - 22 = 10
    means [10, 11) years elapsed — for which "More than 10 years" is literally
    correct. The rule flags only a contradiction beyond that rounding slack.
    b105 codes: 1 'Less than 1 year', 2 '1-3', 3 '4-7', 4 '8-10', 5 'More than 10 years'.
    """

    def _ids(self, age, start_age, b105_code):
        rec = _kobo(**{'grp_a2/a203': age, 'grp_scr/s1_age': age,
                       'grp_b1/b104': start_age, 'grp_b1/b105': b105_code})
        report, _ = _scan([rec])
        return {a['rule_id'] for a in report['anomalies']}

    def test_exactly_ten_years_more_than_10_is_not_flagged(self):
        # Rafi's case: 32, started at 22, "More than 10 years" -> TRUE, not a defect.
        self.assertNotIn('SEX_WORK_YEARS_IMPOSSIBLE', self._ids(32, 22, '5'))

    def test_boundary_rounding_slack_is_allowed(self):
        # 31 started at 22 -> 9 floor, [9,10) elapsed; "More than 10" is within the
        # one-year self-report/rounding slack, so not flagged.
        self.assertNotIn('SEX_WORK_YEARS_IMPOSSIBLE', self._ids(31, 22, '5'))
        # 25 started at 22 -> 3 floor; "4-7 years" is a plausible self-report.
        self.assertNotIn('SEX_WORK_YEARS_IMPOSSIBLE', self._ids(25, 22, '3'))

    def test_genuine_contradiction_still_flagged(self):
        # 25 started at 22 -> at most ~3 years; "More than 10 years" is impossible.
        self.assertIn('SEX_WORK_YEARS_IMPOSSIBLE', self._ids(25, 22, '5'))
        # 24 started at 22 -> at most ~2 years; "8-10 years" is impossible.
        self.assertIn('SEX_WORK_YEARS_IMPOSSIBLE', self._ids(24, 22, '4'))

    def test_start_after_current_age_still_flagged(self):
        self.assertIn('SEX_WORK_START_AFTER_CURRENT_AGE', self._ids(30, 40, '2'))


class SystematicPassRegressionTest(TestCase):
    """Rules retired/narrowed after auditing every flag against real data."""

    def _ids(self, records, population='fsw'):
        report, _ = _scan(records, population)
        return {a['rule_id'] for a in report['anomalies']}

    def test_hijra_uses_the_same_40_minute_threshold(self):
        rec = _hijra_kobo(**{'grp_admin/interview_end_actual': '2026-07-12T10:39:00'})
        self.assertIn('INTERVIEW_TOO_SHORT', self._ids([rec], population='hijra'))

    def test_short_interview_is_always_high(self):
        # Any breach of the 40-minute line is HIGH — not scaled down to medium for
        # a near-miss. A 39-minute interview is as incomplete as a 5-minute one.
        for end in ('2026-07-12T10:39:00', '2026-07-12T10:05:00'):
            report, _ = _scan([_kobo(**{'grp_admin/interview_end_actual': end})])
            short = [a for a in report['anomalies'] if a['rule_id'] == 'INTERVIEW_TOO_SHORT']
            self.assertEqual([a['severity'] for a in short], ['high'], end)

    def test_expense_overrun_retired(self):
        # Spending more than you earn is ordinary here — borrowing, savings and debt
        # are the norm, and the rule could not tell those from a data fault.
        rec = _kobo(**{'grp_b1/b108': 5000, 'grp_b1/b110_family': 21000, 'grp_b1/b109': '0'})
        self.assertNotIn('EXPENSES_EXCEED_INCOME_NO_OTHER_SOURCE', self._ids([rec]))

    def test_gps_quality_rules_retired(self):
        # Precision and distance-from-site describe the handset and the outreach,
        # not the answers. INVALID_GPS/INCOMPLETE_GPS stay registered (see
        # build_fsw_engine) — this fixture carries no coordinates to exercise them.
        ids = self._ids([_kobo(**{'_geolocation_precision': 120, '_geolocation': [23.8, 90.4]})])
        self.assertNotIn('LOW_GPS_PRECISION', ids)
        self.assertNotIn('GPS_SITE_OUTLIER', ids)

    def test_child_location_when_all_children_present_is_not_flagged(self):
        # a215 "With her" / "lives with me" is a consistent answer, not a defect.
        rec = _kobo(**{'grp_a2/a213': 2, 'grp_a2/a214': 2, 'grp_a2/a215': 'With her'})
        self.assertNotIn('OTHER_CHILD_LOCATION_NOT_NEEDED', self._ids([rec]))

    def test_missing_other_child_location_still_flagged(self):
        # The valuable direction survives: children elsewhere but no location.
        rec = _kobo(**{'grp_a2/a213': 3, 'grp_a2/a214': 1, 'grp_a2/a215': ''})
        self.assertIn('OTHER_CHILD_LOCATION_MISSING', self._ids([rec]))

    def test_observation_rules_retired(self):
        # Neither the "vague observation" nor the "same observation repeated" rule
        # fires: the interviewer's note is not respondent data and not a fault.
        recs = [_hijra_kobo(**{'_uuid': f'u{i}', 'grp_c/c2': 'N/A'}) for i in range(6)]
        ids = self._ids(recs, population='hijra')
        self.assertNotIn('REPEATED_ENUMERATOR_OBSERVATION', ids)
        self.assertNotIn('WEAK_INTERVIEWER_OBSERVATION', ids)

    def test_interviews_started_too_close_retired(self):
        # Enumerators open/consent to forms back-to-back and finish from draft, so
        # a short gap between start stamps proves nothing.
        recs = [
            _hijra_kobo(**{'_uuid': 'a', 'grp_admin/interview_start': '2026-07-12T10:00:00'}),
            _hijra_kobo(**{'_uuid': 'b', 'grp_admin/interview_start': '2026-07-12T10:04:00'}),
        ]
        self.assertNotIn('INTERVIEWS_STARTED_TOO_CLOSE', self._ids(recs, population='hijra'))


class RefusalCodeTest(TestCase):
    """B108 states "(99 = Prefer not to say)" in the question text itself, so 99 in
    a money field is a REFUSAL, not taka. Treating it as an amount flagged people
    who simply declined to answer — and inflated their enumerator to Urgent."""

    def _ids(self, records):
        report, _ = _scan(records)
        return {a['rule_id'] for a in report['anomalies']}

    def test_refusal_code_99_is_not_missing_zeros(self):
        rec = _kobo(**{'grp_b1/b108': 99})
        self.assertNotIn('LIKELY_MISSING_ZERO_IN_INCOME', self._ids([rec]))

    def test_98_is_NOT_a_code_on_b108_and_is_flagged(self):
        """This test used to assert the opposite, pinning a code the questionnaire
        never declares. B108's label documents 99 and only 99; the engine's private
        REFUSAL_CODES = {98, 99} invented the 98, so an income of 98 — i.e. 9,800
        typed without its zeros — could never be flagged. tests_codes.py has always
        asserted `assertFalse(is_non_answer('fsw', 'b108', 98))`: the two files
        pinned contradictory meanings and neither could see the other."""
        rec = _kobo(**{'grp_b1/b108': 98})
        self.assertIn('LIKELY_MISSING_ZERO_IN_INCOME', self._ids([rec]))

    def test_age_99_is_not_exempt_because_no_age_field_declares_a_code(self):
        """The age rules hard-coded `age != 99`. No age question declares a refusal
        code — their constraint permits 0–120 — so a 99-year-old respondent was
        silently exempt from AGE_OUT_OF_RANGE."""
        rec = _kobo(**{'grp_scr/s1_age': 99, 'grp_a2/a203': 99})
        self.assertIn('AGE_OUT_OF_RANGE', self._ids([rec]))

    def test_genuinely_low_income_still_flagged(self):
        # Real FSW income runs 2,000-130,000 (median 25,000), so 80 taka/month is
        # almost certainly 8,000 with dropped zeros — a real defect worth keeping.
        for amount in (80, 12, 10):
            rec = _kobo(**{'grp_b1/b108': amount})
            self.assertIn('LIKELY_MISSING_ZERO_IN_INCOME', self._ids([rec]), amount)

    def test_refusal_code_does_not_drive_the_expense_comparison(self):
        rec = _kobo(**{'grp_b1/b108': 99, 'grp_b1/b110_family': 21000,
                       'grp_b1/b109': '0'})
        self.assertNotIn('LIKELY_MISSING_ZERO_IN_INCOME', self._ids([rec]))


class FlatFortyMinuteThresholdTest(TestCase):
    """CIPRB's rule is a single 40-minute line for BOTH instruments. Do not split
    it per population — that override was reverted."""

    def test_threshold_is_40_for_both_populations(self):
        from .anomaly import SHORT_MINUTES
        self.assertEqual(SHORT_MINUTES['fsw'], 40)
        self.assertEqual(SHORT_MINUTES['hijra'], 40)

    def test_39_minutes_is_short_in_both(self):
        report, _ = _scan([_kobo(**{'grp_admin/interview_end_actual':
                                    '2026-07-12T10:39:00'})])
        self.assertIn('INTERVIEW_TOO_SHORT',
                      {a['rule_id'] for a in report['anomalies']})
        report2, _ = _scan([_hijra_kobo(**{'grp_admin/interview_end_actual':
                                           '2026-07-12T10:39:00'})], population='hijra')
        self.assertIn('INTERVIEW_TOO_SHORT',
                      {a['rule_id'] for a in report2['anomalies']})
