"""Seed plausible demo MPDSR cases so the CIPRB dashboard visualisations render.

Idempotent: uses a stable case_hash prefix `DEMO-` so re-runs do nothing.
Removable: `--purge` deletes only DEMO- rows; production data is untouched.
"""
import datetime
import random

from django.core.management.base import BaseCommand
from django.utils import timezone

from mpdsr.models import (
    MPDSRCase, DeathType, PlaceOfDeath, ReviewStatus,
    MPDSRDistrictDenominator, MPDSRFacilityCount, MPDSRActionPlanSummary,
)


# Per MPDSR Form 01 (Sayed 2026-06-02) — GoB ICD-10 cause taxonomy.
# Weighted to reflect typical Bangladesh maternal-mortality cause profile:
# Haemorrhage and Eclampsia together dominate (~50%), then Sepsis,
# Obstructed Labour, Abortion-related, Other Direct.
CAUSES = [
    # Haemorrhage cluster (35%)
    'PPH (Postpartum Haemorrhage)',
    'PPH (Postpartum Haemorrhage)',
    'APH (Antepartum Haemorrhage)',
    'Placenta Previa',
    'Abruptio placentae',
    'Rupture Uterus',
    'Haemorrhage in Early Pregnancy',
    # Eclampsia (18%)
    'Eclampsia',
    'Eclampsia',
    'Eclampsia',
    # Sepsis (12%)
    'Puerperal Sepsis',
    'Puerperal Sepsis',
    # Obstructed Labour (10%)
    'Obstructed Labour due to Malposition',
    'Obstructed Labour',
    # Abortion-related (10%)
    'Unsafe / Failed Abortion',
    'Ectopic Pregnancy',
    # Other Direct (15%)
    'Complication of Anaesthesia',
    'Obstetric Embolism',
    'Malnutrition in pregnancy',
]

PLACES = [PlaceOfDeath.FACILITY, PlaceOfDeath.HOME, PlaceOfDeath.IN_TRANSIT]

DEMO_PROFILE = {
    'Bandarban':    {'md': 6, 'pd': 2},
    'Barguna':      {'md': 14, 'pd': 5},
    'Chandpur':     {'md': 32, 'pd': 11},
    'Gaibandha':    {'md': 27, 'pd': 9},
    'Khagrachari':  {'md': 10, 'pd': 3},
    'Noakhali':     {'md': 41, 'pd': 14},
    'Patuakahli':   {'md': 35, 'pd': 12},
}

# Per-district denominators — Animesh's "Project Deaths 2026" (Live Birth ×
# 136/100k for MD, ×20/1000 for ND, ×21/1000 for SB). Decimals kept exactly
# as Sayed's spreadsheet so the reporting-rate tiles match his figures.
# Without these the Reporting Rate + Per-district tiles render blank.
DEMO_DENOMINATORS = {
    'Bandarban':    {'md': 10.336,   'nd': 152.0,   'sb': 190.0},
    'Barguna':      {'md': 28.0,     'nd': 229.0,   'sb': 166.0},
    'Chandpur':     {'md': 68.19312, 'nd': 1002.84, 'sb': 1253.55},
    'Gaibandha':    {'md': 62.0,     'nd': 1000.0,  'sb': 1270.0},
    'Khagrachari':  {'md': 18.768,   'nd': 276.0,   'sb': 345.0},
    'Noakhali':     {'md': 86.0,     'nd': 1269.0,  'sb': 1586.0},
    'Patuakahli':   {'md': 73.0,     'nd': 1081.0,  'sb': 1351.0},
}


class Command(BaseCommand):
    help = 'Seed demo MPDSR rows for the CIPRB dashboard visualisations (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--purge', action='store_true',
                            help='Delete demo rows instead of seeding.')

    def handle(self, *args, **opts):
        if opts['purge']:
            n, _ = MPDSRCase.objects.filter(case_hash__startswith='DEMO-').delete()
            ap, _ = MPDSRActionPlanSummary.objects.filter(source='demo_response_plan').delete()
            self.stdout.write(self.style.WARNING(
                f'Purged {n} demo MPDSR rows, {ap} demo response plans.'
            ))
            # Denominators + facility counts are idempotent upserts keyed by
            # district; leave them (they carry no DEMO- prefix and are the
            # canonical Project Deaths 2026 figures).
            return

        rng = random.Random(20260602)
        today = timezone.now().date()
        created = 0
        skipped = 0

        # ── Denominators (Project Deaths 2026) — upsert per district ──
        denom_n = 0
        for district, d in DEMO_DENOMINATORS.items():
            _, was_new = MPDSRDistrictDenominator.objects.update_or_create(
                district=district,
                defaults={
                    'project_deaths_md': d['md'],
                    'project_deaths_nd': d['nd'],
                    'project_deaths_sb': d['sb'],
                },
            )
            if was_new:
                denom_n += 1
        self.stdout.write(self.style.SUCCESS(
            f'Denominators upserted ({len(DEMO_DENOMINATORS)} districts, {denom_n} new).'
        ))

        # ── Facility notification/review counts (FDN/FDR) — feeds the
        #    facility-totals fallback in the Notify-vs-Review bar. ──
        fac_n = 0
        for district, prof in DEMO_PROFILE.items():
            md = prof['md']
            nd = prof['pd'] * 3  # neonatal facility notifications scale higher
            _, was_new = MPDSRFacilityCount.objects.update_or_create(
                district=district,
                facility_name=f'{district} District Hospital',
                period='2026',
                defaults={
                    # Community Death Notifications (CDN) — community level
                    'cdn_md': int(md * 0.6), 'cdn_nd': int(nd * 0.55),
                    'cdn_sb': int(nd * 0.7),
                    # Facility Death Notifications (FDN) — facility level
                    'fdn_md': md, 'fdn_nd': nd, 'fdn_sb': int(nd * 1.2),
                    # Facility Death Reviews (FDR)
                    'fdr_md': int(md * 0.35), 'fdr_nd': int(nd * 0.9),
                    'fdr_sb': int(nd * 0.5),
                },
            )
            if was_new:
                fac_n += 1
        self.stdout.write(self.style.SUCCESS(
            f'Facility counts upserted ({len(DEMO_PROFILE)} districts, {fac_n} new).'
        ))

        # ── Response Plan action matrix (Animesh's accountability tool) ──
        # Each district meeting carries a full per-action list with the 7
        # spec fields. Statuses + timelines are mixed so the deadline-based
        # green/red colouring has something to show.
        ACTION_TEMPLATES = [
            ('MPDSR System Strengthening', 'Refresher training for FWAs and HAs', 'UH&FPO',
             'implemented', -20, '% staff trained', 'All FWAs trained'),
            ('MPDSR System Strengthening', 'Ensure death notification within 24h', 'RMO',
             'implemented', -10, 'Notification timeliness', '90% within 24h'),
            ('Community Verbal Autopsy', 'Strengthen community SBCC on danger signs', 'HI',
             'in_progress', 8, 'Sessions conducted', '12 sessions/quarter'),
            ('Community Verbal Autopsy', 'Engage union council on transport fund', 'UH&FPO',
             'pending', -5, 'Transport fund active', 'Fund operational'),
            ('Facility Death Review', 'Review and update facility SOPs', 'RMO',
             'delayed', -15, 'SOPs updated', 'All SOPs current'),
            ('Facility Death Review', 'Establish blood transfusion readiness', 'CS',
             'implemented', -3, 'Blood available 24/7', 'Zero stock-outs'),
        ]
        ap_n = 0
        # Use first 4 districts for response-plan meetings
        rp_districts = list(DEMO_PROFILE.keys())[:4]
        for di, district in enumerate(rp_districts):
            actions = []
            n_actions = 4 + (di % 3)  # 4–6 actions per meeting
            implemented = 0
            for ai in range(n_actions):
                sec, act, resp, status, days, indicator, milestone = ACTION_TEMPLATES[ai % len(ACTION_TEMPLATES)]
                timeline = (today + datetime.timedelta(days=days)).isoformat()
                actions.append({
                    'section': sec,
                    'action': act,
                    'responsible': resp,
                    'timeline': timeline,
                    'indicator': indicator,
                    'milestone': milestone,
                    'considerations': 'Demo seed',
                    'status': status,
                })
                if status == 'implemented':
                    implemented += 1
            _, was_new = MPDSRActionPlanSummary.objects.update_or_create(
                district=district,
                level='DM',
                meeting_date=(today - datetime.timedelta(days=30 + di)).isoformat(),
                defaults={
                    'place_of_meeting': f'{district} Civil Surgeon Office',
                    'participants': 12 + di,
                    'meetings_planned': 1,
                    'activities_planned': n_actions,
                    'activities_implemented': implemented,
                    'actions': actions,
                    'source': 'demo_response_plan',
                },
            )
            if was_new:
                ap_n += 1
        self.stdout.write(self.style.SUCCESS(
            f'Response plan meetings upserted ({len(rp_districts)} districts, {ap_n} new).'
        ))

        for district, prof in DEMO_PROFILE.items():
            for i in range(prof['md']):
                # Deterministic per-(district,i) values so re-runs are stable
                # regardless of whether the MD row already exists. This lets a
                # plain re-seed BACKFILL the va_md/sa_md/f4 review rows onto a
                # database that was seeded before they existed (e.g. Railway).
                irng = random.Random(f'{district}-{i}')
                dod = today - datetime.timedelta(
                    days=irng.randint(0, 11) if irng.random() < 0.7 else irng.randint(12, 165)
                )
                notify_sub = 'f2' if irng.random() < 0.6 else 'f1'
                cause = irng.choice(CAUSES)
                place = irng.choice(PLACES)
                want_va = irng.random() < 0.75   # Community Verbal Autopsy
                want_sa = irng.random() < 0.65   # Social Autopsy
                want_f4 = notify_sub == 'f2' and irng.random() < 0.70  # Facility review

                # ── Notification row (f1/f2) — create if missing ──
                _, md_new = MPDSRCase.objects.get_or_create(
                    case_hash=f'DEMO-MD-{district}-{i}',
                    defaults=dict(
                        partner='CIPRB', district=district, sub_form_type=notify_sub,
                        date_of_death=dod, death_type=DeathType.MATERNAL,
                        cause_of_death=cause, place_of_death=place,
                        facility_name=f'{district} UHC', age_years=irng.randint(18, 42),
                        status=ReviewStatus.REPORTED, source='demo_seed',
                        audit_trail=[{
                            'timestamp': timezone.now().isoformat(),
                            'user': 'demo_seeder', 'action': 'Seeded demo MPDSR case',
                        }],
                    ),
                )
                created += 1 if md_new else 0
                skipped += 0 if md_new else 1

                # ── Review rows — INDEPENDENT upserts (Animesh's CDN/FDR/SA) ──
                reviews = []
                if want_va: reviews.append(('VAMD', 'va_md', f'{district} community'))
                if want_sa: reviews.append(('SAMD', 'sa_md', f'{district} community'))
                if want_f4: reviews.append(('F4',   'f4',    f'{district} UHC'))
                # Facility (Form 04) deep-dive needs an admission date (to
                # derive the admission→death interval), a spread of review-
                # committee statuses, and action plans on the cases that have
                # progressed. Cycle deterministically so the visuals are
                # stable across reseeds.
                _F4_STATUSES = [
                    ReviewStatus.REPORTED, ReviewStatus.UNDER_REVIEW,
                    ReviewStatus.COMMITTEE_REVIEW, ReviewStatus.ACTION_PLAN_DRAFTED,
                    ReviewStatus.CLOSED,
                ]
                for prefix, sub, fac in reviews:
                    extra = {}
                    if sub == 'f4':
                        f4_status = _F4_STATUSES[i % len(_F4_STATUSES)]
                        extra = dict(
                            status=f4_status,
                            admission_date=dod - datetime.timedelta(
                                days=irng.choice([0, 0, 1, 1, 2, 4, 6, 9, 12])),
                            action_plan=(
                                f'Facility action plan: strengthen referral & '
                                f'blood availability ({district} UHC).'
                                if f4_status in (ReviewStatus.ACTION_PLAN_DRAFTED,
                                                 ReviewStatus.CLOSED)
                                else ''
                            ),
                        )
                    _, r_new = MPDSRCase.objects.get_or_create(
                        case_hash=f'DEMO-{prefix}-{district}-{i}',
                        defaults=dict(
                            partner='CIPRB', district=district, sub_form_type=sub,
                            date_of_death=dod, death_type=DeathType.MATERNAL,
                            cause_of_death=cause, place_of_death=place,
                            facility_name=fac, status=ReviewStatus.UNDER_REVIEW,
                            source='demo_seed', **extra,
                        ),
                    )
                    created += 1 if r_new else 0

            for i in range(prof['pd']):
                case_hash = f'DEMO-PD-{district}-{i}'
                if MPDSRCase.objects.filter(case_hash=case_hash).exists():
                    skipped += 1
                    continue
                dod = today - datetime.timedelta(
                    days=rng.randint(0, 11) if rng.random() < 0.7 else rng.randint(12, 165)
                )
                MPDSRCase.objects.create(
                    case_hash=case_hash,
                    partner='CIPRB',
                    district=district,
                    sub_form_type='f3',
                    date_of_death=dod,
                    death_type=DeathType.PERINATAL,
                    cause_of_death='Birth Asphyxia' if i % 2 == 0 else 'Prematurity',
                    place_of_death=rng.choice(PLACES),
                    facility_name=f'{district} UHC',
                    status=ReviewStatus.REPORTED,
                    audit_trail=[{
                        'timestamp': timezone.now().isoformat(),
                        'user': 'demo_seeder',
                        'action': 'Seeded demo MPDSR case',
                    }],
                    source='demo_seed',
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Demo MPDSR seed complete: {created} created, {skipped} skipped (idempotent).'
        ))
