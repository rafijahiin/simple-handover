"""Seed demo ServiceCenters + KoboSubmissions for PHD and Bandhu so the
OrgDashboard surfaces live numbers instead of mock fallback.

Idempotent: centres get stable codes (e.g. PHD-COXBAZ-001), submissions get a
deterministic kobo_id (DEMO-PHD-...), so re-runs do nothing.

Removable: --purge deletes only DEMO-prefixed rows; real data is untouched.
"""
import datetime
import random
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from programs.models.center import ServiceCenter
from submissions.models import KoboSubmission, FormType, SubmissionStatus


PHD_PROFILE = {
    # district: { 'centres': [(code_suffix, name, type, upazila, lat, lng), ...], 'monthly_volume': int }
    "Cox's Bazar": {
        'centres': [
            ('COXBAZ-CS',    "Cox's Bazar Civil Surgeon Office", 'sda',  'Sadar',  21.4272, 91.9810),
            ('COXBAZ-DH',    "Cox's Bazar District Hospital",    'sdp',  'Sadar',  21.4292, 91.9788),
        ],
        'monthly': 156,
    },
    'Ukhiya': {
        'centres': [
            ('UKHIYA-UHC',   'Ukhiya Upazila Health Complex',    'sdp',  'Ukhiya', 21.2566, 92.1234),
            ('UKHIYA-CAMP1', 'Rohingya Camp 1 PHD Outreach',     'oc',   'Ukhiya', 21.2300, 92.1500),
        ],
        'monthly': 89,
    },
    'Chattogram': {
        'centres': [
            ('CTG-MEMORIAL', 'Chattagram Maa Shishu Hospital',   'sdp',  'Sadar',  22.3569, 91.7832),
        ],
        'monthly': 78,
    },
    'Sylhet': {
        'centres': [
            ('SYL-OSMANI',   'Sylhet MAG Osmani Medical College','sdp',  'Sadar',  24.8949, 91.8687),
        ],
        'monthly': 56,
    },
    'Teknaf': {
        'centres': [
            ('TEKNAF-UHC',   'Teknaf Upazila Health Complex',    'sdp',  'Teknaf', 20.8654, 92.2978),
        ],
        'monthly': 46,
    },
}

BANDHU_PROFILE = {
    'Dhaka': {
        'centres': [
            ('DHK-MOHA',     'Mohammadpur Bandhu Centre',        'sda',  'Mohammadpur', 23.7651, 90.3590),
            ('DHK-MOTI',     'Motijheel Bandhu Drop-in Centre',  'sda',  'Motijheel',   23.7300, 90.4200),
        ],
        'monthly': 210,
    },
    'Chittagong': {
        'centres': [
            ('CTG-BAN-AGRA', 'Agrabad Bandhu Centre',            'sda',  'Agrabad', 22.3261, 91.8137),
        ],
        'monthly': 168,
    },
    'Sylhet': {
        'centres': [
            ('SYL-BAN',      'Sylhet Bandhu Centre',             'sda',  'Sadar',   24.8949, 91.8687),
        ],
        'monthly': 145,
    },
    'Narayanganj': {
        'centres': [
            ('NGJ-BAN',      'Narayanganj Bandhu Centre',        'sda',  'Sadar',   23.6238, 90.5000),
        ],
        'monthly': 102,
    },
    'Comilla': {
        'centres': [
            ('CML-BAN',      'Comilla Bandhu Centre',            'sda',  'Sadar',   23.4607, 91.1809),
        ],
        'monthly': 78,
    },
}

# Forms PHD/Bandhu actually submit day-to-day. ACTIVITY is the catch-all
# FormType these all classify under (see submissions/views.py form_type router).
# Fistula is intentionally excluded — PHD/Bandhu don't run fistula programmes;
# the webhook would otherwise auto-create empty FistulaCampaign rows that
# pollute the CIPRB dashboard's Campaign Reach aggregate.
DEMO_FORM_MIX = [FormType.ACTIVITY] * 10


class Command(BaseCommand):
    help = 'Seed demo ServiceCenters + KoboSubmissions for PHD/Bandhu (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--purge', action='store_true',
                            help='Delete demo rows instead of seeding.')

    def handle(self, *args, **opts):
        if opts['purge']:
            # Submissions: only DEMO-prefixed kobo_id rows.
            n_sub, _ = KoboSubmission.objects.filter(kobo_id__startswith='DEMO-').delete()

            # Centres: only the ones MY seed created. Codes are prefixed
            # PHD-... or BANDHU-... (set when this command writes). Real
            # seed_centers rows (e.g. "PHD Brothel 01", "Bandhu DIC Dhaka")
            # don't carry this prefix and may have FK-protected children
            # like OutreachSession; never touch them.
            from django.db.models import Q
            demo_centres = ServiceCenter.objects.filter(
                Q(code__startswith='PHD-') | Q(code__startswith='BANDHU-'),
            )
            n_ctr = 0
            for sc in demo_centres:
                try:
                    sc.delete()
                    n_ctr += 1
                except Exception as exc:  # FK-protected children
                    self.stdout.write(self.style.WARNING(
                        f'  skipped {sc.code} — protected child rows ({exc.__class__.__name__})'
                    ))
            self.stdout.write(self.style.WARNING(
                f'Purged {n_sub} demo submissions, {n_ctr} demo centres.'
            ))
            return

        # Always clean up any leaked Fistula submissions from older seed runs
        # (when DEMO_FORM_MIX included FISTULA the webhook auto-created empty
        # FistulaCampaign rows that broke the Campaign Reach aggregate).
        from fistula.models import FistulaCampaign
        FistulaCampaign.objects.filter(
            partner__in=('PHD', 'Bandhu'),
            households_visited=0,
        ).delete()

        rng = random.Random(20260602)
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        created_c = updated_c = 0
        created_s = skipped_s = 0

        for partner, profile in (('PHD', PHD_PROFILE), ('Bandhu', BANDHU_PROFILE)):
            for district, cfg in profile.items():
                for suffix, name, ctype, upazila, lat, lng in cfg['centres']:
                    code = f'{partner.upper()}-{suffix}' if not suffix.startswith(partner.upper()) else suffix
                    sc, was_created = ServiceCenter.objects.update_or_create(
                        code=code,
                        defaults={
                            'organisation': partner,
                            'name': name,
                            'center_type': ctype,
                            'district': district,
                            'upazila': upazila,
                            'latitude': lat,
                            'longitude': lng,
                            'is_active': True,
                        },
                    )
                    if was_created:
                        created_c += 1
                    else:
                        updated_c += 1

                # Distribute this district's monthly volume across its centres
                centres = [
                    f'{partner.upper()}-{s}' if not s.startswith(partner.upper()) else s
                    for s, *_ in cfg['centres']
                ]
                total = cfg['monthly']
                # Spread across a trailing ~24-day window (not just since the
                # 1st) so the 14-day sparkline is populated even early in a
                # month. Submissions landing in the current month still feed
                # the "this month" district counts.
                trailing_window = 24
                for i in range(total):
                    code = centres[i % len(centres)]
                    days_back = rng.randint(0, trailing_window)
                    submitted = now - datetime.timedelta(
                        days=days_back,
                        hours=rng.randint(0, 23),
                        minutes=rng.randint(0, 59),
                    )
                    form_type = rng.choice(DEMO_FORM_MIX)
                    kobo_id = f'DEMO-{partner}-{district[:6].replace(" ", "")}-{i:04d}'
                    if KoboSubmission.objects.filter(kobo_id=kobo_id).exists():
                        skipped_s += 1
                        continue
                    KoboSubmission.objects.create(
                        kobo_id=kobo_id,
                        form_type=form_type,
                        partner=partner,
                        worker_name=f'{partner} Field Worker',
                        district=district,
                        centre_code=code,
                        latitude=cfg['centres'][i % len(cfg['centres'])][4],
                        longitude=cfg['centres'][i % len(cfg['centres'])][5],
                        submitted_at=submitted,
                        raw_data={
                            'partner_org': partner,
                            'center_code': code,
                            'district': district,
                            '_source': 'demo_seed',
                        },
                        status=SubmissionStatus.APPROVED,
                    )
                    created_s += 1

        # One explicit "zero / no-activity" report per partner, dated today,
        # so the daily-compliance health flag demonstrates the feature: the
        # partner reported today even though a centre had no activity.
        zero_created = 0
        for partner, profile in (('PHD', PHD_PROFILE), ('Bandhu', BANDHU_PROFILE)):
            district, cfg = next(iter(profile.items()))
            suffix = cfg['centres'][0][0]
            code = f'{partner.upper()}-{suffix}' if not suffix.startswith(partner.upper()) else suffix
            kobo_id = f'DEMO-{partner}-ZERO-TODAY'
            if not KoboSubmission.objects.filter(kobo_id=kobo_id).exists():
                KoboSubmission.objects.create(
                    kobo_id=kobo_id,
                    form_type=FormType.ACTIVITY,
                    partner=partner,
                    worker_name=f'{partner} Field Worker',
                    district=district,
                    centre_code=code,
                    latitude=cfg['centres'][0][4],
                    longitude=cfg['centres'][0][5],
                    submitted_at=now,
                    raw_data={
                        'partner_org': partner, 'center_code': code,
                        'district': district, '_source': 'demo_seed',
                        'no_activity': 'yes',
                    },
                    status=SubmissionStatus.APPROVED,
                    is_zero_report=True,
                )
                zero_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Centres: {created_c} created, {updated_c} updated. '
            f'Submissions: {created_s} created, {skipped_s} skipped. '
            f'Zero-reports: {zero_created} created.'
        ))
