"""
CIPRB handover prune command (programs/management/commands/prune_partner_data.py).

Proves the three things that must hold for the handover migration:
  1. Partner (PHD/Bandhu) service-delivery data is deleted, in a PROTECT-safe
     order (ClinicVisit before Client before ServiceCenter).
  2. CIPRB data (mpdsr/fistula/baseline/training) and CIPRB infra (CIPRB-org
     centres and users) survive.
  3. Keep-by-reference works: a KoboSubmission, ServiceCenter, or User that a
     CIPRB record points at is kept even if it would otherwise be a partner row
     (attribution rule).
"""
from datetime import date

from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from programs.models import ServiceCenter, Client, ClinicVisit
from submissions.models import KoboSubmission
from mpdsr.ciprb_models import MPDSRDeathNotification
from baseline.models import BaselineSurvey
from training.models import TrainingSession


def _seed():
    center_ciprb = ServiceCenter.objects.create(
        organisation='CIPRB', name='CIPRB HQ', code='C1',
        center_type=ServiceCenter.KP_CLINIC, district='Dhaka')
    center_phd = ServiceCenter.objects.create(
        organisation='PHD', name='Dhaka Brothel (PHD)', code='P1',
        center_type=ServiceCenter.BROTHEL, district='Dhaka')

    user_ciprb = User.objects.create_user(
        'admin@ciprb.test', 'x', full_name='CIPRB Admin', organisation='CIPRB')
    user_phd = User.objects.create_user(
        'mgr@phd.test', 'x', full_name='PHD Manager', organisation='PHD')

    client_phd = Client.objects.create(
        organisation='PHD', center=center_phd, client_id='PHD-0001',
        name='A Client')
    ClinicVisit.objects.create(
        organisation='PHD', center=center_phd, client=client_phd,
        visit_date=date(2026, 6, 1))

    sub_partner = KoboSubmission.objects.create(
        kobo_id='activity-1', form_type='activity', partner='PHD',
        submitted_at='2026-06-01T00:00:00Z', raw_data={})
    sub_ciprb = KoboSubmission.objects.create(
        kobo_id='mpdsr-1', form_type='mpdsr', partner='CIPRB',
        submitted_at='2026-06-01T00:00:00Z', raw_data={})

    # CIPRB record pointing at the CIPRB submission + CIPRB centre, but
    # approved_by a PHD user on purpose: that PHD user must be KEPT.
    MPDSRDeathNotification.objects.create(
        submission=sub_ciprb, center=center_ciprb, approved_by=user_phd,
        district='Dhaka', death_kind=MPDSRDeathNotification.KIND_MATERNAL,
        deceased_name='Deceased', date_of_death=date(2026, 5, 20),
        reporter_name='Reporter')

    BaselineSurvey.objects.create(partner='PHD', district='Dhaka')
    TrainingSession.objects.create(partner='PHD', topic='CHW training',
                                   date=date(2026, 6, 10))
    return {'sub_ciprb': sub_ciprb.pk, 'user_phd': user_phd.pk}


class PrunePartnerDataTests(TestCase):

    def test_dry_run_changes_nothing(self):
        _seed()
        before = {m: m.objects.count() for m in
                  (Client, ClinicVisit, ServiceCenter, User, KoboSubmission,
                   MPDSRDeathNotification)}
        call_command('prune_partner_data')  # no --apply
        for model, count in before.items():
            self.assertEqual(model.objects.count(), count,
                             f'{model.__name__} changed during dry run')

    def test_apply_removes_partner_keeps_ciprb(self):
        ids = _seed()
        call_command('prune_partner_data', '--apply', '--yes-i-have-a-backup')

        # Partner service-delivery data gone (PROTECT order held, no error).
        self.assertEqual(ClinicVisit.objects.count(), 0)
        self.assertEqual(Client.objects.count(), 0)

        # Non-CIPRB centre gone, CIPRB centre kept.
        self.assertEqual(
            list(ServiceCenter.objects.values_list('organisation', flat=True)),
            ['CIPRB'])

        # Partner submission gone, CIPRB-referenced submission kept.
        self.assertEqual(
            list(KoboSubmission.objects.values_list('pk', flat=True)),
            [ids['sub_ciprb']])

        # CIPRB data kept in full.
        self.assertEqual(MPDSRDeathNotification.objects.count(), 1)
        self.assertEqual(BaselineSurvey.objects.count(), 1)
        self.assertEqual(TrainingSession.objects.count(), 1)

        # Both users kept: CIPRB by org, PHD by reference (approved a CIPRB record).
        self.assertEqual(User.objects.count(), 2)
        self.assertTrue(User.objects.filter(pk=ids['user_phd']).exists())

        # The CIPRB record's links still resolve.
        n = MPDSRDeathNotification.objects.get()
        self.assertEqual(n.submission_id, ids['sub_ciprb'])
        self.assertIsNotNone(n.center_id)
        self.assertEqual(n.approved_by_id, ids['user_phd'])

    def test_apply_requires_backup_flag(self):
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('prune_partner_data', '--apply')
