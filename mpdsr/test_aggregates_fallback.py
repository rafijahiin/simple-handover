"""An empty Excel ingest must not blank the dashboard.

MPDSRFacilityCount holds programme-wide counts imported from Sayeed's reporting
sheet. Until that import runs the table is empty, and `.aggregate(Sum(...))`
returns a dict of Nones — which is still TRUTHY. The frontend guards with

    const d = totals ? excelNumbers : liveCounts   // "falls back to live-only
                                                   //  counts if the import
                                                   //  hasn't run"

so the all-empty dict defeated its own fallback: the Notified-vs-Reviewed panel
and the six Notifications-by-Level cells rendered 0 while 86 real notification
slips and 139 cases sat in the database.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from mpdsr.ciprb_models import MPDSRDeathNotification
from mpdsr.models import MPDSRFacilityCount


class AggregatesFallbackTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='agg@ciprb.org', password='p', full_name='Agg Tester',
            organisation=Organisation.CIPRB, role=Role.ORG_LEAD)
        self.client.force_authenticate(user=self.user)

    def _notif(self, kind, place, **over):
        kw = dict(district='Bhola', death_kind=kind, place_of_death=place,
                  slip_variant='01',
                  date_of_death='2026-07-01',
                  approval_status='APPROVED', organisation='CIPRB')
        kw.update(over)
        return MPDSRDeathNotification.objects.create(**kw)

    def _get(self):
        r = self.client.get('/api/mpdsr/aggregates/')
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_facility_totals_is_null_when_the_excel_import_has_not_run(self):
        """A dict of zeros is truthy and silently defeats the frontend fallback."""
        self.assertEqual(MPDSRFacilityCount.objects.count(), 0)
        self.assertIsNone(self._get()['facility_totals'])

    def test_notification_by_level_is_the_slip_variant_not_the_place(self):
        """CDN/FDN = which slip was filed. The old place-of-death split put a
        hospital death notified on the community slip under 'facility', and all
        41 facility-slip stillbirths under 'community' (Slip 02 has no place
        field) — exactly backwards, caught by Rafi on the live panel."""
        F = MPDSRDeathNotification.PLACE_FACILITY
        # A CHW files Slip 01 for a mother who died AT A FACILITY: still CDN.
        self._notif(MPDSRDeathNotification.KIND_MATERNAL, F, slip_variant='01')
        self._notif(MPDSRDeathNotification.KIND_MATERNAL, 'home', slip_variant='01')
        # Facility slip with NO place recorded (Slip 02 carries no place field).
        self._notif(MPDSRDeathNotification.KIND_STILLBIRTH, '', slip_variant='02')
        self._notif(MPDSRDeathNotification.KIND_NEONATAL, '', slip_variant='02')

        d = self._get()
        self.assertEqual(d['notification_by_level_source'], 'kobo')
        lvl = d['notification_by_level']
        self.assertEqual(lvl['md'], {'community': 2, 'facility': 0})
        self.assertEqual(lvl['sb'], {'community': 0, 'facility': 1})
        self.assertEqual(lvl['nd'], {'community': 0, 'facility': 1})
        self.assertEqual(d['notifications']['by_level'],
                         {'community': 2, 'facility': 2})

    def test_only_approved_notifications_are_counted(self):
        self._notif(MPDSRDeathNotification.KIND_MATERNAL, 'home')
        self._notif(MPDSRDeathNotification.KIND_MATERNAL, 'home',
                    approval_status='PENDING')
        self.assertEqual(
            self._get()['notification_by_level']['md']['community'], 1,
            'a pending slip must not count toward a published indicator')

    def test_excel_wins_when_the_import_has_run(self):
        MPDSRFacilityCount.objects.create(
            district='Bhola', facility_name='Sadar', period='2026-07',
            cdn_md=7, fdn_md=3, cdn_nd=0, fdn_nd=0, cdn_sb=0, fdn_sb=0,
            fdr_md=0, fdr_nd=0, fdr_sb=0,
        )
        self._notif(MPDSRDeathNotification.KIND_MATERNAL, 'home')

        d = self._get()
        self.assertEqual(d['notification_by_level_source'], 'excel')
        self.assertIsNotNone(d['facility_totals'])
        self.assertEqual(d['notification_by_level']['md'],
                         {'community': 7, 'facility': 3})

    def test_district_filter_still_applies_to_the_fallback(self):
        self._notif(MPDSRDeathNotification.KIND_MATERNAL, 'home', district='Bhola')
        self._notif(MPDSRDeathNotification.KIND_MATERNAL, 'home', district='Kurigram')
        r = self.client.get('/api/mpdsr/aggregates/?districts=Bhola')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json()['notification_by_level']['md']['community'], 1)


class ReviewCountsShapeTest(TestCase):
    """review_counts must never fabricate a 'notified' number from review forms.

    The old block set notified_md = f1 + f2 — maternal community reviews plus
    NEONATAL community reviews, labelled "MD notified" — and the dashboard used
    it as every review tile's denominator ("0 of 86 notified"). Notified counts
    come only from the notification slips."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user(
            email='rc@ciprb.org', password='p', full_name='RC',
            organisation=Organisation.CIPRB, role=Role.ORG_LEAD))

    def test_no_fabricated_notified_keys(self):
        from mpdsr.models import MPDSRCase
        MPDSRCase.objects.create(
            partner='CIPRB', sub_form_type='f1', district='Bhola',
            date_of_death='2026-06-01', death_type='maternal',
            approval_status='APPROVED', case_hash='rc-1')
        MPDSRCase.objects.create(
            partner='CIPRB', sub_form_type='f2', district='Bhola',
            date_of_death='2026-06-02', death_type='perinatal',
            approval_status='APPROVED', case_hash='rc-2')
        r = self.client.get('/api/mpdsr/aggregates/')
        rc = r.json()['review_counts']
        self.assertEqual(rc.get('f1'), 1)
        self.assertEqual(rc.get('f2'), 1)
        self.assertNotIn('notified_md', rc,
                         'review forms must not masquerade as notifications')
