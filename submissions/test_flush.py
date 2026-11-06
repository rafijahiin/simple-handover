"""flush_practice_data — wipes practice/demo/Excel data, keeps configuration."""
import datetime
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import Organisation, Role, User
from programs.models import ServiceCenter
from indicators.models import IndicatorTarget
from submissions.models import KoboSubmission, FormType, SubmissionStatus
from fistula.ciprb_models import CIPRBFistulaCase
from mpdsr.models import MPDSRCase, DeathType, ReviewStatus
from baseline.models import BaselineResponse
from pharmacy.models import PrescriptionRecord, Drug
from partners.models import Partner


class FlushPracticeDataTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='x@y.org', password='p', full_name='X',
            organisation=Organisation.CIPRB, role=Role.MANAGER)
        self.real_centre = ServiceCenter.objects.create(
            organisation='PHD', name='Real Wellness Centre', code='BND-DIC-99',
            center_type=ServiceCenter.BROTHEL, district='Rajbari')
        self.demo_centre = ServiceCenter.objects.create(
            organisation='PHD', name='Demo Centre', code='PHD-demo1',
            center_type=ServiceCenter.BROTHEL, district='Dhaka')
        self.targets_before = IndicatorTarget.objects.count()

        KoboSubmission.objects.create(
            kobo_id='k1', form_type=FormType.MPDSR, partner='CIPRB',
            district='Dhaka', region='Dhaka', submitted_at=timezone.now(),
            raw_data={}, status=SubmissionStatus.APPROVED)
        CIPRBFistulaCase.objects.create(
            organisation='CIPRB', district='Dhaka', name='Patient',
            current_stage=CIPRBFistulaCase.STAGE_REPAIRED, approval_status='APPROVED')
        MPDSRCase.objects.create(
            organisation='CIPRB', partner='CIPRB', district='Dhaka', region='Dhaka',
            date_of_death=datetime.date.today(), death_type=DeathType.MATERNAL,
            cause_of_death='Hemorrhage', status=ReviewStatus.REPORTED,
            approval_status='APPROVED')
        BaselineResponse.objects.create(population='hijra', district='Dhaka')
        # Pharmacy data — direct manager entry, NOT via KoboSubmission. Proves the
        # dynamic all-apps approval_status sweep reaches beyond the programs app.
        PrescriptionRecord.objects.create(
            client_id='C-1', partner=Partner.objects.first(), center=self.real_centre,
            date=datetime.date.today(), drug=Drug.choices[0][0], quantity=1)

    def test_dry_run_deletes_nothing(self):
        call_command('flush_practice_data', stdout=StringIO())
        self.assertEqual(KoboSubmission.objects.count(), 1)
        self.assertEqual(CIPRBFistulaCase.objects.count(), 1)
        self.assertEqual(BaselineResponse.objects.count(), 1)

    def test_confirm_wipes_data_keeps_config(self):
        self.assertGreater(self.targets_before, 0)  # migrations seed targets
        call_command('flush_practice_data', confirm=True, stdout=StringIO())

        # All practice data gone.
        self.assertEqual(KoboSubmission.objects.count(), 0)
        self.assertEqual(CIPRBFistulaCase.objects.count(), 0)
        self.assertEqual(MPDSRCase.objects.count(), 0)
        self.assertEqual(BaselineResponse.objects.count(), 0)
        self.assertEqual(PrescriptionRecord.objects.count(), 0)  # pharmacy swept too

        # Configuration preserved.
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(ServiceCenter.objects.filter(code='BND-DIC-99').exists())
        self.assertEqual(IndicatorTarget.objects.count(), self.targets_before)

        # Demo centre removed, real registry intact.
        self.assertFalse(ServiceCenter.objects.filter(code='PHD-demo1').exists())
