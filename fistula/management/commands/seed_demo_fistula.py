"""Seed demo Fistula Corner cases + Mass Campaign visits for the CIPRB
dashboard. Idempotent; --purge removes only DEMO-* rows.
"""
import datetime
import random
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from fistula.models import FistulaCornerCase, FistulaCampaign


DISTRICTS = [
    ('Sunamganj',   18),
    ('Sherpur',     14),
    ('Bhola',       12),
    ('Khagrachari', 10),
    ('Noakhali',    11),
    ('Chandpur',     8),
    ('Gaibandha',    6),
]

CAUSES_KOBO = [
    'Prolonged/Obstructed Labour',
    'Prolonged/Obstructed Labour',
    'Prolonged/Obstructed Labour',
    'Early Marriage/Adolescent Pregnancy',
    'Unsafe Abortion',
    'Surgical Injury',
    'Surgical Injury',
    'Gender-Based Violence',
    'Unknown',
]

CAMPAIGN_DISTRICTS = ['Sunamganj', 'Sherpur', 'Bhola', 'Khagrachari']


class Command(BaseCommand):
    help = 'Seed demo Fistula Corner cases + Mass Campaign visits.'

    def add_arguments(self, parser):
        parser.add_argument('--purge', action='store_true')

    def handle(self, *args, **opts):
        if opts['purge']:
            n1, _ = FistulaCornerCase.objects.filter(case_hash__startswith='DEMO-').delete()
            n2, _ = FistulaCampaign.objects.filter(case_hash__startswith='DEMO-').delete()
            self.stdout.write(self.style.WARNING(f'Purged {n1} corner cases, {n2} campaign visits.'))
            return

        rng = random.Random(20260603)
        today = timezone.now().date()
        created_c = skipped_c = 0
        created_v = skipped_v = 0

        # ----- Corner cases (clinical / facility walk-ins) -----
        for district, count in DISTRICTS:
            for i in range(count):
                ch = f'DEMO-FC-{district[:6]}-{i:03d}'
                if FistulaCornerCase.objects.filter(case_hash=ch).exists():
                    skipped_c += 1
                    continue
                # 70% of cases inside the current Contract window (last 12 days),
                # 30% spread further back so trend charts have shape.
                if rng.random() < 0.7:
                    diag_offset = rng.randint(0, 11)
                else:
                    diag_offset = rng.randint(12, 150)
                susp_offset = diag_offset + rng.randint(7, 30)
                ftype = rng.choices(
                    [FistulaCornerCase.VVF, FistulaCornerCase.RVF, FistulaCornerCase.BOTH, FistulaCornerCase.OTHER],
                    weights=[70, 12, 10, 8],
                )[0]
                cause = rng.choice(CAUSES_KOBO)
                surgery = rng.choices(
                    [FistulaCornerCase.SURGERY_YES, FistulaCornerCase.SURGERY_NO, FistulaCornerCase.SURGERY_PENDING],
                    weights=[55, 15, 30],
                )[0]
                # Rehab — Animesh's definition: any of 9 support types =
                # rehabilitated. Only operated patients are eligible. Seed
                # ~50% of operated patients as rehabilitated to give the
                # tile a meaningful 30–50% value on screen.
                operated = surgery == FistulaCornerCase.SURGERY_YES
                # Surgical outcome — only meaningful for operated cases.
                # ~68% dry, ~22% not-dry, ~10% failed (typical fistula-repair
                # success profile). Dashboard reports the two successful ones.
                surgery_outcome = ''
                if operated:
                    surgery_outcome = rng.choices(
                        [FistulaCornerCase.OUTCOME_DRY,
                         FistulaCornerCase.OUTCOME_NOT_DRY,
                         FistulaCornerCase.OUTCOME_FAILED],
                        weights=[68, 22, 10],
                    )[0]
                rehabbed = operated and rng.random() < 0.55
                support_options = [
                    'Cash', 'Training', 'Psychosocial support',
                    'Reintegration support', 'Sewing machine', 'VGF Card',
                ]
                support_types = (
                    ','.join(rng.sample(support_options, k=rng.randint(1, 3)))
                    if rehabbed else ''
                )

                FistulaCornerCase.objects.create(
                    case_hash=ch,
                    source='demo_seed',
                    district=district,
                    upazila='Sadar',
                    age_years=rng.randint(18, 55),
                    suspected_date=today - datetime.timedelta(days=susp_offset),
                    identification_date=today - datetime.timedelta(days=susp_offset - 5),
                    diagnosis_date=today - datetime.timedelta(days=diag_offset),
                    fistula_type=ftype,
                    fistula_cause=cause,
                    surgery_performed=surgery,
                    surgery_outcome=surgery_outcome,
                    referral_date=today - datetime.timedelta(days=max(1, diag_offset - 3)) if surgery != FistulaCornerCase.SURGERY_NO else None,
                    referral_place='Dhaka Medical College Fistula Centre',
                    received_rehab_support=rehabbed,
                    rehab_support_types=support_types,
                    rehab_support_date=(
                        today - datetime.timedelta(days=max(1, diag_offset - 14))
                        if rehabbed else None
                    ),
                )
                created_c += 1

        # ----- Campaign visits (community house-to-house screening) -----
        # 2-3 visits per campaign district, spread across recent months.
        for district in CAMPAIGN_DISTRICTS:
            n_visits = rng.randint(2, 4)
            for i in range(n_visits):
                ch = f'DEMO-CV-{district[:6]}-{i:02d}'
                if FistulaCampaign.objects.filter(case_hash=ch).exists():
                    skipped_v += 1
                    continue
                households = rng.randint(80, 220)
                population = households * rng.randint(4, 6)
                screened = rng.randint(60, 160)
                # Suspected is the top of the funnel — it must sum well above
                # the diagnosed (Fistula Corner) count so the pipeline reads
                # logically (≈60% of suspected go on to be diagnosed).
                suspected = rng.randint(8, 16)
                confirmed = rng.randint(max(1, suspected // 2), max(1, suspected - 2))
                FistulaCampaign.objects.create(
                    case_hash=ch,
                    partner='CIPRB',
                    district=district,
                    upazila='Sadar',
                    campaign_date=today - datetime.timedelta(
                        days=rng.randint(0, 10) if rng.random() < 0.7 else rng.randint(10, 140)
                    ),
                    households_visited=households,
                    population_covered=population,
                    women_screened=screened,
                    women_reached_awareness=screened * 2,
                    men_reached_awareness=rng.randint(30, 80),
                    community_sessions=rng.randint(1, 4),
                    suspected_fistula_cases=suspected,
                    confirmed_fistula_cases=confirmed,
                    new_cases=confirmed,
                    cases_referred=confirmed,
                    cases_accepted_referral=max(0, confirmed - rng.randint(0, 1)),
                    cases_reached_facility=max(0, confirmed - rng.randint(0, 2)),
                    cases_surgery_completed=max(0, confirmed - rng.randint(1, 2)),
                    cases_followup_completed=rng.randint(0, max(1, confirmed - 1)),
                    cases_counselling_provided=screened,
                )
                created_v += 1

        self.stdout.write(self.style.SUCCESS(
            f'Corner cases: {created_c} created, {skipped_c} skipped. '
            f'Campaign visits: {created_v} created, {skipped_v} skipped.'
        ))
