"""Smoke-test the FISTULA_STAGED + MPDSR_RESPONSE_PLAN dispatch by
synthesising KoboSubmission rows with realistic payloads, marking them
APPROVED, and verifying the downstream FistulaCornerCase + MPDSRActionPlanSummary
rows get created/updated by the signal handlers.

Run: python manage.py test_staged_dispatch
"""
import datetime
import random
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from submissions.models import KoboSubmission, FormType, SubmissionStatus


FISTULA_ASSET_UID = 'a4N3C9eZvUM5UJetngf5h7'
MPDSR_RP_ASSET_UID = 'aVMRPKVUdwcVAcixBszUKU'


def _fistula_suspected_payload(patient_id, district='Sunamganj'):
    return {
        '_xform_id_string': FISTULA_ASSET_UID,
        'stage': 'suspected',
        'patient_id': patient_id,
        'auto_id_seed': patient_id,
        'district': district.lower().replace(' ', '_'),
        'partner_org': 'CIPRB',
        'pt_name': f'Test Patient {patient_id[-6:]}',
        'pt_age': random.randint(18, 50),
        'husband_name': f'Test Husband {patient_id[-6:]}',
        'pt_contact': '01700000000',
        'addr_village': 'Test Village',
        'addr_union': 'Test Union',
        'addr_upazila': 'Sadar',
        'date_suspected': timezone.now().date().isoformat(),
    }


def _fistula_diagnosed_payload(patient_id, district='Sunamganj'):
    return {
        '_xform_id_string': FISTULA_ASSET_UID,
        'stage': 'diagnosed',
        'patient_id': patient_id,
        'district': district.lower().replace(' ', '_'),
        'partner_org': 'CIPRB',
        'date_diagnosed': timezone.now().date().isoformat(),
        'place_diagnosed': f'{district} District Hospital',
        'diagnosis_by': 'Dr. Test',
    }


def _fistula_referred_payload(patient_id, district='Sunamganj'):
    return {
        '_xform_id_string': FISTULA_ASSET_UID,
        'stage': 'referred',
        'patient_id': patient_id,
        'district': district.lower().replace(' ', '_'),
        'partner_org': 'CIPRB',
        'refer_date': timezone.now().date().isoformat(),
        'refer_place': 'Dhaka Medical College Fistula Centre',
        'referrer': 'CIPRB field officer',
        'refer_outcome': 'Patient accepted referral',
    }


def _fistula_repaired_payload(patient_id, district='Sunamganj'):
    return {
        '_xform_id_string': FISTULA_ASSET_UID,
        'stage': 'repaired',
        'patient_id': patient_id,
        'district': district.lower().replace(' ', '_'),
        'partner_org': 'CIPRB',
        'op_date': timezone.now().date().isoformat(),
        'op_place': 'Dhaka Medical College',
        'cause_type': random.choice(['obstetric', 'iatrogenic']),
        'fistula_anatomy': random.choice(['vvf', 'rvf']),
        'op_outcome': random.choice(['success_dry', 'success_not_dry']),
    }


def _fistula_rehabilitated_payload(patient_id, district='Sunamganj'):
    return {
        '_xform_id_string': FISTULA_ASSET_UID,
        'stage': 'rehabilitated',
        'patient_id': patient_id,
        'district': district.lower().replace(' ', '_'),
        'partner_org': 'CIPRB',
        'rehab_received': 'yes',
        'rehab_date': timezone.now().date().isoformat(),
        'rehab_place': 'ngo',
        'rehab_types': 'cash training psycho',
    }


def _mpdsr_response_plan_payload(district='Sunamganj'):
    p = {
        '_xform_id_string': MPDSR_RP_ASSET_UID,
        'district': district.lower().replace(' ', '_'),
        'meeting_level': 'DM',
        'meeting_date': timezone.now().date().isoformat(),
        'place_of_meeting': f'{district} EPI Bhobon',
        'participants_count': 12,
        'partner_org': 'CIPRB',
    }
    # System Strengthening section — 5 actions, 3 implemented
    for i in range(1, 6):
        p[f'sys_strengthen_a{i}_action_taken'] = f'Refresher training for FWAs (action {i})'
        p[f'sys_strengthen_a{i}_responsible'] = 'UH&FPO'
        p[f'sys_strengthen_a{i}_status'] = 'implemented' if i <= 3 else 'in_progress'
    # Community VA section — 4 actions, 2 implemented
    for i in range(1, 5):
        p[f'community_va_a{i}_action_taken'] = f'Community engagement (action {i})'
        p[f'community_va_a{i}_status'] = 'implemented' if i <= 2 else 'pending'
    # Facility DR section — 3 actions, 1 implemented
    for i in range(1, 4):
        p[f'facility_dr_a{i}_action_taken'] = f'SOP review (action {i})'
        p[f'facility_dr_a{i}_status'] = 'implemented' if i == 1 else 'delayed'
    return p


class Command(BaseCommand):
    help = 'Smoke-test staged-form dispatchers with synthetic KoboSubmissions.'

    def handle(self, *args, **opts):
        from fistula.models import FistulaCornerCase
        from mpdsr.models import MPDSRActionPlanSummary

        rng = random.Random(20260603)
        now = timezone.now()
        created_subs = 0

        # 5 patients × 5 stages each = 25 fistula submissions
        STAGES = [
            ('suspected', _fistula_suspected_payload),
            ('diagnosed', _fistula_diagnosed_payload),
            ('referred', _fistula_referred_payload),
            ('repaired', _fistula_repaired_payload),
            ('rehabilitated', _fistula_rehabilitated_payload),
        ]

        for patient_idx in range(1, 6):
            district = rng.choice(['Sunamganj', 'Bhola', 'Sherpur', 'Bandarban', 'Noakhali'])
            pid = f"{district.upper().replace(' ', '')}-2026-{patient_idx:06d}"
            for stage_name, fn in STAGES:
                payload = fn(pid, district)
                kobo_id = f'TEST-FS-{pid}-{stage_name}'
                if KoboSubmission.objects.filter(kobo_id=kobo_id).exists():
                    continue
                sub = KoboSubmission.objects.create(
                    kobo_id=kobo_id,
                    form_type=FormType.FISTULA_STAGED,
                    partner='CIPRB',
                    worker_name='test_staged_dispatch',
                    district=district,
                    latitude=23.7,
                    longitude=90.4,
                    submitted_at=now,
                    raw_data=payload,
                    status=SubmissionStatus.APPROVED,  # triggers signal
                )
                created_subs += 1
                self.stdout.write(f'  [ok] {pid} -> {stage_name}')

        # 3 MPDSR Response Plan submissions in different districts
        for district in ['Sunamganj', 'Sherpur', 'Bhola']:
            payload = _mpdsr_response_plan_payload(district)
            kobo_id = f'TEST-MPDSR-RP-{district}'
            if KoboSubmission.objects.filter(kobo_id=kobo_id).exists():
                continue
            KoboSubmission.objects.create(
                kobo_id=kobo_id,
                form_type=FormType.MPDSR_RESPONSE_PLAN,
                partner='CIPRB',
                worker_name='test_staged_dispatch',
                district=district,
                latitude=23.7,
                longitude=90.4,
                submitted_at=now,
                raw_data=payload,
                status=SubmissionStatus.APPROVED,
            )
            created_subs += 1
            self.stdout.write(f'  [ok] Response Plan submitted for {district}')

        # Verify
        new_corners = FistulaCornerCase.objects.filter(source='kobo_staged').count()
        new_aps = MPDSRActionPlanSummary.objects.filter(source='kobo_response_plan').count()
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Created {created_subs} test submissions. '
            f'Downstream: {new_corners} FistulaCornerCase rows, '
            f'{new_aps} MPDSRActionPlanSummary rows.'
        ))

        # Per-patient stage walk
        from collections import defaultdict
        by_pid = defaultdict(list)
        for c in FistulaCornerCase.objects.filter(source='kobo_staged'):
            stages = []
            if c.suspected_date: stages.append('S')
            if c.diagnosis_date: stages.append('D')
            if c.referral_date: stages.append('R')
            if c.surgery_performed == 'yes': stages.append('Op')
            if c.received_rehab_support: stages.append('Rh')
            by_pid[c.patient_id] = stages
        self.stdout.write('Per-patient stage progression:')
        for pid, st in sorted(by_pid.items()):
            self.stdout.write(f'  {pid}: {" -> ".join(st)}')
