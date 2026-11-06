"""
Tests for the fistula app — refactored to match the current
FistulaCampaign aggregate model.

The previous test file targeted a now-removed FistulaCase model (with
encrypted patient PII, per-case status workflow, and an overdue follow-up
flow). Migration 0002_fistulacampaign_delete_fistulacase_and_more
replaced that with a campaign-session aggregate model — no PII at the
row level, no per-case workflow, just one record per outreach/screening
session with aggregated reach + referral + surgery counts.

The encryption helpers (fistula/encryption.py) are still in the codebase
for re-use by other modules; tests in EncryptionTest stay.
"""
import datetime

from cryptography.fernet import Fernet
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from submissions.models import FormType, KoboSubmission, SubmissionStatus

from .encryption import decrypt, encrypt
from .models import FistulaCampaign

TEST_KEY = Fernet.generate_key().decode()
BASE_URL = '/api/fistula/cases/'


def make_user(email, org, role):
    return User.objects.create_user(
        email=email, password='pass', full_name='Test',
        organisation=org, role=role,
    )


def _rows(resp):
    """Return list of rows whether the response is paginated or a plain list."""
    data = resp.data
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


def make_submission(partner='PHD', kobo_id='k001'):
    # PENDING so the post_save signal does not auto-create the
    # FistulaCampaign; the manager-method test exercises the
    # creation path directly.
    return KoboSubmission.objects.create(
        kobo_id=kobo_id,
        form_type=FormType.FISTULA,
        partner=partner,
        worker_name='Rina',
        district='Dhaka',
        region='Dhaka',
        submitted_at=timezone.now(),
        raw_data={
            'district': 'Dhaka',
            'upazila': 'Dhanmondi',
            'women_screened': '40',
            'confirmed_fistula_cases': '3',
            'cases_referred': '2',
        },
        status=SubmissionStatus.PENDING,
    )


def make_campaign(partner='PHD', district='Dhaka', campaign_date=None,
                  women_screened=0, confirmed=0, referred=0):
    if campaign_date is None:
        campaign_date = datetime.date.today()
    return FistulaCampaign.objects.create(
        partner=partner,
        district=district,
        region='Dhaka',
        campaign_date=campaign_date,
        women_screened=women_screened,
        confirmed_fistula_cases=confirmed,
        cases_referred=referred,
    )


# ─── Encryption helpers ──────────────────────────────────────────────────────

@override_settings(FERNET_KEY=TEST_KEY)
class EncryptionTest(TestCase):

    def test_encrypt_decrypt_round_trip(self):
        ciphertext = encrypt('Fatema Begum')
        self.assertNotEqual(ciphertext, 'Fatema Begum')
        self.assertEqual(decrypt(ciphertext), 'Fatema Begum')

    def test_empty_string_returns_empty(self):
        self.assertEqual(encrypt(''), '')
        self.assertEqual(decrypt(''), '')

    def test_different_ciphertexts_for_same_plaintext(self):
        # Fernet uses random IV so each encryption produces unique ciphertext
        c1 = encrypt('test')
        c2 = encrypt('test')
        self.assertNotEqual(c1, c2)
        self.assertEqual(decrypt(c1), 'test')
        self.assertEqual(decrypt(c2), 'test')

    def test_invalid_ciphertext_returns_empty(self):
        self.assertEqual(decrypt('not-valid-ciphertext'), '')


# ─── FistulaCampaign model ───────────────────────────────────────────────────

class FistulaCampaignModelTest(TestCase):

    def test_case_hash_auto_generated(self):
        camp = make_campaign()
        self.assertTrue(camp.case_hash.startswith('FST-PHD-'))

    def test_bandhu_hash_prefix(self):
        camp = make_campaign(partner='Bandhu')
        self.assertIn('BON', camp.case_hash)

    def test_str_contains_case_hash(self):
        camp = make_campaign()
        self.assertIn('FST-', str(camp))


# ─── get_or_create_from_submission ───────────────────────────────────────────

class FromSubmissionTest(TestCase):

    def test_creates_campaign_from_submission(self):
        sub = make_submission()
        camp, created = FistulaCampaign.objects.get_or_create_from_submission(sub)
        self.assertTrue(created)
        self.assertEqual(camp.partner, 'PHD')
        self.assertEqual(camp.district, 'Dhaka')
        self.assertEqual(camp.women_screened, 40)
        self.assertEqual(camp.confirmed_fistula_cases, 3)
        self.assertEqual(camp.cases_referred, 2)

    def test_idempotent_get_or_create(self):
        sub = make_submission(kobo_id='k002')
        _, c1 = FistulaCampaign.objects.get_or_create_from_submission(sub)
        _, c2 = FistulaCampaign.objects.get_or_create_from_submission(sub)
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(FistulaCampaign.objects.count(), 1)

    def test_missing_aggregate_fields_default_to_zero(self):
        sub = make_submission(kobo_id='k003')
        sub.raw_data = {}
        sub.save()
        camp, _ = FistulaCampaign.objects.get_or_create_from_submission(sub)
        self.assertEqual(camp.women_screened, 0)
        self.assertEqual(camp.confirmed_fistula_cases, 0)


# ─── API — list, org isolation, write methods blocked ────────────────────────

class FistulaCampaignAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)
        self.bandhu = make_user('bm@bandhu.org', Organisation.BANDHU, Role.MANAGER)

    def test_unauthenticated_returns_403(self):
        resp = self.client.get(BASE_URL)
        self.assertEqual(resp.status_code, 403)

    def test_phd_manager_sees_only_phd_campaigns(self):
        make_campaign(partner='PHD')
        make_campaign(partner='Bandhu')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(BASE_URL)
        self.assertEqual(resp.status_code, 200)
        rows = _rows(resp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['partner'], 'PHD')

    def test_bandhu_cannot_see_phd_campaigns(self):
        make_campaign(partner='PHD')
        self.client.force_authenticate(user=self.bandhu)
        resp = self.client.get(BASE_URL)
        self.assertEqual(len(_rows(resp)), 0)

    def test_post_not_allowed(self):
        # Viewset is read-only — http_method_names = ['get', 'head', 'options']
        self.client.force_authenticate(user=self.phd)
        resp = self.client.post(BASE_URL, {}, format='json')
        self.assertEqual(resp.status_code, 405)

    def test_delete_not_allowed(self):
        camp = make_campaign(partner='PHD')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.delete(f'{BASE_URL}{camp.id}/')
        self.assertEqual(resp.status_code, 405)


# ─── Stats endpoint ──────────────────────────────────────────────────────────

class StatsEndpointTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)

    def test_stats_keys_present(self):
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}stats/')
        self.assertEqual(resp.status_code, 200)
        for key in (
            'total_sessions',
            'this_month_sessions',
            'this_month_women_screened',
            'this_month_confirmed_cases',
            'this_month_cases_referred',
            'this_month_surgery_completed',
        ):
            self.assertIn(key, resp.data)

    def test_stats_aggregates_this_month(self):
        today = datetime.date.today()
        make_campaign(partner='PHD', campaign_date=today,
                      women_screened=50, confirmed=4, referred=2)
        make_campaign(partner='PHD', campaign_date=today,
                      women_screened=30, confirmed=2, referred=1)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}stats/')
        self.assertEqual(resp.data['total_sessions'], 2)
        self.assertEqual(resp.data['this_month_sessions'], 2)
        self.assertEqual(resp.data['this_month_women_screened'], 80)
        self.assertEqual(resp.data['this_month_confirmed_cases'], 6)
        self.assertEqual(resp.data['this_month_cases_referred'], 3)

    def test_stats_org_isolated(self):
        make_campaign(partner='Bandhu')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}stats/')
        self.assertEqual(resp.data['total_sessions'], 0)


# ─── Daily CHW campaign webhook handler ──────────────────────────────────────

def _daily_campaign_payload(kobo_id='daily-1'):
    """A ciprb_fistula_campaign_v1 (daily CHW activity) submission payload."""
    return {
        '_id': kobo_id,
        '_xform_id_string': 'ciprb_fistula_campaign_v1',
        '_submitted_by': 'chw_rina',
        'organisation': 'CIPRB',
        'collection_date': '2026-07-01',
        'union': 'abc',
        'upazila': 'Dhanmondi',
        'district': 'dhaka',
        'staff_hi_ahi': '2', 'staff_ha': '3', 'staff_chcp': '1',
        'staff_fwv': '1', 'staff_fpi': '0', 'staff_fwa': '4', 'staff_chw': '6',
        'focal_community': '5', 'focal_epi': '2', 'focal_fwc': '1', 'focal_cc': '3',
        'households_visited': '120',
        'population_covered': '540',
        'suspected_patients': '7',
        'diagnosed_patients': '3',
        'referral': '2',
        'surgeries': '1',
        'rehabilitation': '4',
        'enumerator_name': 'Rina Akter',
        'enumerator_mobile': '01710000000',
    }


class CIPRBFistulaDailyCampaignWebhookTest(TestCase):

    def test_creates_pending_campaign_with_correct_mappings(self):
        from fistula.webhook_handlers import handle_ciprb_fistula_campaign
        resp = handle_ciprb_fistula_campaign(
            _daily_campaign_payload(), lat=23.75, lng=90.38)
        self.assertEqual(resp.status_code, 201)

        self.assertEqual(FistulaCampaign.objects.count(), 1)
        camp = FistulaCampaign.objects.get()
        # Partner / org / approval
        self.assertEqual(camp.partner, 'CIPRB')
        self.assertEqual(camp.organisation, 'CIPRB')
        self.assertEqual(camp.approval_status, 'PENDING')
        # CIP prefix on the auto case_hash (the save() prefix fix)
        self.assertTrue(camp.case_hash.startswith('FST-CIP-'), camp.case_hash)
        # Reach
        self.assertEqual(camp.households_visited, 120)
        self.assertEqual(camp.population_covered, 540)
        # Staff / focal head-counts
        self.assertEqual(camp.staff_chw, 6)
        self.assertEqual(camp.focal_community, 5)
        # Outcome mappings (form field → model field)
        self.assertEqual(camp.suspected_fistula_cases, 7)      # suspected_patients
        self.assertEqual(camp.confirmed_fistula_cases, 3)      # diagnosed_patients
        self.assertEqual(camp.cases_referred, 2)               # referral
        self.assertEqual(camp.cases_surgery_completed, 1)      # surgeries
        self.assertEqual(camp.cases_social_reintegration, 4)   # rehabilitation
        # Provenance
        self.assertEqual(camp.kobo_submission_id, 'daily-1')
        self.assertEqual(camp.submitted_by_kobo_user, 'chw_rina')
        self.assertEqual(camp.enumerator_name, 'Rina Akter')
        self.assertEqual(str(camp.campaign_date), '2026-07-01')

    def test_idempotent_on_kobo_id(self):
        from fistula.webhook_handlers import handle_ciprb_fistula_campaign
        payload = _daily_campaign_payload(kobo_id='dup-9')
        r1 = handle_ciprb_fistula_campaign(payload, lat=None, lng=None)
        r2 = handle_ciprb_fistula_campaign(payload, lat=None, lng=None)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 200)   # deduped
        self.assertEqual(FistulaCampaign.objects.count(), 1)


@override_settings(FISTULA_CAMPAIGN_ARCHIVE=False)  # archive overlay tested separately
class CampaignVsCaseRegistryTest(TestCase):
    """The 'Fistula Campaign' panel must report the CAMPAIGN FORM, never the
    case registry wearing a campaign label (CIPRB meeting, 3 Aug 2026: the two
    panels showed the same eight numbers and 57 carried two denominators)."""

    def setUp(self):
        from .models import CIPRBFistulaCase
        self.client = APIClient()
        self.user = make_user('ciprb@x.org', Organisation.CIPRB, Role.ORG_LEAD)
        self.client.force_authenticate(user=self.user)
        # Case registry: 3 cases across 3 districts / 3 upazilas.
        for i, d in enumerate(['Dhaka', 'Rangpur', 'Bhola']):
            CIPRBFistulaCase.objects.create(
                case_serial='C%d' % i, district=d, upazila='U%d' % i,
                current_stage='diagnosed', approval_status='APPROVED')
        # Campaign form: 2 activity days, ONE district, with real reach.
        for i in range(2):
            FistulaCampaign.objects.create(
                district='Kurigram', upazila='Nageshwari',
                campaign_date=datetime.date(2026, 7, 1 + i),
                households_visited=100 + i, population_covered=500 + i,
                suspected_fistula_cases=2, approval_status='APPROVED',
                latitude=25.8 + i / 100, longitude=89.6)

    def _agg(self):
        r = self.client.get('/api/fistula/aggregates/')
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_campaign_block_reports_the_campaign_form_not_the_registry(self):
        camp = self._agg()['campaign']
        self.assertEqual(camp['reports'], 2)
        self.assertEqual(camp['districts'], 1)      # NOT the registry's 3
        self.assertEqual(camp['upazilas'], 1)
        self.assertEqual(camp['households'], 201)
        self.assertEqual(camp['population'], 1001)
        self.assertEqual(camp['suspected'], 4)

    def test_case_coverage_stays_separate_from_campaign_coverage(self):
        agg = self._agg()
        self.assertEqual(agg['campaign_reach']['districts'], 3)
        self.assertEqual(agg['campaign']['districts'], 1)

    def test_dots_are_grouped_per_upazila_not_per_row(self):
        rows = self._agg()['campaign']['by_upazila']
        self.assertEqual(len(rows), 1)          # 2 reports, ONE upazila
        self.assertEqual(rows[0]['district'], 'Kurigram')
        self.assertEqual(rows[0]['upazila'], 'Nageshwari')
        self.assertEqual(rows[0]['reports'], 2)
        self.assertEqual(rows[0]['households'], 201)
        self.assertIn('key', rows[0])

    def test_rows_without_gps_are_skipped_but_still_counted(self):
        FistulaCampaign.objects.create(
            district='Kurigram', upazila='Nageshwari',
            campaign_date=datetime.date(2026, 7, 9),
            households_visited=50, approval_status='APPROVED')
        camp = self._agg()['campaign']
        self.assertEqual(camp['reports'], 3)          # counted
        self.assertEqual(camp['households'], 251)
        # placement is by upazila, so a GPS-less row still gets a dot
        row = camp['by_upazila'][0]
        self.assertEqual(row['reports'], 3)
        self.assertEqual(row['gps_rows'], 2)          # only 2 carried GPS

    def test_pending_campaign_rows_are_excluded(self):
        FistulaCampaign.objects.create(
            district='Kurigram', upazila='Nageshwari',
            campaign_date=datetime.date(2026, 7, 10),
            households_visited=9999, approval_status='PENDING',
            latitude=25.9, longitude=89.7)
        camp = self._agg()['campaign']
        self.assertEqual(camp['reports'], 2)
        self.assertEqual(camp['households'], 201)


@override_settings(FISTULA_CAMPAIGN_ARCHIVE=False)  # archive overlay tested separately
class UpazilaNameFoldingTest(TestCase):
    """Field staff spell one upazila several ways in a single week. The map and
    the table must show ONE row per real upazila (Rafi, 3 Aug 2026)."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(
            user=make_user('fold@x.org', Organisation.CIPRB, Role.ORG_LEAD))

    def _add(self, district, upazila, households):
        FistulaCampaign.objects.create(
            district=district, upazila=upazila,
            campaign_date=datetime.date(2026, 7, 1),
            households_visited=households, approval_status='APPROVED')

    def _rows(self):
        r = self.client.get('/api/fistula/aggregates/')
        self.assertEqual(r.status_code, 200)
        return r.json()['campaign']['by_upazila']

    def test_latin_spelling_variants_merge(self):
        self._add('Gaibandha', 'Sadullahpur', 10)
        self._add('Gaibandha', 'Sadullahpur', 4)
        self._add('Gaibandha', 'Sadullapur', 5)
        self._add('gaibandha', 'sadullahpur ', 1)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['reports'], 4)
        self.assertEqual(rows[0]['households'], 20)
        # the majority spelling is displayed, variants stay visible
        self.assertEqual(rows[0]['upazila'], 'Sadullahpur')
        self.assertEqual(rows[0]['spellings'],
                         ['Sadullahpur', 'Sadullapur', 'sadullahpur'])

    def test_bengali_and_latin_merge(self):
        self._add('Khagrachari', 'Ramgarh', 7)
        self._add('খাগড়াছড়ি',
                  'রামগড়', 3)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['households'], 10)

    def test_different_upazilas_stay_apart(self):
        self._add('Gaibandha', 'Saghatta', 4)
        self._add('Gaibandha', 'Sadullapur', 4)
        self.assertEqual(len(self._rows()), 2)

    def test_same_upazila_name_in_two_districts_stays_apart(self):
        self._add('Khagrachari', 'Ramgarh', 4)
        self._add('Sirajganj', 'Ramgarh', 4)
        self.assertEqual(len(self._rows()), 2)


@override_settings(FISTULA_CAMPAIGN_ARCHIVE=True)
class CampaignArchiveOverlayTest(TestCase):
    """Q1/Q2 paper archive (RCH request, 17 Aug 2026): archive rows appear in
    by_upazila tagged source='archive', win over live rows for the same
    upazila, and the campaign totals include them."""
    def setUp(self):
        from accounts.models import User
        from rest_framework.test import APIClient
        self.user = User.objects.create_user(
            email='dev2@x.org', password='Str0ng-Passw0rd-2026', full_name='Dev',
            organisation='CIPRB', role='developer')
        self.c = APIClient(); self.c.force_authenticate(self.user)

    def test_archive_rows_present_and_win(self):
        from fistula.models import FistulaCampaign
        FistulaCampaign.objects.create(
            district='Kurigram', upazila='Chilmari',
            campaign_date=datetime.date(2026, 5, 10),
            households_visited=99999, population_covered=1,
            approval_status='APPROVED')
        r = self.c.get('/api/fistula/aggregates/')
        camp = r.json()['campaign']
        rows = {x['upazila'].lower(): x for x in camp['by_upazila']}
        chil = rows['chilmari']
        self.assertEqual(chil['source'], 'archive')
        self.assertEqual(chil['population'], 57380)   # archive wins over live 1
        self.assertIn('Q2', chil['quarters'])
        self.assertEqual(rows['panchari']['population'], 31025)  # Q1-only upazila
        self.assertEqual(camp['population'],
                         sum(x['population'] or 0 for x in camp['by_upazila']))
        self.assertEqual(len(camp['archive_rows']), 24)


class CampaignDistrictFunnelTest(TestCase):
    """The per-district campaign funnel beside the map (RCH, 2 Sep 2026).

    The campaign form records only `suspected`, so the other four stages come
    from the case registry scoped to the districts the campaign worked in. The
    two must stay distinguishable: a CHW day-count is not a registered patient,
    and folding one into the other is the 3 Aug 2026 complaint all over again.
    """

    def setUp(self):
        from .models import CIPRBFistulaCase
        self.client = APIClient()
        self.user = make_user('rch@x.org', Organisation.CIPRB, Role.ORG_LEAD)
        self.client.force_authenticate(user=self.user)

        # Kurigram is a campaign district. One case at each of three stages.
        for i, stage in enumerate(['suspected', 'referred', 'rehabilitated']):
            CIPRBFistulaCase.objects.create(
                case_serial='K%d' % i, district='Kurigram', upazila='Nageshwari',
                current_stage=stage, approval_status='APPROVED')
        # Dhaka is NOT a campaign district. It must not appear at all.
        CIPRBFistulaCase.objects.create(
            case_serial='D1', district='Dhaka', upazila='Savar',
            current_stage='repaired', approval_status='APPROVED')

        FistulaCampaign.objects.create(
            district='Kurigram', upazila='Nageshwari',
            campaign_date=datetime.date(2026, 7, 1),
            households_visited=100, population_covered=500,
            suspected_fistula_cases=9, approval_status='APPROVED',
            latitude=25.8, longitude=89.6)

    def _camp(self):
        r = self.client.get('/api/fistula/aggregates/')
        self.assertEqual(r.status_code, 200)
        return r.json()['campaign']

    def test_only_campaign_districts_appear(self):
        # The Q1/Q2 paper archive is merged into by_upazila unconditionally,
        # so its eight districts are campaign districts too and belong here.
        # What must NOT appear is a district with cases but no campaign.
        names = [r['district'] for r in self._camp()['by_district']]
        self.assertIn('Kurigram', names)
        self.assertNotIn('Dhaka', names)

    def _row(self, name='Kurigram'):
        for r in self._camp()['by_district']:
            if r['district'] == name:
                return r
        self.fail('%s missing from by_district' % name)

    def test_stages_are_cumulative_and_never_invert(self):
        row = self._row()
        # 3 cases at suspected / referred / rehabilitated. A case at a later
        # stage has passed every earlier one.
        self.assertEqual(row['suspected'], 3)
        self.assertEqual(row['diagnosed'], 2)
        self.assertEqual(row['referred'], 2)
        self.assertEqual(row['repaired'], 1)
        self.assertEqual(row['rehabilitated'], 1)
        order = ['suspected', 'diagnosed', 'referred', 'repaired', 'rehabilitated']
        for a, b in zip(order, order[1:]):
            self.assertGreaterEqual(row[a], row[b])

    def test_chw_tally_is_carried_separately_not_folded_in(self):
        row = self._row()
        # 9 from the live activity day, plus whatever the Q1/Q2 paper archive
        # holds for Kurigram. Either way it is a CHW field tally.
        self.assertGreaterEqual(row['chw_suspected'], 9)
        # And it must NOT have become the funnel's first stage: that stays the
        # registered-case count, which is 3.
        self.assertEqual(row['suspected'], 3)
        self.assertNotEqual(row['chw_suspected'], row['suspected'])

    def test_national_funnel_is_the_sum_of_the_districts(self):
        camp = self._camp()
        rows = camp['by_district']
        for stage in ('suspected', 'diagnosed', 'referred', 'repaired',
                      'rehabilitated'):
            self.assertEqual(camp['funnel'][stage],
                             sum(r[stage] for r in rows))
        self.assertEqual(camp['funnel']['chw_suspected'],
                         sum(r['chw_suspected'] for r in rows))
        # Kurigram also carries a Q1 archive row, so the CHW tally is the
        # live 9 plus the archive's own. The point is that it is summed from
        # the same rows the panel draws, not that it equals any one figure.

    def test_a_district_the_campaign_missed_is_excluded_from_the_funnel(self):
        camp = self._camp()
        # Dhaka has a repaired case but no campaign activity, so it must not
        # inflate the campaign's repaired count.
        self.assertEqual(camp['funnel']['repaired'], 1)
        self.assertNotIn('Dhaka', [r['district'] for r in camp['by_district']])


class FistulaTreatmentCostTest(TestCase):
    """Treatment cost entries (Question Bank rows 96-102).

    The rules locked down here all come from Dr Tanjina Pervin (RCH CIPRB,
    9 September 2026): cost attaches from referral onward, a woman can be
    operated twice and each operation carries its own cost, and the project
    bears the whole cost so the figures exist to be compared against the
    BDT 10,000-12,000 per patient allocation.
    """

    def setUp(self):
        from fistula.ciprb_models import CIPRBFistulaCase
        self.case = CIPRBFistulaCase.objects.create(
            patient_code='1-0001', organisation='CIPRB', district='Sunamganj',
            name='Test Woman', approval_status='APPROVED',
            current_stage=CIPRBFistulaCase.STAGE_REPAIRED)

    def _post(self, **over):
        from programs.ciprb_handlers import handle_ciprb_fistula
        payload = {
            'stage': 'cost',
            'patient_code_final': '1-0001',
            'cost_point': 'repaired',
            'episode_final': '1',
            'cost_date': '2026-09-01',
            'medical_cost': '3000',
            'investigation_cost': '1500',
            'ot_cost': '5000',
            'travel_cost': '800',
            'food_cost': '700',
            'other_cost': '0',
            'cost_remarks': 'first repair',
            '_id': 'cost-1',
        }
        payload.update(over)
        return handle_ciprb_fistula(payload, lat=None, lng=None)

    def test_a_cost_entry_is_recorded_and_totalled(self):
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        self.assertEqual(self._post().status_code, 200)
        row = CIPRBFistulaCaseCost.objects.get()
        self.assertEqual(row.case, self.case)
        self.assertEqual(row.total, 11000)
        self.assertEqual(row.remarks, 'first repair')

    def test_recording_cost_does_not_move_the_clinical_stage(self):
        """Money is not a step in the pathway. If a cost entry advanced
        current_stage the woman would leave the pipeline counts entirely."""
        from fistula.ciprb_models import CIPRBFistulaCase
        self._post()
        self.case.refresh_from_db()
        self.assertEqual(self.case.current_stage,
                         CIPRBFistulaCase.STAGE_REPAIRED)

    def test_a_second_operation_is_a_second_row_not_an_overwrite(self):
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        self._post()
        self._post(episode_final='2', ot_cost='6000', medical_cost='2000',
                   investigation_cost='', travel_cost='', food_cost='',
                   other_cost='', _id='cost-2')
        self.assertEqual(CIPRBFistulaCaseCost.objects.count(), 2)
        totals = sorted(r.total for r in CIPRBFistulaCaseCost.objects.all())
        self.assertEqual(totals, [8000, 11000])

    def test_resending_the_same_episode_corrects_it_not_duplicates_it(self):
        """A webhook redelivery, or a worker fixing a typo, must not double the
        programme's reported spend."""
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        self._post()
        self._post(ot_cost='5500')
        self.assertEqual(CIPRBFistulaCaseCost.objects.count(), 1)
        self.assertEqual(CIPRBFistulaCaseCost.objects.get().total, 11500)

    def test_a_referral_cost_needs_no_operation(self):
        """A woman referred and travelled but never operated (a comorbidity
        ruled out theatre) still cost the project money."""
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        r = self._post(cost_point='referred', episode_final='', ot_cost='',
                       medical_cost='', investigation_cost='1200',
                       travel_cost='900', food_cost='300', other_cost='',
                       _id='cost-ref')
        self.assertEqual(r.status_code, 200)
        row = CIPRBFistulaCaseCost.objects.get(cost_point='referred')
        self.assertEqual(row.episode_no, 1)
        self.assertEqual(row.total, 2400)
        self.assertIsNone(row.ot_cost)

    def test_a_second_referral_is_its_own_row(self):
        """A woman referred twice travels twice. Collapsing both onto one row
        would let the second entry's travel cost replace the first."""
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        base = dict(cost_point='referred', ot_cost='', medical_cost='',
                    investigation_cost='', food_cost='', other_cost='')
        self._post(episode_final='1', travel_cost='900', _id='ref-1', **base)
        self._post(episode_final='2', travel_cost='650', _id='ref-2', **base)
        rows = CIPRBFistulaCaseCost.objects.filter(cost_point='referred')
        self.assertEqual(rows.count(), 2)
        self.assertEqual(sum(r.total for r in rows), 1550)

    def test_blank_is_not_recorded_and_zero_is_a_real_figure(self):
        """Collapsing the two would fill the data with meaningless zeroes and
        make 'we do not know' indistinguishable from 'it was free'."""
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        self._post(food_cost='', other_cost='0')
        row = CIPRBFistulaCaseCost.objects.get()
        self.assertIsNone(row.food_cost)
        self.assertEqual(row.other_cost, 0)

    def test_the_amount_released_is_recorded_beside_what_was_spent(self):
        """CIPRB does not pay the facility. A District Coordinator releases the
        money to the woman and she settles the bill, so what was released and
        what was spent are two figures and the gap must stay visible."""
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        self._post(amount_disbursed='12000', disbursed_by='DC Sunamganj')
        row = CIPRBFistulaCaseCost.objects.get()
        self.assertEqual(row.amount_disbursed, 12000)
        self.assertEqual(row.disbursed_by, 'DC Sunamganj')
        self.assertEqual(row.total, 11000)
        self.assertEqual(row.balance, 1000)

    def test_balance_is_none_when_nothing_was_recorded_as_released(self):
        """0 minus the spend would read as an overspend that never happened."""
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        self._post()
        self.assertIsNone(CIPRBFistulaCaseCost.objects.get().balance)

    def test_spending_beyond_what_was_released_shows_as_a_negative_balance(self):
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        self._post(amount_disbursed='9000')
        self.assertEqual(CIPRBFistulaCaseCost.objects.get().balance, -2000)

    def test_cost_for_an_unregistered_patient_is_rejected(self):
        """A stub would park money against a woman who was never registered
        and inflate the programme total."""
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        r = self._post(patient_code_final='9-9999')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(CIPRBFistulaCaseCost.objects.count(), 0)

    def test_an_unknown_cost_point_is_rejected(self):
        self.assertEqual(self._post(cost_point='rehabilitated').status_code, 400)


class FistulaCostAggregateTest(TestCase):
    """The cost block on /api/fistula/aggregates/."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from fistula.ciprb_models import (CIPRBFistulaCase,
                                          CIPRBFistulaCaseCost)
        self.user = get_user_model().objects.create_user(
            email='cost@test.local', password='x', role='SUPER_ADMIN')
        # Three women: 8,000 (under budget), 11,000 (within), 20,000 (over).
        for i, amounts in enumerate([(8000,), (11000,), (14000, 6000)], start=1):
            case = CIPRBFistulaCase.objects.create(
                patient_code='1-000%d' % i, organisation='CIPRB',
                district='Sunamganj', name='W%d' % i,
                approval_status='APPROVED', current_stage='repaired')
            for ep, amt in enumerate(amounts, start=1):
                CIPRBFistulaCaseCost.objects.create(
                    case=case, cost_point='repaired', episode_no=ep,
                    ot_cost=amt)

    def _get(self):
        from rest_framework.test import APIClient
        c = APIClient()
        c.force_authenticate(self.user)
        return c.get('/api/fistula/aggregates/').data['cost']

    def test_totals_and_averages(self):
        d = self._get()
        self.assertEqual(d['total_bdt'], 39000)
        self.assertEqual(d['patients_costed'], 3)
        self.assertEqual(d['avg_per_patient'], 13000)
        # Four operations across three women, so the per-operation average is
        # NOT the per-patient average. Reporting one as the other would
        # understate what a repair costs.
        self.assertEqual(d['operations_costed'], 4)
        self.assertEqual(d['avg_per_operation'], 9750)

    def test_the_budget_comparison_is_the_point_of_the_panel(self):
        d = self._get()
        self.assertEqual(d['budget_low'], 10000)
        self.assertEqual(d['budget_high'], 12000)
        self.assertEqual(d['vs_budget'], {'under': 1, 'within': 1, 'over': 1})

    def test_released_against_spent_reconciles(self):
        """The figure CIPRB's ledger has to match. Only episodes with a
        disbursement recorded are counted, so an unrecorded release is never
        read as a zero release."""
        from fistula.ciprb_models import CIPRBFistulaCaseCost
        rows = list(CIPRBFistulaCaseCost.objects.order_by('case__patient_code',
                                                          'episode_no'))
        # Release 10,000 against the 8,000 episode and 5,000 against the 6,000
        # one. The remaining two episodes carry no release at all.
        rows[0].amount_disbursed = 10000
        rows[0].save()
        rows[3].amount_disbursed = 5000
        rows[3].save()
        d = self._get()
        self.assertEqual(d['episodes_with_disbursement'], 2)
        self.assertEqual(d['total_disbursed'], 15000)
        self.assertEqual(d['spent_where_disbursed'], 14000)
        self.assertEqual(d['balance'], 1000)
        self.assertEqual(d['vs_disbursed'],
                         {'matched': 0, 'underspent': 1, 'overspent': 1})

    def test_no_disbursement_recorded_is_not_a_zero_disbursement(self):
        d = self._get()
        self.assertEqual(d['episodes_with_disbursement'], 0)
        self.assertEqual(d['total_disbursed'], 0)
        self.assertEqual(d['balance'], 0)

    def test_the_basis_line_does_not_call_this_out_of_pocket(self):
        """CIPRB pays the full cost, so out-of-pocket expenditure is zero by
        definition. The wording must not invite that mislabel in a report."""
        self.assertNotIn('out-of-pocket expenditure', self._get()['basis'])
