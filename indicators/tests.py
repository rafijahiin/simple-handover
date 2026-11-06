"""
Tests for the restructured IndicatorTarget API + Target Config permissions.

The 43-row seed (PHD 22 + Bandhu 18 + CIPRB 3) is loaded by the indicators
migrations; these tests rely on it. PHD uses the SL1–SL16 SIDA codes; the legacy
PHD scheme (1.1 / 3.1a–d / 1.7 / the "OVERALL — Brothels covered" row) was
retired in the PHD rebuild.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from indicators.models import IndicatorTarget

TARGETS_URL = '/api/indicators/targets/'


def _user(email, org, role):
    return User.objects.create_user(
        email=email, password='x', full_name='T',
        organisation=org, role=role,
    )


class SeedShapeTest(TestCase):
    """The migration-loaded fixture should produce 43 rows with the
    correct partner split and the correct null-target counts."""

    def test_total_rows(self):
        self.assertEqual(IndicatorTarget.objects.count(), 43)

    def test_partner_counts(self):
        self.assertEqual(IndicatorTarget.objects.filter(partner__code='PHD').count(), 22)
        self.assertEqual(IndicatorTarget.objects.filter(partner__code='Bandhu').count(), 18)
        self.assertEqual(IndicatorTarget.objects.filter(partner__code='CIPRB').count(), 3)

    def test_phd_uses_sl_codes(self):
        # The PHD rebuild replaced the legacy scheme with SL1–SL16. There is no
        # 'OVERALL' / '1.1' / '3.1a' row any more.
        codes = set(
            IndicatorTarget.objects
            .filter(partner__code='PHD')
            .values_list('activity_code', flat=True)
        )
        self.assertTrue(all(c.startswith('SL') for c in codes), msg=codes)
        self.assertNotIn('OVERALL', codes)

    def test_bandhu_no_objective_3(self):
        objs = set(
            IndicatorTarget.objects
            .filter(partner__code='Bandhu')
            .values_list('objective_number', flat=True)
        )
        self.assertEqual(objs, {1, 2, 4})

    def test_ciprb_targets_all_null(self):
        rows = IndicatorTarget.objects.filter(partner__code='CIPRB')
        self.assertEqual(rows.count(), 3)
        self.assertEqual(rows.filter(target_value__isnull=True).count(), 3)


class IndicatorTargetReadTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.sup = _user('s@unfpa', Organisation.UNFPA, Role.SUPERVISOR)
        self.phd_lead = _user('lead@phd', Organisation.PHD, Role.ORG_LEAD)
        self.bandhu_mgr = _user('mgr@bandhu', Organisation.BANDHU, Role.MANAGER)

    def _rows(self, r):
        if isinstance(r.data, dict) and 'results' in r.data:
            return r.data['results']
        return r.data

    def test_supervisor_sees_all_43(self):
        self.client.force_authenticate(user=self.sup)
        r = self.client.get(TARGETS_URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self._rows(r)), 43)

    def test_ciprb_org_lead_reads_all_partners(self):
        # ORG_LEAD cross-org read is now bound to CIPRB (the monitoring org),
        # mirroring can_access_mpdsr/fistula. A CIPRB lead still reads all 44.
        ciprb_lead = _user('lead@ciprb', Organisation.CIPRB, Role.ORG_LEAD)
        self.client.force_authenticate(user=ciprb_lead)
        r = self.client.get(TARGETS_URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self._rows(r)), 43)

    def test_non_ciprb_org_lead_sees_only_own_partner(self):
        # A PHD/Bandhu org lead is org-bound (can_read_other_orgs=False) — no
        # cross-partner read. This is the security fix being asserted.
        self.client.force_authenticate(user=self.phd_lead)
        r = self.client.get(TARGETS_URL)
        self.assertEqual(r.status_code, 200)
        codes = {row['partner_code'] for row in self._rows(r)}
        self.assertEqual(codes, {'PHD'})

    def test_manager_only_sees_own_partner(self):
        self.client.force_authenticate(user=self.bandhu_mgr)
        r = self.client.get(TARGETS_URL)
        self.assertEqual(r.status_code, 200)
        codes = {row['partner_code'] for row in self._rows(r)}
        self.assertEqual(codes, {'Bandhu'})


class IndicatorTargetWritePermissionTest(TestCase):
    """CanConfigureTargets — UNFPA Supervisor + Developer only (Animesh's
    2026-06-01 directive). Org leads and managers are blocked from editing
    targets, even for their own partner; reads stay broad."""

    def setUp(self):
        self.client = APIClient()
        self.sup = _user('s@unfpa', Organisation.UNFPA, Role.SUPERVISOR)
        self.ciprb_lead = _user('lead@ciprb', Organisation.CIPRB, Role.ORG_LEAD)
        self.phd_lead = _user('lead@phd', Organisation.PHD, Role.ORG_LEAD)
        self.bandhu_mgr = _user('mgr@bandhu', Organisation.BANDHU, Role.MANAGER)

        self.phd_row   = IndicatorTarget.objects.filter(partner__code='PHD').first()
        self.ciprb_row = IndicatorTarget.objects.filter(partner__code='CIPRB').first()

    def _patch(self, row_id, target_value):
        return self.client.patch(
            f'{TARGETS_URL}{row_id}/',
            {'target_value': target_value},
            format='json',
        )

    def test_supervisor_can_edit_any_partner(self):
        self.client.force_authenticate(user=self.sup)
        r = self._patch(self.phd_row.id, 9999)
        self.assertEqual(r.status_code, 200)
        self.phd_row.refresh_from_db()
        self.assertEqual(self.phd_row.target_value, Decimal('9999.00'))
        self.assertEqual(self.phd_row.updated_by, self.sup)

    def test_ciprb_lead_cannot_edit_ciprb_target(self):
        # Org leads (incl. the CIPRB monitoring lead) may READ all targets but
        # NOT edit them — only UNFPA Supervisor + Developer set targets.
        self.client.force_authenticate(user=self.ciprb_lead)
        r = self._patch(self.ciprb_row.id, 25)
        self.assertEqual(r.status_code, 403)

    def test_phd_lead_cannot_edit_ciprb_target(self):
        self.client.force_authenticate(user=self.phd_lead)
        r = self._patch(self.ciprb_row.id, 25)
        self.assertEqual(r.status_code, 403)

    def test_manager_cannot_edit_target(self):
        self.client.force_authenticate(user=self.bandhu_mgr)
        row = IndicatorTarget.objects.filter(partner__code='Bandhu').first()
        r = self._patch(row.id, 100)
        self.assertEqual(r.status_code, 403)


# ─── Step 3: service-layer compute wiring ────────────────────────────────────

from datetime import date

from indicators import bandhu, phd
from indicators.service import (
    get_partner_indicator_progress,
    get_indicator_progress,
)

P_START = date(2026, 5, 21)
P_END   = date(2026, 11, 20)


class ActivityRegistryShapeTest(TestCase):
    """Both partner registries must cover every fixture row that has a
    'real' (i.e. not deliberately unlinked) module, and no others."""

    def test_phd_all_codes_wired(self):
        """After the IECMaterial compute landed (Commit 2 model + migration
        0006 wiring), every PHD fixture code has a compute function.
        Replaces the old test that asserted 3.1a-d were unlinked."""
        codes_in_fixture = set(
            IndicatorTarget.objects
            .filter(partner__code='PHD', is_active=True)
            .values_list('activity_code', flat=True)
        )
        unlinked = codes_in_fixture - set(phd.ACTIVITY_REGISTRY)
        self.assertEqual(unlinked, set())

    def test_bandhu_all_codes_wired(self):
        """After DAY_OBSERVANCE (Commit 1) + IECMaterial (Commit 2) +
        migration 0006, every Bandhu fixture code resolves to a compute
        function. 2.6 (day observance) and 4.3 (e-billboards) used to
        be unlinked; both are now live."""
        codes_in_fixture = set(
            IndicatorTarget.objects
            .filter(partner__code='Bandhu', is_active=True)
            .values_list('activity_code', flat=True)
        )
        unlinked = codes_in_fixture - set(bandhu.ACTIVITY_REGISTRY)
        self.assertEqual(unlinked, set())


class PartnerProgressShapeTest(TestCase):
    """get_partner_indicator_progress emits the Step 3 dict shape with
    achievement=0 / percentage rules / unlinked flag."""

    def test_phd_returns_22_rows(self):
        rows = get_partner_indicator_progress('PHD', P_START, P_END)
        self.assertEqual(len(rows), 22)

    def test_bandhu_returns_18_rows(self):
        rows = get_partner_indicator_progress('Bandhu', P_START, P_END)
        self.assertEqual(len(rows), 18)

    def test_ciprb_returns_3_rows_all_linked(self):
        # Migration 0007 + indicators.ciprb wired all 3 CIPRB rows
        # (F.C, F.Camp, B) to fistula and baseline backings.
        rows = get_partner_indicator_progress('CIPRB', P_START, P_END)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(not r['unlinked'] for r in rows))

    def test_every_row_has_step3_keys(self):
        rows = get_partner_indicator_progress('PHD', P_START, P_END)
        required = {
            'activity_code', 'objective_number', 'activity_label',
            'indicator_label', 'target_value', 'unit',
            'achievement', 'percentage', 'unlinked',
        }
        for r in rows:
            self.assertTrue(required.issubset(r.keys()), msg=f'row={r}')

    def test_achievement_is_zero_not_none_with_no_records(self):
        # No fixtures, no Kobo submissions → every linked row should
        # return achievement=0 (never None).
        for org in ('PHD', 'Bandhu'):
            for r in get_partner_indicator_progress(org, P_START, P_END):
                self.assertIsNotNone(r['achievement'], msg=f'{org}/{r["activity_code"]}')
                self.assertEqual(r['achievement'], 0)

    def test_percentage_null_when_target_null(self):
        # CIPRB rows all have target_value=None → percentage must be None.
        for r in get_partner_indicator_progress('CIPRB', P_START, P_END):
            self.assertIsNone(r['target_value'])
            self.assertIsNone(r['percentage'])

    def test_percentage_zero_when_target_positive_and_achievement_zero(self):
        # PHD rows have positive targets and achievement=0 (no records);
        # percentage must be 0.0, not None.
        rows = [
            r for r in get_partner_indicator_progress('PHD', P_START, P_END)
            if r['target_value'] is not None and not r['unlinked']
        ]
        self.assertTrue(rows, 'expected at least one linked PHD row with a target')
        for r in rows:
            self.assertEqual(
                r['percentage'], 0.0,
                msg=f"{r['activity_code']} achievement={r['achievement']} target={r['target_value']}",
            )

    def test_iec_rows_now_linked_and_returning_zero(self):
        # PHD's IEC display indicators (SL15a message boards / SL15b signboards /
        # SL15c billboards) are wired to the IECMaterial compute functions; with
        # no IECMaterial rows in the test DB they return achievement=0,
        # unlinked=False.
        rows = {r['activity_code']: r for r in get_partner_indicator_progress('PHD', P_START, P_END)}
        for code in ('SL15a', 'SL15b', 'SL15c'):
            self.assertIn(code, rows)
            self.assertFalse(rows[code]['unlinked'])
            self.assertEqual(rows[code]['achievement'], 0)

    def test_ciprb_rows_now_linked_and_returning_zero(self):
        # CIPRB compute functions (indicators.ciprb) wire all 3 rows.
        # With no FistulaCornerCase / FistulaCampaignVisit / BaselineSurvey
        # in the test DB they correctly return achievement=0 and
        # unlinked=False (linked, just no data yet).
        rows = {r['activity_code']: r for r in get_partner_indicator_progress('CIPRB', P_START, P_END)}
        for code in ('F.C', 'F.Camp', 'B'):
            self.assertIn(code, rows)
            self.assertFalse(rows[code]['unlinked'])
            self.assertEqual(rows[code]['achievement'], 0)

    def test_bandhu_objective_order_skips_3(self):
        rows = get_partner_indicator_progress('Bandhu', P_START, P_END)
        objs = [r['objective_number'] for r in rows]
        # Must be sorted and contain 1, 2, 4 — never 3.
        self.assertEqual(sorted(set(objs)), [1, 2, 4])
        self.assertEqual(objs, sorted(objs))


class SingleIndicatorProgressTest(TestCase):
    """get_indicator_progress returns the same row shape for a single
    (partner, code) pair, and degrades gracefully on unknown codes."""

    def test_known_code_returns_row(self):
        r = get_indicator_progress('PHD', 'SL1', P_START, P_END)
        self.assertEqual(r['activity_code'], 'SL1')
        self.assertEqual(r['achievement'], 0)
        self.assertFalse(r['unlinked'])

    def test_ciprb_fistula_corner_now_linked(self):
        # F.C wired to FistulaCornerCase by migration 0007. No fixture
        # rows in test DB so achievement is 0, but the row is linked.
        r = get_indicator_progress('CIPRB', 'F.C', P_START, P_END)
        self.assertFalse(r['unlinked'])
        self.assertEqual(r['achievement'], 0)

    def test_unknown_code_does_not_crash(self):
        r = get_indicator_progress('PHD', 'BOGUS', P_START, P_END)
        self.assertEqual(r['achievement'], 0)
        self.assertTrue(r['unlinked'])
        self.assertIsNone(r['target_value'])


class ProgressEndpointTest(TestCase):
    """The /api/indicators/progress/ endpoint surfaces the Step 3 shape
    through the IndicatorProgressSerializer."""

    def setUp(self):
        self.client = APIClient()
        self.sup = _user('s@unfpa', Organisation.UNFPA, Role.SUPERVISOR)
        self.client.force_authenticate(user=self.sup)

    def test_progress_endpoint_returns_step3_shape(self):
        r = self.client.get(
            '/api/indicators/progress/?org=PHD'
            '&period_start=2026-05-21&period_end=2026-11-20'
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 22)
        first = r.data[0]
        for key in ('activity_code', 'objective_number', 'achievement',
                    'percentage', 'unlinked', 'target_value'):
            self.assertIn(key, first)

    def test_all_orgs_endpoint_includes_ciprb(self):
        r = self.client.get(
            '/api/indicators/progress/'
            '?period_start=2026-05-21&period_end=2026-11-20'
        )
        self.assertEqual(r.status_code, 200)
        # Supervisor with no ?org param ⇒ all three partners merged.
        orgs = {row['organisation'] for row in r.data}
        self.assertEqual(orgs, {'CIPRB', 'Bandhu', 'PHD'})
        self.assertEqual(len(r.data), 43)


# ─── KoboFormMapping wiring (migration 0006) ─────────────────────────────────

class KoboFormMappingWiringTest(TestCase):
    """Verifies migration 0006 seeded the form catalogue and wired the
    IndicatorTarget.source_form FK for every activity that has a Kobo form
    backing it. Reference-table-driven indicators correctly stay NULL."""

    def test_form_mappings_seeded(self):
        from indicators.models import KoboFormMapping
        # The form catalogue started at 21 (0006 programs forms + IEC, 0007
        # fistula + baseline) and grew to 37 as later migrations registered the
        # CIPRB MPDSR/fistula forms (0015), the consolidated PHD service log
        # (0016) and the baseline key-population forms (0017).
        self.assertEqual(KoboFormMapping.objects.count(), 37)
        slugs = set(KoboFormMapping.objects.values_list('form_slug', flat=True))
        self.assertIn('spondon_clinic_visit_v1', slugs)
        self.assertIn('spondon_iec_material_v1', slugs)
        self.assertIn('spondon_fistula_corner_v1', slugs)
        self.assertIn('spondon_fistula_campaign_v1', slugs)

    def test_partner_exclusive_forms_have_partner_fk(self):
        from indicators.models import KoboFormMapping
        self.assertEqual(
            KoboFormMapping.objects.get(form_slug='spondon_hygiene_kit_v1').partner.code,
            'Bandhu',
        )
        self.assertEqual(
            KoboFormMapping.objects.get(form_slug='spondon_autoclave_log_v1').partner.code,
            'PHD',
        )
        self.assertEqual(
            KoboFormMapping.objects.get(form_slug='spondon_antenatal_card_v1').partner.code,
            'PHD',
        )

    def test_cross_partner_forms_have_null_partner(self):
        from indicators.models import KoboFormMapping
        self.assertIsNone(
            KoboFormMapping.objects.get(form_slug='spondon_clinic_visit_v1').partner,
        )
        self.assertIsNone(
            KoboFormMapping.objects.get(form_slug='spondon_coord_meeting_v1').partner,
        )

    def test_phd_indicators_source_form_wired(self):
        # PHD's SL codes are all fed by the single consolidated service log,
        # except SL8 (functional centres) which is reference-table driven.
        for code in ('SL1', 'SL15a', 'SL16'):
            row = IndicatorTarget.objects.get(partner__code='PHD', activity_code=code)
            self.assertEqual(row.source_form.form_slug, 'phd_service_log_v1',
                             msg=f'PHD/{code} source_form')

    def test_bandhu_indicators_have_null_source_form(self):
        # Bandhu indicators each aggregate several forms (clinic, outreach,
        # training, IEC…), so none is wired to a single source_form — all NULL.
        rows = IndicatorTarget.objects.filter(partner__code='Bandhu')
        self.assertEqual(rows.count(), 18)
        self.assertEqual(rows.filter(source_form__isnull=True).count(), 18)

    def test_reference_table_indicators_remain_null(self):
        # ServiceCenter-driven / aggregate rows must not be wired to a Kobo form.
        for partner, code in [
            ('PHD',    'SL8'),       # functional brothel centres (ServiceCenter)
            ('Bandhu', '1.6'),       # Dhaka KP clinic (ServiceCenter)
            ('Bandhu', '1.8'),       # DICs (ServiceCenter)
        ]:
            row = IndicatorTarget.objects.get(partner__code=partner, activity_code=code)
            self.assertIsNone(row.source_form,
                              msg=f'{partner}/{code} should have source_form=NULL')

    def test_ciprb_indicators_wired_to_fistula_and_baseline(self):
        # Migration 0007 wired all 3 CIPRB rows after the Fistula register
        # photo + Sunamganj campaign xlsx confirmed the schema.
        expected = {
            'F.C':    'spondon_fistula_corner_v1',
            'F.Camp': 'spondon_fistula_campaign_v1',
            'B':      'spondon_baseline_v1',
        }
        for code, slug in expected.items():
            row = IndicatorTarget.objects.get(partner__code='CIPRB', activity_code=code)
            self.assertIsNotNone(row.source_form, msg=f'CIPRB/{code} should be wired')
            self.assertEqual(row.source_form.form_slug, slug,
                             msg=f'CIPRB/{code} wrong source_form')


# ─── New compute functions (Commit 2 IEC + day-observance) ───────────────────

class NewComputeFunctionsTest(TestCase):
    """The IEC + day-observance compute functions (Bandhu 2.6 day observance,
    Bandhu 4.2 displays, PHD SL15a message boards) exercised with minimal
    fixtures: assert non-crash + correct count from the IECMaterial and
    CoordMeeting (DAY_OBSERVANCE) backings."""

    def setUp(self):
        from programs.models import ServiceCenter
        self.phd_center = ServiceCenter.objects.create(
            organisation='PHD', name='C-IECTEST', code='IECTEST-1',
            center_type=ServiceCenter.BROTHEL, district='Dhaka',
        )

    def test_bnd_1_1_counts_mother_list_not_service_forms(self):
        """KP reached (1.1) is the Mother List registry, not F-05/F-06 services.
        Registered (approved, named) Bandhu clients count; stubs and service
        ClinicVisits do not."""
        from programs.models import ServiceCenter, Client, ClinicVisit
        from indicators.bandhu import compute_I_BND_1_1
        from datetime import date
        centre = ServiceCenter.objects.create(
            organisation='Bandhu', name='C-ML', code='ML-1',
            center_type=ServiceCenter.DIC, district='Dhaka')
        # Two real Mother List registrations (auto-approved, named).
        c1 = Client.objects.create(organisation='Bandhu', center=centre,
                                   client_id='ML-01', name='Asha',
                                   approval_status=Client.APPROVED)
        Client.objects.create(organisation='Bandhu', center=centre,
                              client_id='ML-02', name='Rani',
                              approval_status=Client.APPROVED)
        # A stub (service log cited an unregistered id) — must NOT count.
        Client.objects.create(organisation='Bandhu', center=centre,
                              client_id='ML-STUB', name='Unknown',
                              approval_status=Client.APPROVED)
        # A service record — must NOT drive KP-reached any more.
        ClinicVisit.objects.create(organisation='Bandhu', center=centre,
                                   client=c1, visit_date=date(2026, 6, 2),
                                   hiv_screening_done=True,
                                   approval_status=ClinicVisit.APPROVED)
        n = compute_I_BND_1_1('Bandhu', date(2026, 5, 21), date(2026, 11, 20))
        self.assertEqual(n, 2)   # the two named registrations only

    def test_phd_sl1r_counts_registry_not_screening(self):
        """PHD 'FSWs reached' headline (SL1R) = the Mother List registry
        (distinct approved, non-stub PHD clients), measured like Bandhu 1.1 —
        NOT the SL1 screening-service count. SL1 stays the narrower indicator."""
        from programs.models import ServiceCenter, Client, ClinicVisit
        from indicators.phd import compute_SL1R, compute_SL1
        from datetime import date
        centre = ServiceCenter.objects.create(
            organisation='PHD', name='C-REG', code='REG-1',
            center_type=ServiceCenter.BROTHEL, district='Rajbari')
        # Three registered FSWs (approved, named) — the registry.
        reg = [Client.objects.create(organisation='PHD', center=centre,
                                     client_id='1-000%d' % i, name='F%d' % i,
                                     approval_status=Client.APPROVED)
               for i in range(3)]
        # A stub (service log cited an unregistered id) — must NOT count.
        Client.objects.create(organisation='PHD', center=centre,
                              client_id='1-STUB', name='Unknown',
                              approval_status=Client.APPROVED)
        # A pending registration — must NOT count.
        Client.objects.create(organisation='PHD', center=centre,
                              client_id='1-PEND', name='Pending',
                              approval_status=Client.PENDING)
        # Only ONE of the three has actually received a screening service.
        ClinicVisit.objects.create(organisation='PHD', center=centre,
                                   client=reg[0], visit_date=date(2026, 6, 2),
                                   hiv_screening_done=True,
                                   approval_status=ClinicVisit.APPROVED)
        P = (date(2026, 5, 21), date(2026, 11, 20))
        self.assertEqual(compute_SL1R('PHD', *P), 3)   # registry = 3 named approved
        self.assertEqual(compute_SL1('PHD', *P), 1)    # screening service = 1

    def test_phd_registry_kpi_shape(self):
        """The headline KPI row is SL1R, carries the 3,500 target, and is linked
        (so the card renders a real percentage, not a 'module pending' tag)."""
        from indicators.service import get_phd_registry_kpi
        from datetime import date
        row = get_phd_registry_kpi(date(2026, 5, 21), date(2026, 11, 20),
                                   date(2026, 11, 2))
        self.assertEqual(row['activity_code'], 'SL1R')
        self.assertEqual(row['target_value'], 3500.0)
        self.assertFalse(row['unlinked'])
        self.assertIsNone(row['month_target'])

    def test_phd_sl2_counts_gbv_referral_not_screening(self):
        """SL2 = GBV survivors referred (referral_gbv), NOT the routine GBV
        screening tick that PHD records on nearly every visit."""
        from programs.models import ServiceCenter, Client, ClinicVisit
        from indicators.phd import compute_SL2
        from datetime import date
        centre = ServiceCenter.objects.create(
            organisation='PHD', name='C-GBV', code='GBV-1',
            center_type=ServiceCenter.BROTHEL, district='Khulna')
        c1 = Client.objects.create(organisation='PHD', center=centre,
                                   client_id='2-0001', name='A',
                                   approval_status=Client.APPROVED)
        c2 = Client.objects.create(organisation='PHD', center=centre,
                                   client_id='2-0002', name='B',
                                   approval_status=Client.APPROVED)
        # Both screened; only c2 was actually referred for GBV.
        ClinicVisit.objects.create(organisation='PHD', center=centre, client=c1,
                                   visit_date=date(2026, 6, 2),
                                   gbv_screening_done=True, referral_gbv=False,
                                   approval_status=ClinicVisit.APPROVED)
        ClinicVisit.objects.create(organisation='PHD', center=centre, client=c2,
                                   visit_date=date(2026, 6, 3),
                                   gbv_screening_done=True, referral_gbv=True,
                                   approval_status=ClinicVisit.APPROVED)
        self.assertEqual(
            compute_SL2('PHD', date(2026, 5, 21), date(2026, 11, 20)), 1)

    def test_phd_sl3_sums_counselling_report_mh_not_screening(self):
        """SL3 = MH counselling delivered (PHDCounsellingReport.mh_count summed),
        NOT the routine mh_screening tick on ClinicVisit; pending reports excluded."""
        from programs.models import (ServiceCenter, Client, ClinicVisit,
                                      PHDCounsellingReport)
        from indicators.phd import compute_SL3
        from datetime import date
        centre = ServiceCenter.objects.create(
            organisation='PHD', name='C-MH', code='MH-1',
            center_type=ServiceCenter.BROTHEL, district='Tangail')
        c1 = Client.objects.create(organisation='PHD', center=centre,
                                   client_id='3-0001', name='A',
                                   approval_status=Client.APPROVED)
        # A screened clinic visit must NOT count toward SL3 any more.
        ClinicVisit.objects.create(organisation='PHD', center=centre, client=c1,
                                   visit_date=date(2026, 6, 2),
                                   mh_screening_done=True,
                                   approval_status=ClinicVisit.APPROVED)
        # Two approved monthly counselling reports with MH counselling counts.
        PHDCounsellingReport.objects.create(
            organisation='PHD', center=centre, report_date=date(2026, 6, 30),
            mh_count=4, approval_status=PHDCounsellingReport.APPROVED)
        PHDCounsellingReport.objects.create(
            organisation='PHD', center=centre, report_date=date(2026, 7, 31),
            mh_count=3, approval_status=PHDCounsellingReport.APPROVED)
        # A pending report must NOT count.
        PHDCounsellingReport.objects.create(
            organisation='PHD', center=centre, report_date=date(2026, 8, 31),
            mh_count=99, approval_status=PHDCounsellingReport.PENDING)
        self.assertEqual(
            compute_SL3('PHD', date(2026, 5, 21), date(2026, 11, 20)), 7)

    def test_phd_sl9_counts_camp_training_events(self):
        """PHD mobile health camps are stored as TrainingEvent(event_type='camp')
        by the Service Log event handler, so SL9 counts those. An ordinary
        training event is not a camp; a pending camp does not count."""
        from programs.models import TrainingEvent
        from indicators.phd import compute_SL9
        from datetime import date
        TrainingEvent.objects.create(
            organisation='PHD', event_date=date(2026, 6, 10),
            event_type='camp', total_participants=0,
            approval_status=TrainingEvent.APPROVED)
        TrainingEvent.objects.create(
            organisation='PHD', event_date=date(2026, 7, 10),
            event_type='camp', total_participants=0,
            approval_status=TrainingEvent.APPROVED)
        # Pending camp excluded.
        TrainingEvent.objects.create(
            organisation='PHD', event_date=date(2026, 8, 10),
            event_type='camp', total_participants=0,
            approval_status=TrainingEvent.PENDING)
        # A real training is not a camp.
        TrainingEvent.objects.create(
            organisation='PHD', event_date=date(2026, 6, 15),
            event_type='training', total_participants=5,
            approval_status=TrainingEvent.APPROVED)
        self.assertEqual(
            compute_SL9('PHD', date(2026, 5, 21), date(2026, 11, 20)), 2)

    def test_phd_sl14_counts_coord_meeting_training_events(self):
        """PHD coordination meetings are stored as
        TrainingEvent(event_type='coord_meeting') by the Service Log event
        handler, so SL14 counts those, not ordinary trainings."""
        from programs.models import TrainingEvent
        from indicators.phd import compute_SL14
        from datetime import date
        TrainingEvent.objects.create(
            organisation='PHD', event_date=date(2026, 6, 5),
            event_type='coord_meeting', total_participants=0,
            approval_status=TrainingEvent.APPROVED)
        # Pending meeting excluded.
        TrainingEvent.objects.create(
            organisation='PHD', event_date=date(2026, 7, 5),
            event_type='coord_meeting', total_participants=0,
            approval_status=TrainingEvent.PENDING)
        TrainingEvent.objects.create(
            organisation='PHD', event_date=date(2026, 6, 20),
            event_type='training', total_participants=3,
            approval_status=TrainingEvent.APPROVED)
        self.assertEqual(
            compute_SL14('PHD', date(2026, 5, 21), date(2026, 11, 20)), 1)

    def test_phd_sl5_maps_free_text_commodity_names(self):
        """SL5c/SL5d must match the real free-text item names (HBsAg / HCV),
        not the literal strings 'hepatitis b' / 'hepatitis c' which never appear.
        Penicillin injections are syphilis treatment and must NOT count as a
        syphilis test kit (SL5b). Pending rows excluded."""
        from programs.models import ServiceCenter, StockEntry
        from indicators.phd import (compute_SL5a, compute_SL5b, compute_SL5c,
                                     compute_SL5d, compute_SL5e)
        from datetime import date
        centre = ServiceCenter.objects.create(
            organisation='PHD', name='C-Stock', code='STK-1',
            center_type=ServiceCenter.BROTHEL, district='Tangail')

        def stock(name, issued, status=StockEntry.APPROVED, month=date(2026, 6, 1)):
            StockEntry.objects.create(
                organisation='PHD', center=centre, reporting_month=month,
                item_name=name, quantity_issued=issued, approval_status=status)

        # Hep B — all three are the HBsAg surface-antigen test under different names.
        stock('HBsAg kits', 50)
        stock('HbsAG', 9, month=date(2026, 7, 1))
        stock('Hepatitis B kits', 1, month=date(2026, 8, 1))   # also hep B
        # Hep C — HCV antibody test, varied spelling.
        stock('HCV kits', 40)
        stock('Hepatitis C', 2, month=date(2026, 7, 1))        # also hep C
        # Syphilis test kit — counts; penicillin treatment — must NOT.
        stock('Syphilis kits', 30)
        stock('Inj. Benjapen-12Lac', 100)                      # treatment, excluded
        # Condoms and HIV.
        stock('Condom ( Free)', 500)
        stock('Determine HIV1/2', 70)
        # A pending HBsAg row must be excluded.
        stock('HBsAg kits', 999, status=StockEntry.PENDING, month=date(2026, 9, 1))

        P = (date(2026, 5, 21), date(2026, 11, 20))
        self.assertEqual(compute_SL5c('PHD', *P), 60)   # 50 + 9 + 1, pending excluded
        self.assertEqual(compute_SL5d('PHD', *P), 42)   # 40 + 2
        self.assertEqual(compute_SL5b('PHD', *P), 30)   # syphilis kit only, NOT penicillin
        self.assertEqual(compute_SL5a('PHD', *P), 500)
        self.assertEqual(compute_SL5e('PHD', *P), 70)

    def test_phd_sl6_counts_positive_cases_referred_for_treatment(self):
        """SL6 = HIV-positive (HTC) OR STI-diagnosed (clinic) FSWs who were
        referred for treatment (a clinic STI/HIV referral flag or a Referral
        register row). A positive with no referral, and a referral with no
        positive, both do not count."""
        from programs.models import (ServiceCenter, Client, ClinicVisit,
                                      HIVSTITestResult, Referral)
        from indicators.phd import compute_SL6
        from datetime import date
        centre = ServiceCenter.objects.create(
            organisation='PHD', name='C-SL6', code='SL6-1',
            center_type=ServiceCenter.BROTHEL, district='Tangail')

        def mk_client(cid):
            return Client.objects.create(
                organisation='PHD', center=centre, client_id=cid, name=cid,
                approval_status=Client.APPROVED)

        P = (date(2026, 5, 21), date(2026, 11, 20))

        # A: HIV positive + clinic STI/HIV treatment referral -> counts.
        a = mk_client('6-A')
        HIVSTITestResult.objects.create(
            organisation='PHD', center=centre, client=a,
            testing_date=date(2026, 6, 1), hiv_result='positive',
            approval_status=HIVSTITestResult.APPROVED)
        ClinicVisit.objects.create(
            organisation='PHD', center=centre, client=a,
            visit_date=date(2026, 6, 2), referral_sti_kp=True,
            approval_status=ClinicVisit.APPROVED)

        # B: STI diagnosed in clinic + a Referral-register row -> counts.
        b = mk_client('6-B')
        ClinicVisit.objects.create(
            organisation='PHD', center=centre, client=b,
            visit_date=date(2026, 6, 3), diag_ss=True,
            approval_status=ClinicVisit.APPROVED)
        Referral.objects.create(
            organisation='PHD', center=centre, client=b,
            referral_date=date(2026, 6, 4), referral_type=Referral.OTHER,
            approval_status=Referral.APPROVED)

        # C: HIV positive but NO referral -> excluded.
        c = mk_client('6-C')
        HIVSTITestResult.objects.create(
            organisation='PHD', center=centre, client=c,
            testing_date=date(2026, 6, 5), hiv_result='positive',
            approval_status=HIVSTITestResult.APPROVED)

        # D: referred but NOT positive -> excluded.
        d = mk_client('6-D')
        ClinicVisit.objects.create(
            organisation='PHD', center=centre, client=d,
            visit_date=date(2026, 6, 6), referral_sti_kp=True,
            approval_status=ClinicVisit.APPROVED)

        self.assertEqual(compute_SL6('PHD', *P), 2)

    def test_phd_sl15a_counts_message_boards(self):
        from programs.models import IECMaterial
        from partners.models import Partner
        from indicators.phd import compute_SL15a
        from datetime import date
        partner = Partner.objects.get(code='PHD')
        IECMaterial.objects.create(
            partner=partner, center=self.phd_center, organisation='PHD',
            material_type=IECMaterial.MESSAGE_BOARD,
            quantity=10, date_distributed=date(2026, 6, 1),
            approval_status=IECMaterial.APPROVED,
        )
        IECMaterial.objects.create(
            partner=partner, center=self.phd_center, organisation='PHD',
            material_type=IECMaterial.POSTER,   # different type — excluded
            quantity=99, date_distributed=date(2026, 6, 1),
            approval_status=IECMaterial.APPROVED,
        )
        result = compute_SL15a('PHD', date(2026, 5, 21), date(2026, 11, 20))
        self.assertEqual(result, 10)  # sum of MESSAGE_BOARD quantity

    def test_bandhu_2_6_counts_day_observance(self):
        from programs.models import CoordMeeting
        from indicators.bandhu import compute_I_BND_2_6
        from datetime import date
        CoordMeeting.objects.create(
            organisation='Bandhu',
            meeting_date=date(2026, 6, 1),
            meeting_type=CoordMeeting.DAY_OBSERVANCE,
            meeting_notes='dummy.pdf',  # blank=False on the field
            approval_status=CoordMeeting.APPROVED,
        )
        CoordMeeting.objects.create(
            organisation='Bandhu',
            meeting_date=date(2026, 6, 2),
            meeting_type=CoordMeeting.GOB,  # different type
            meeting_notes='dummy.pdf',
            approval_status=CoordMeeting.APPROVED,
        )
        result = compute_I_BND_2_6('Bandhu', date(2026, 5, 21), date(2026, 11, 20))
        self.assertEqual(result, 1)

    def test_bandhu_4_2_counts_displays(self):
        # Bandhu 4.2 "public messaging displays" sums BILLBOARD + DIGITAL
        # IEC-material quantity (printed + e-billboards); other types excluded.
        from programs.models import IECMaterial
        from partners.models import Partner
        from indicators.bandhu import compute_I_BND_4_2
        from datetime import date
        partner = Partner.objects.get(code='Bandhu')
        IECMaterial.objects.create(
            partner=partner, organisation='Bandhu',
            material_type=IECMaterial.DIGITAL,
            quantity=1, date_distributed=date(2026, 6, 1),
            approval_status=IECMaterial.APPROVED,
        )
        IECMaterial.objects.create(
            partner=partner, organisation='Bandhu',
            material_type=IECMaterial.BILLBOARD,
            quantity=1, date_distributed=date(2026, 7, 1),
            approval_status=IECMaterial.APPROVED,
        )
        IECMaterial.objects.create(
            partner=partner, organisation='Bandhu',
            material_type=IECMaterial.POSTER,   # excluded type
            quantity=99, date_distributed=date(2026, 7, 1),
            approval_status=IECMaterial.APPROVED,
        )
        result = compute_I_BND_4_2('Bandhu', date(2026, 5, 21), date(2026, 11, 20))
        self.assertEqual(result, 2)  # sum of BILLBOARD + DIGITAL quantity
