"""Full clean-slate wipe of all PRACTICE / demo / Excel submission + case data.

Rafi's 2026-06-28 directive: every submission in the system so far is practice
data (form testing/training). Wipe it ALL so the dashboards start from zero and
populate only from real field data going forward.

DELETES (all rows):
  - submissions.KoboSubmission
  - every programs submission model (Client, ClinicVisit, HIV/STI, GBV, Referral,
    Outreach, Training, NilReport, …) — anything carrying approval_status
  - mpdsr: MPDSRCase, MaternalNearMissCase, MPDSRDeathNotification, MPDSRAction,
    MPDSRActionPlanSummary, MPDSRFacilityCount, MPDSRDistrictDenominator (Excel)
  - fistula: CIPRBFistulaCase, FistulaCornerCase, FistulaCampaign, FistulaCampaignVisit
  - baseline: BaselineResponse, BaselineSurvey
  - tracker.Alert (generated)
  - demo ServiceCenters (code PHD-* / BANDHU-* from seed_demo)

KEEPS (configuration — NOT submission data):
  - accounts.User, partners.Partner
  - programs.ServiceCenter (the real wellness-centre registry; only demo-prefixed
    rows are removed)
  - indicators.IndicatorTarget + KoboFormMapping, tracker.MonthlyTarget

Dry-run by default (prints counts). Pass --confirm to actually delete. The delete
runs inside one transaction, so an unexpected protected-FK error rolls back the
whole thing rather than leaving a half-wiped DB.
"""
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q


class Command(BaseCommand):
    help = 'Wipe ALL practice/demo/Excel submission + case data (full clean slate).'

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Actually delete. Without this it is a dry run.')

    # Configuration models that must SURVIVE the wipe (never submission data).
    CONFIG_KEEP = {
        'accounts.User', 'partners.Partner',
        'indicators.IndicatorTarget', 'indicators.KoboFormMapping',
        'tracker.MonthlyTarget',
        'programs.ServiceCenter',  # real registry kept; demo rows handled separately
    }

    def _ordered_targets(self):
        """(label, queryset) pairs in FK-safe delete order. Every model carrying
        approval_status across ALL apps is practice/submission data — programs,
        pharmacy prescriptions, mpdsr/fistula cases, training, etc. Plus the data
        models that lack approval_status (aggregates, visits, baseline, alerts).
        Config (users, real centres, targets, form mappings) is preserved.
        Order: leaf submission/case rows first; the PROTECT parents (Client, then
        demo ServiceCenters) last; the whole run is wrapped in one transaction."""
        from programs.models import Client, ServiceCenter

        # 1. Every approval_status data model across ALL apps, EXCEPT Client
        #    (a PROTECT parent referenced by ClinicVisit/HIVSTITest/pharmacy/…).
        approval_models = [
            m for m in apps.get_models()
            if f'{m._meta.app_label}.{m.__name__}' not in self.CONFIG_KEEP
            and any(f.name == 'approval_status' for f in m._meta.get_fields())
        ]
        seen = set(approval_models)
        targets = []
        for m in approval_models:
            if m is Client:
                continue  # Client deleted late (step 4)
            targets.append((f'{m._meta.app_label}.{m.__name__}', m.objects.all()))

        # 2. Data models WITHOUT approval_status (aggregates / visits / baseline /
        #    alerts). Skip any already captured above.
        EXTRA = [
            ('mpdsr', 'MPDSRActionPlanSummary'), ('mpdsr', 'MPDSRFacilityCount'),
            ('mpdsr', 'MPDSRDistrictDenominator'), ('mpdsr', 'MPDSRDeathNotification'),
            ('fistula', 'FistulaCornerCase'), ('fistula', 'FistulaCampaign'),
            ('fistula', 'FistulaCampaignVisit'),
            ('baseline', 'BaselineResponse'), ('baseline', 'BaselineSurvey'),
            ('tracker', 'Alert'),
        ]
        for app_label, name in EXTRA:
            try:
                m = apps.get_model(app_label, name)
            except LookupError:
                continue
            if m in seen:
                continue
            seen.add(m)
            targets.append((f'{app_label}.{name}', m.objects.all()))

        # 3. Legacy KoboSubmission (case FKs to it are SET_NULL).
        from submissions.models import KoboSubmission
        targets.append(('submissions.KoboSubmission', KoboSubmission.objects.all()))

        # 4. Client — after every row that PROTECT-references it is gone.
        targets.append(('programs.Client', Client.objects.all()))

        # 5. demo ServiceCenters only (real registry kept), last of all.
        targets.append((
            'programs.ServiceCenter[demo PHD-/BANDHU-]',
            ServiceCenter.objects.filter(
                Q(code__startswith='PHD-') | Q(code__startswith='BANDHU-')),
        ))
        return targets

    def handle(self, *args, **opts):
        confirm = opts['confirm']
        targets = self._ordered_targets()

        self.stdout.write(self.style.MIGRATE_HEADING(
            'Practice-data flush — rows found:'))
        total = 0
        for label, qs in targets:
            c = qs.count()
            total += c
            self.stdout.write(f'  {label:46s} {c}')
        self.stdout.write(f'  {"TOTAL":46s} {total}')

        if not confirm:
            self.stdout.write(self.style.WARNING(
                'DRY RUN — nothing deleted. Re-run with --confirm to wipe.'))
            return

        with transaction.atomic():
            deleted_total = 0
            for label, qs in targets:
                n, _ = qs.delete()
                deleted_total += n
                self.stdout.write(self.style.SUCCESS(f'  deleted {label:40s} {n}'))
            self.stdout.write(self.style.SUCCESS(
                f'DONE — full clean slate. {deleted_total} rows removed.'))
