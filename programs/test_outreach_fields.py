"""Bandhu F-04 Daily Outreach — count columns must reflect the real submission,
not a uniform "0 contacts / 0 condoms".

Covers the group-key path (grouped Kobo keys map to the columns), the backfill
that repairs rows frozen at 0 before the flattener existed, and the plain-language
narrative that lists what was actually distributed / referred.
"""
from datetime import date

from django.core.management import call_command
from django.test import TestCase

from programs.models import ServiceCenter, OutreachSession
from programs.webhook import _flatten_group_keys
from programs.bandhu_handlers import handle_bandhu_activity_ops
from programs.views import _build_narrative, _build_summary


def _center():
    return ServiceCenter.objects.create(
        organisation='Bandhu', name='X', code='BAN-001',
        center_type=ServiceCenter.DIC, district='Chittagong', is_active=True)


def _grouped_payload(_id='55501'):
    return {
        '_id': _id, '_submitted_by': 'w', 'record_type': 'outreach',
        'center_code': 'BAN-001',
        'grp_outreach/or_date': '2026-06-30',
        'grp_outreach/or_peer_educator': 'Faruk',
        'grp_outreach/or_spot': 'Sholokbohor',
        'grp_outreach/or_condom': '50',
        'grp_outreach/or_lubricant': '15',
        'grp_outreach/or_awareness': '2',
        'grp_outreach/or_ref_counseling': '4',
        'grp_outreach/or_ref_recreation': '6',
    }


class OutreachFieldsTest(TestCase):
    def setUp(self):
        self.center = _center()

    def test_grouped_payload_maps_counts(self):
        handle_bandhu_activity_ops(_flatten_group_keys(_grouped_payload()), lat=23.7, lng=90.4)
        o = OutreachSession.objects.get()
        self.assertEqual(o.condoms_distributed_free, 50)
        self.assertEqual(o.lubricants_distributed_free, 15)
        self.assertEqual(o.hiv_aids_sti_knowledge_sessions, 2)
        self.assertEqual(o.referral_other, 10)  # counseling 4 + recreation 6

    def test_backfill_repairs_a_row_frozen_at_zero(self):
        # A pre-flattener row: raw_payload holds the grouped keys, but the count
        # columns were saved as 0 because the handler could not read them then.
        o = OutreachSession.objects.create(
            organisation='Bandhu', center=self.center,
            session_date=date(2026, 6, 30), peer_educator_name='Faruk',
            condoms_distributed_free=0, hiv_aids_sti_knowledge_sessions=0,
            raw_payload=_grouped_payload(), kobo_submission_id='55501',
        )
        call_command('backfill_outreach_fields', '--commit')
        o.refresh_from_db()
        self.assertEqual(o.condoms_distributed_free, 50)
        self.assertEqual(o.hiv_aids_sti_knowledge_sessions, 2)
        self.assertEqual(o.referral_other, 10)

    def test_narrative_lists_distributions_and_referrals(self):
        handle_bandhu_activity_ops(_flatten_group_keys(_grouped_payload()), lat=23.7, lng=90.4)
        o = OutreachSession.objects.get()
        text = _build_narrative(o, 'outreach_session')
        self.assertIn('Sholokbohor', text)
        self.assertIn('50 condoms', text)
        self.assertIn('2 awareness sessions', text)
        self.assertIn('10 referrals', text)
        self.assertNotIn('individual contact', text)  # 0 for Bandhu → omitted
        # header summary likewise drops the empty "0 contacts"
        self.assertNotIn('0 contacts', _build_summary(o, 'outreach_session'))

    def test_empty_outreach_reads_cleanly(self):
        o = OutreachSession.objects.create(
            organisation='Bandhu', center=self.center,
            session_date=date(2026, 6, 30), peer_educator_name='Faruk')
        self.assertIn('recorded no distributions or referrals',
                      _build_narrative(o, 'outreach_session'))
