"""F-01 Wellness Centre Service Logbook — the CANONICAL Bandhu service record.

Each F-01 submission creates a reviewable WellnessLogbookEntry AND maps its
service ticks to columns that the Bandhu indicators read (2026-07 MIS rewire:
Bandhu files no F-05/F-06, so the logbook is the single source, not a double
count). The client ID is normalised to DD-NNNN so services link to the Mother
List."""
from datetime import date

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from programs.bandhu_handlers import handle_bandhu_service_log, _norm_client_id
from programs.models import ServiceCenter, WellnessLogbookEntry
from accounts.models import User
from indicators import bandhu as bnd


def _bandhu_center():
    # district Dhaka → Bandhu district code '09' (BANDHU_DISTRICT_CODE).
    return ServiceCenter.objects.create(
        organisation='Bandhu', name='Bandhu DIC', code='BAN-001',
        center_type=ServiceCenter.DIC, district='Dhaka', is_active=True,
    )


def _f01(kobo_id='9001', cid='01-0001', **services):
    payload = {
        'record_type': 'wellness_logbook',
        'center_code': 'BAN-001',
        'log_date': '2026-06-29',
        'log_client_id': cid,
        '_id': kobo_id,
        '_submitted_by': 'bandhu_field_worker',
    }
    payload.update(services)
    return handle_bandhu_service_log(payload, lat=23.7, lng=90.4)


class WellnessLogbookTest(TestCase):
    def setUp(self):
        cache.clear()
        self.center = _bandhu_center()

    def test_f01_creates_pending_reviewable_entry(self):
        resp = _f01()
        self.assertEqual(resp.status_code, 201)
        e = WellnessLogbookEntry.objects.get()
        self.assertEqual(e.organisation, 'Bandhu')
        self.assertEqual(e.approval_status, WellnessLogbookEntry.PENDING)
        self.assertEqual(e.client_id, '01-0001')
        self.assertEqual(str(e.service_date), '2026-06-29')
        self.assertTrue(e.raw_payload)  # full submission retained for the reviewer

    def test_f01_is_idempotent_on_redelivery(self):
        _f01(kobo_id='9001')
        _f01(kobo_id='9001')  # Kobo re-sends on redeploy — must not duplicate
        self.assertEqual(WellnessLogbookEntry.objects.count(), 1)

    def test_f01_surfaces_in_approval_queue(self):
        _f01()
        dev = User.objects.create_user(
            email='dev@x.org', password='Str0ng-Passw0rd-2026', full_name='Dev',
            organisation='CIPRB', role='developer',
        )
        c = APIClient()
        c.force_authenticate(dev)
        r = c.get('/api/programs/pending-approvals/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('wellness_logbook', str(r.content))

    def test_f01_populates_service_flags(self):
        _f01(log_htc='yes', log_gbv='yes', log_mental_health='yes',
             log_sti_screening='yes', log_counseling='no', log_iec='5',
             log_condom='3', log_tg='05', log_referral='art hiv')
        e = WellnessLogbookEntry.objects.get()
        self.assertTrue(e.htc and e.gbv and e.mental_health and e.sti_screening)
        self.assertFalse(e.counseling)
        self.assertEqual((e.iec, e.condom, e.tg_code), (5, 3, '05'))
        self.assertEqual(e.referral_codes, 'art hiv')

    def test_service_indicators_count_the_logbook_once_approved(self):
        _f01(log_htc='yes', log_gbv='yes', log_mental_health='yes',
             log_sti_screening='yes', log_iec='4')
        e = WellnessLogbookEntry.objects.get()
        p0, p1 = date(2026, 6, 1), date(2026, 6, 30)
        # PENDING → counts zero (two-stage approval gate).
        self.assertEqual(bnd.compute_I_BND_1_5_hiv('Bandhu', p0, p1), 0)
        e.approval_status = WellnessLogbookEntry.APPROVED
        e.save(update_fields=['approval_status'])
        self.assertEqual(bnd.compute_I_BND_1_5_hiv('Bandhu', p0, p1), 1)
        self.assertEqual(bnd.compute_I_BND_1_5_sti('Bandhu', p0, p1), 1)
        self.assertEqual(bnd.compute_I_BND_1_2('Bandhu', p0, p1), 1)
        self.assertEqual(bnd.compute_I_BND_1_3('Bandhu', p0, p1), 1)
        self.assertEqual(bnd.compute_I_BND_4_1('Bandhu', p0, p1), 4)

    def test_specific_model_row_does_not_double_the_logbook(self):
        # Single-source guard: a stray/legacy GBVCase in the same period must NOT
        # be summed on top of the logbook's gbv count (the review's HIGH finding).
        from programs.models import GBVCase
        p0, p1 = date(2026, 6, 1), date(2026, 6, 30)
        GBVCase.objects.create(
            organisation='Bandhu', center=self.center,
            interview_date=date(2026, 6, 10), incident_date=date(2026, 6, 10),
            approval_status=GBVCase.APPROVED,
        )
        _f01(kobo_id='7001', cid='09-0001', log_gbv='yes')
        e = WellnessLogbookEntry.objects.get()
        e.approval_status = WellnessLogbookEntry.APPROVED
        e.save(update_fields=['approval_status'])
        # logbook-only → 1 (the GBVCase is never added), not 2.
        self.assertEqual(bnd.compute_I_BND_1_2('Bandhu', p0, p1), 1)

    def test_six_digit_typo_id_left_verbatim(self):
        _f01(kobo_id='7002', cid='070002')  # DD+serial typed with no dash
        e = WellnessLogbookEntry.objects.get()
        self.assertEqual(e.client_id_norm, '070002')  # NOT mangled to a fake '09-070002'

    def test_bare_serial_id_normalised_to_dd_nnnn(self):
        _f01(cid='0002')  # bare serial, no district prefix
        e = WellnessLogbookEntry.objects.get()
        self.assertEqual(e.client_id, '0002')          # as-submitted kept verbatim
        self.assertEqual(e.client_id_norm, '09-0002')  # Dhaka centre → code 09

    def test_new_client_registered_inline_via_f01(self):
        from programs.models import Client
        _f01(cid='09-0100', ml_name='Rima', ml_gender='05', log_htc='yes')
        c = Client.objects.get(client_id='09-0100')
        self.assertEqual(c.name, 'Rima')
        self.assertEqual(c.approval_status, Client.APPROVED)  # Bandhu reg auto-approves
        self.assertEqual(WellnessLogbookEntry.objects.count(), 1)  # service logged too

    def test_returning_client_not_re_registered(self):
        from programs.models import Client
        Client.objects.create(
            client_id='09-0200', organisation='Bandhu', center=self.center,
            name='Existing', approval_status=Client.APPROVED,
        )
        _f01(cid='09-0200', log_htc='yes')  # no ml_name → no re-registration
        self.assertEqual(Client.objects.filter(client_id='09-0200').count(), 1)
        self.assertEqual(Client.objects.get(client_id='09-0200').name, 'Existing')

    def test_narrative_describes_the_services_not_just_the_title(self):
        # The approval card's "In plain language" line must read the service
        # ticks, not repeat the F-01 title. (Rafi: plain language was problematic.)
        from programs.views import _build_narrative
        _f01(cid='05-0010', log_tg='01', log_counseling='yes', log_htc='yes',
             log_condom='3', log_referral='ART')
        e = WellnessLogbookEntry.objects.get()
        text = _build_narrative(e, 'wellness_logbook')
        self.assertIn('MSM client', text)          # tg_code 01 → MSM
        self.assertIn('05-0010', text)
        self.assertIn('HIV test', text)
        self.assertIn('counselling', text)
        self.assertIn('3 condoms', text)
        self.assertIn('ART', text)
        self.assertNotIn('F-01 logbook', text)     # not the bare title fallback

    def test_narrative_handles_an_empty_logbook_gracefully(self):
        from programs.views import _build_narrative
        _f01(cid='09-0011')  # no service ticks
        e = WellnessLogbookEntry.objects.get()
        text = _build_narrative(e, 'wellness_logbook')
        self.assertIn('no services were recorded', text)

    def test_backfill_repairs_existing_rows(self):
        # An old-style row: flags empty, bare-serial id — as they exist in prod.
        _f01(cid='0007', log_htc='yes', log_iec='2')
        e = WellnessLogbookEntry.objects.get()
        e.htc = False; e.iec = 0; e.client_id_norm = ''      # simulate pre-rewire state
        e.save(update_fields=['htc', 'iec', 'client_id_norm'])
        from django.core.management import call_command
        call_command('backfill_wellness_logbook', '--commit')
        e.refresh_from_db()
        self.assertTrue(e.htc)
        self.assertEqual(e.iec, 2)
        self.assertEqual(e.client_id_norm, '09-0007')
