"""
Management command: python manage.py generate_scheduled_reports

Generates the bi-weekly programme reports for CIPRB/UNFPA, reusing the EXACT
generation path of reports.views.ReportViewSet.generate (collect_programme_data
-> AI narrative with safe fallback -> _generate_file -> Report.objects.create ->
report.file.save), but headless (no request.user).

For each partner in PARTNERS (['PHD', 'Bandhu', 'CIPRB', ''] where '' = ALL
partners / the overall project report) and each report_type in REPORT_TYPES, it
produces one report for the CURRENT bi-weekly period (period_start = today - 14d,
period_end = today) -> 4 scopes x 3 report types = 12 reports per run.

Each report_type is paired with the single best, crash-resistant FORMAT
(all PDF), because fmt == 'pdf' is the only branch in views._generate_file that
honours report_type and routes to the distinct designed builders:
    monthly_summary -> build_summary_pdf
    one_pager       -> build_infographic
    newsletter      -> build_newsletter
docx/pptx ignore report_type and collapse to the generic summary/deck, so they
are deliberately avoided here.

IDEMPOTENT: before generating, a report is SKIPPED if one already exists for the
same (partner, report_type, period_type, period_start, period_end) — so a re-run
on the same day, or a double-fired cron, never creates duplicates.

ROBUST: every one of the 9 generations is wrapped in its own try/except, so a
single failure (AI error, empty data, generator crash, DB hiccup) is logged and
the run CONTINUES with the rest. The command never aborts the batch on one bad
report. The AI narrative path is already fully defensive (20s timeout, blanket
try/except, deterministic fallback — see reports/ai_narrative.py) so it cannot
hang or raise; an absent GROQ_API_KEY simply degrades to a narrative-less but
otherwise complete report.

ZERO-DATA SAFETY: collect_programme_data always returns a fully-populated
all-zeros dict for a quiet period, and every generator guards its divisions, so
an empty period yields a valid near-empty report rather than a crash.

CRON CADENCE
------------
Railway native cron runs in UTC and cannot express "every 2 weeks", so the
practical bi-weekly schedule is the 1st and 15th of each month at 00:00 UTC,
which is 06:00 Asia/Dhaka (Bangladesh is a fixed UTC+6, no DST):

    0 0 1,15 * *

Run this on a SEPARATE Railway service (NOT the web/gunicorn service, which never
exits) whose start command is:

    python manage.py migrate --noinput && python manage.py generate_scheduled_reports

See the command's module docstring / project deploy notes for full setup.
"""
from __future__ import annotations

import logging
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from reports.ai_narrative import generate_narrative, generate_newsletter_narrative
from reports.generators.data import collect_programme_data
from reports.models import NarrativeSource, PeriodType, Report, ReportType
from reports.views import _compute_period, _generate_file, _period_label

logger = logging.getLogger(__name__)

# Partners to generate for. '' == ALL partners (the overall project report).
PARTNERS: list[str] = ['PHD', 'Bandhu', 'CIPRB', '']

# report_type -> best single crash-resistant format. PDF is the only format
# whose _generate_file branch honours report_type, and it is the least
# crash-prone (build_summary_pdf only touches top_kpis; infographic/newsletter
# use .get with defaults and guard every division).
REPORT_TYPE_FORMATS: dict[str, str] = {
    ReportType.MONTHLY_SUMMARY: 'pdf',  # -> build_summary_pdf
    ReportType.ONE_PAGER:       'pdf',  # -> build_infographic
    ReportType.NEWSLETTER:      'pdf',  # -> build_newsletter
}

# File extension per format (mirrors views.generate).
EXT_FOR_FORMAT: dict[str, str] = {'pdf': 'pdf', 'docx': 'docx', 'pptx': 'pptx'}


class Command(BaseCommand):
    help = (
        'Generate the bi-weekly programme reports (12 = 4 scopes x 3 types) '
        'for the current biweekly period, idempotently. Intended for Railway '
        'cron on the 1st and 15th of each month.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Compute and log what WOULD be generated, but create nothing.',
        )
        parser.add_argument(
            '--period-type',
            default=PeriodType.BIWEEKLY,
            choices=[c[0] for c in PeriodType.choices],
            help='Period type to generate for (default: biweekly).',
        )
        parser.add_argument(
            '--no-narrative',
            action='store_true',
            help=(
                'Skip the AI narrative entirely and render template-only reports '
                '(fully deterministic / offline-safe).'
            ),
        )

    # ── Entry point ──────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        dry = options['dry_run']
        period_type = options['period_type']
        include_narrative = not options['no_narrative']
        prefix = '[DRY RUN] ' if dry else ''

        ps, pe = _compute_period(period_type, None, None, None, None)
        period_lbl = _period_label(period_type, ps, pe)

        system_user = self._resolve_system_user()

        self.stdout.write(
            f'{prefix}Generating {len(PARTNERS) * len(REPORT_TYPE_FORMATS)} '
            f'report(s) for period {period_lbl} '
            f'({ps:%Y-%m-%d} -> {pe:%Y-%m-%d}), period_type={period_type}.'
        )
        if include_narrative and not getattr(settings, 'GROQ_API_KEY', ''):
            self.stdout.write(self.style.WARNING(
                '  GROQ_API_KEY is not set — reports will render without an AI '
                'narrative (this is handled gracefully, not an error).'
            ))

        created = skipped = failed = 0

        for partner in PARTNERS:
            for report_type, fmt in REPORT_TYPE_FORMATS.items():
                outcome = self._handle_one(
                    partner=partner,
                    report_type=report_type,
                    fmt=fmt,
                    period_type=period_type,
                    ps=ps,
                    pe=pe,
                    period_lbl=period_lbl,
                    include_narrative=include_narrative,
                    system_user=system_user,
                    dry=dry,
                )
                if outcome == 'created':
                    created += 1
                elif outcome == 'skipped':
                    skipped += 1
                else:
                    failed += 1

        summary = f'{prefix}Done: {created} created, {skipped} skipped, {failed} failed.'
        style = self.style.SUCCESS if failed == 0 else self.style.WARNING
        self.stdout.write(style(summary))
        logger.info(
            'generate_scheduled_reports complete',
            extra={'created': created, 'skipped': skipped, 'failed': failed,
                   'dry_run': dry, 'period_type': period_type},
        )

    # ── Per-report worker (one of the 9) ─────────────────────────────────────
    def _handle_one(
        self,
        *,
        partner: str,
        report_type: str,
        fmt: str,
        period_type: str,
        ps: date,
        pe: date,
        period_lbl: str,
        include_narrative: bool,
        system_user,
        dry: bool,
    ) -> str:
        """Generate a single report. Returns 'created' | 'skipped' | 'failed'.

        Never raises — any exception is logged and reported as 'failed' so the
        rest of the batch continues.
        """
        label = f'{report_type}/{fmt} · {partner or "all"}'
        try:
            # Idempotency guard — skip if this (partner, type, period) already exists.
            if Report.objects.filter(
                report_type=report_type,
                partner=partner,
                period_type=period_type,
                period_start=ps,
                period_end=pe,
            ).exists():
                self.stdout.write(f'  SKIP  {label} (already exists for this period)')
                return 'skipped'

            if dry:
                self.stdout.write(f'  PLAN  {label} (would generate)')
                return 'created'  # counted as "would create" in the dry-run summary

            # Build the title exactly as the viewset does.
            title = (
                f'{ReportType(report_type).label} — '
                f'{partner or "All Partners"} · {period_lbl}'
            )

            # Collect data, then replicate the viewset's two augmentations.
            prog_data = collect_programme_data(ps, pe, partner)
            prog_data['organisation'] = partner or 'All Partners'
            prog_data['period_label'] = period_lbl

            narrative, narrative_meta = self._build_narrative(
                report_type=report_type,
                prog_data=prog_data,
                period_lbl=period_lbl,
                include_narrative=include_narrative,
            )

            file_bytes, _content_type = _generate_file(
                report_type, fmt, prog_data, narrative, title,
                narrative_source=narrative_meta.get('source', NarrativeSource.TEMPLATE),
            )

            ext = EXT_FOR_FORMAT[fmt]
            filename = (
                f'{report_type}_{partner or "all"}_{period_type}'
                f'_{ps:%Y%m%d}_{pe:%Y%m%d}.{ext}'
            )

            report = Report.objects.create(
                report_type      = report_type,
                format           = fmt,
                partner          = partner,
                year             = ps.year,
                month            = ps.month,
                period_type      = period_type,
                period_start     = ps,
                period_end       = pe,
                title            = title,
                narrative        = narrative or '',
                narrative_source = narrative_meta.get('source', NarrativeSource.TEMPLATE),
                model_used       = narrative_meta.get('model', ''),
                generated_by     = system_user,
                file_bytes       = file_bytes,     # durable copy in Postgres
                original_filename = filename,
            )
            # Durable bytes are already in Postgres (file_bytes above) and the
            # download endpoint serves those, so the on-disk copy is best-effort:
            # a flaky/ephemeral filesystem write must never fail a complete report.
            try:
                report.file.save(filename, ContentFile(file_bytes), save=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning('disk file.save failed for %s (bytes safe in DB): %s', label, exc)

            self.stdout.write(self.style.SUCCESS(
                f'  OK    {label} -> {filename} '
                f'[{narrative_meta.get("source", NarrativeSource.TEMPLATE)}]'
            ))
            return 'created'

        except Exception as exc:  # noqa: BLE001 — batch must survive any one failure
            logger.exception('scheduled report generation failed for %s', label)
            self.stdout.write(self.style.ERROR(f'  FAIL  {label}: {type(exc).__name__}: {exc}'))
            # If the DB connection dropped, reset it so the NEXT report reconnects
            # instead of cascading the same closed-connection failure across the batch.
            try:
                from django.db import connection
                connection.close()
            except Exception:  # noqa: BLE001
                pass
            return 'failed'

    # ── Narrative (mirrors views.generate, with offline opt-out) ─────────────
    def _build_narrative(
        self,
        *,
        report_type: str,
        prog_data: dict,
        period_lbl: str,
        include_narrative: bool,
    ) -> tuple[str, dict]:
        """Return (narrative_text, meta). Never raises; AI path is self-isolating."""
        if not include_narrative:
            return '', {'source': NarrativeSource.AI_DISABLED, 'model': ''}

        ai_context = {
            'organisation':     prog_data['organisation'],
            'period':           period_lbl,
            'total_activities': prog_data['total_submissions'],
            **prog_data['counts'],
            'fistula_cases':    prog_data['fistula_cases'],
            'mpdsr_cases':      prog_data['mpdsr_cases'],
        }
        if report_type == ReportType.NEWSLETTER:
            return generate_newsletter_narrative(ai_context)
        return generate_narrative(ai_context)

    # ── System user lookup (generated_by is nullable → None is fine) ─────────
    def _resolve_system_user(self):
        """Look up a developer/superuser to attribute reports to, else None.

        Report.generated_by is null=True / on_delete=SET_NULL, so None is a
        perfectly valid value for an unattended job.
        """
        User = get_user_model()
        try:
            user = (
                User.objects.filter(role='developer').first()
                or User.objects.filter(is_superuser=True).first()
            )
        except Exception as exc:  # noqa: BLE001 — never block generation on this
            logger.debug('system user lookup failed: %s', exc)
            return None

        if user is not None:
            self.stdout.write(f'  Attributing reports to system user: {user}')
        else:
            self.stdout.write('  No developer/superuser found — generated_by will be NULL.')
        return user
