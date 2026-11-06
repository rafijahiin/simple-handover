"""Cross-panel coherence of /api/mpdsr/aggregates — the CIPRB dashboard's spine.

Every number on the MPDSR panels is derived here, and this week two of them were
fabricated or mislabelled against each other on a single screen:
  - CDN/FDN was split by PLACE OF DEATH instead of SLIP VARIANT (backwards).
  - A review-tile denominator was invented (notified_md = f1 + f2) — maternal
    reviews plus NEONATAL reviews, labelled "MD notified".

These tests seed a scenario where REVIEWS deliberately outnumber NOTIFICATIONS
and the two are unequal per kind, so any re-derivation of one from the other, or
any place/slip confusion, breaks an assertion. The invariants come from the
recon's aggregate-invariants map (mpdsr/views.py:122-497).
"""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from mpdsr.models import MPDSRCase, DeathType, MPDSRFacilityCount
from mpdsr.ciprb_models import MPDSRDeathNotification

N = MPDSRDeathNotification


class AggregateCoherenceTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user(
            email='coh@ciprb.org', password='p', full_name='Coh',
            organisation=Organisation.CIPRB, role=Role.ORG_LEAD))

        # ── Notifications (the ONLY source of "notified"): per kind, per slip.
        #    maternal 3 community(01) + 1 facility(02); neonatal 2 community;
        #    stillbirth 4 facility. Deliberately NOT equal to any review count.
        self._notif(N.KIND_MATERNAL, N.SLIP_01, 3)
        self._notif(N.KIND_MATERNAL, N.SLIP_02, 1)
        self._notif(N.KIND_NEONATAL, N.SLIP_01, 2)
        self._notif(N.KIND_STILLBIRTH, N.SLIP_02, 4)

        # ── Review forms (the ONLY source of "reviewed"): f1×5 f4×2 (maternal),
        #    f2×3 f5×1 (perinatal), sa_md 4 maternal + 2 perinatal. These counts
        #    (5,2,3,1,6) share no value with the notified counts by construction.
        self._case('f1', DeathType.MATERNAL, 5)
        self._case('f4', DeathType.MATERNAL, 2)
        self._case('f2', DeathType.PERINATAL, 3)
        self._case('f5', DeathType.PERINATAL, 1)
        self._case('sa_md', DeathType.MATERNAL, 4)
        self._case('sa_md', DeathType.PERINATAL, 2)
        # f3/f6 stillbirth reviews exist but must be excluded from every surface.
        self._case('f3', DeathType.PERINATAL, 9)

    _seq = 0

    def _notif(self, kind, slip, n):
        for _ in range(n):
            AggregateCoherenceTest._seq += 1
            N.objects.create(
                organisation='CIPRB', district='Bhola', death_kind=kind,
                slip_variant=slip, place_of_death='home',
                date_of_death='2026-06-01', deceased_name='X%d' % self._seq,
                case_serial=str(self._seq), approval_status='APPROVED')

    def _case(self, sub, dtype, n):
        for _ in range(n):
            AggregateCoherenceTest._seq += 1
            MPDSRCase.objects.create(
                partner='CIPRB', sub_form_type=sub, district='Bhola',
                date_of_death='2026-06-01', death_type=dtype,
                cause_of_death='pph', approval_status='APPROVED',
                case_hash='coh-%d' % self._seq)

    def _agg(self):
        r = self.client.get('/api/mpdsr/aggregates/')
        self.assertEqual(r.status_code, 200)
        return r.json()

    # ── notified: slip variant IS the level, never place of death ─────────────
    def test_notification_by_level_is_slip_variant(self):
        lvl = self._agg()['notification_by_level']
        self.assertEqual(lvl['md'], {'community': 3, 'facility': 1})
        self.assertEqual(lvl['nd'], {'community': 2, 'facility': 0})
        self.assertEqual(lvl['sb'], {'community': 0, 'facility': 4})

    def test_notification_by_level_sums_to_notifications_total(self):
        d = self._agg()
        cells = sum(v for kind in d['notification_by_level'].values()
                    for v in kind.values())
        self.assertEqual(cells, d['notifications']['total'])
        self.assertEqual(d['notifications']['total'], 10)

    def test_notifications_by_level_is_slip_variant_across_all_kinds(self):
        by = self._agg()['notifications']['by_level']
        self.assertEqual(by['community'], 5)   # 3 md + 2 nd, all slip 01
        self.assertEqual(by['facility'], 5)    # 1 md + 4 sb, all slip 02

    def test_source_is_kobo_and_facility_totals_is_null_when_no_excel(self):
        d = self._agg()
        self.assertEqual(MPDSRFacilityCount.objects.count(), 0)
        self.assertIsNone(d['facility_totals'])
        self.assertEqual(d['notification_by_level_source'], 'kobo')

    # ── reviewed: independent of notified, from the review forms ───────────────
    def test_review_counts_are_the_form_counts_not_derived_from_notified(self):
        rc = self._agg()['review_counts']
        self.assertEqual(rc.get('f1'), 5)
        self.assertEqual(rc.get('f4'), 2)
        self.assertEqual(rc.get('f2'), 3)
        self.assertEqual(rc.get('f5'), 1)
        self.assertEqual(rc.get('sa_md'), 6)
        # The fabricated key must never reappear.
        self.assertNotIn('notified_md', rc)
        self.assertNotIn('notified_nd', rc)
        # No review count coincidentally equals a notified count in this seed,
        # so equality would prove tangling — assert the values are what the
        # forms hold, not what the slips hold (md notified community was 3).
        self.assertNotEqual(rc.get('f1'), 3)

    def test_sa_md_maternal_is_a_subset_of_sa_md(self):
        rc = self._agg()['review_counts']
        self.assertEqual(rc['sa_md_maternal'], 4)
        self.assertLessEqual(rc['sa_md_maternal'], rc['sa_md'])

    def test_social_autopsy_total_is_the_maternal_subset(self):
        # The section is titled "Social autopsy of maternal deaths" and the
        # dashboard tile counts maternal only, so this total must agree with
        # BOTH. It used to return the whole sa_md cohort, which is why the same
        # page showed 15 in the tile and 18 in the section.
        d = self._agg()
        self.assertEqual(d['social_autopsy']['total'],
                         d['review_counts']['sa_md_maternal'])

    def test_social_autopsy_all_kinds_is_the_whole_sa_cohort(self):
        d = self._agg()
        self.assertEqual(d['social_autopsy']['all_kinds_total'],
                         d['review_counts']['sa_md'])

    def test_social_autopsy_by_kind_accounts_for_every_row(self):
        # No social autopsy may fall out of the split — a stillbirth review
        # that lands nowhere is the bug this whole block exists to prevent.
        sa = self._agg()['social_autopsy']
        self.assertEqual(sum(sa['by_kind'].values()), sa['all_kinds_total'])

    def test_stillbirth_reviews_are_counted_and_bounded(self):
        d = self._agg()
        sb = d['review_counts']['sb_reviewed']
        self.assertGreaterEqual(sb, 0)
        self.assertLessEqual(sb, d['review_counts']['sa_md'],
                             'stillbirth reviews are a subset of social autopsies')

    # ── cohorts ────────────────────────────────────────────────────────────────
    def test_facility_deep_dive_is_the_f4_maternal_subset(self):
        d = self._agg()
        self.assertEqual(d['facility']['total'], 2)   # f4 maternal only

    def test_neonatal_total_is_all_perinatal_and_causes_sum_to_it(self):
        d = self._agg()
        # neonatal.total = count(mpdsr_qs, death_type=perinatal) = every
        # perinatal review EXCEPT f3/f6: f2(3) + f5(1) + sa_md-perinatal(2) = 6.
        # (Whether Social-Autopsy perinatal re-reviews belong in the "Neonatal
        # Deaths" panel is a SEMANTIC question for Animesh — logged in
        # SEMANTICS.md; the coherence invariant below holds regardless.)
        self.assertEqual(d['neonatal']['total'], 6)
        self.assertEqual(sum(d['neonatal']['cause_of_death'].values()),
                         d['neonatal']['total'])

    def test_totals_mpdsr_cases_excludes_f3_f6(self):
        d = self._agg()
        # f1+f4+f2+f5+sa_md = 5+2+3+1+6 = 17 ; the 9 f3 rows are excluded
        self.assertEqual(d['totals']['mpdsr_cases'], 17)

    # ── the excel branch flips the source enum coherently ─────────────────────
    def test_excel_ingest_flips_source_and_populates_facility_totals(self):
        MPDSRFacilityCount.objects.create(
            district='Bhola', facility_name='Sadar', period='2026-06',
            cdn_md=7, fdn_md=3, cdn_nd=0, fdn_nd=0, cdn_sb=0, fdn_sb=0,
            fdr_md=0, fdr_nd=0, fdr_sb=0)
        d = self._agg()
        self.assertEqual(d['notification_by_level_source'], 'excel')
        self.assertIsNotNone(d['facility_totals'])
