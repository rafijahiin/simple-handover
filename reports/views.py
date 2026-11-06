import calendar
from datetime import date, timedelta

from django.core.files.base import ContentFile
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import IsSupervisorOrManager
from submissions.models import FormType
from .anomaly import submission_anomalies_for_partner
from .ai_narrative import generate_narrative, generate_newsletter_narrative
from .models import Report, ReportFormat, ReportType, PeriodType, NarrativeSource
from .serializers import GenerateReportSerializer, ReportSerializer
from .generators.data import collect_programme_data


def _compute_period(
    period_type: str,
    year: int | None,
    month: int | None,
    period_start: date | None,
    period_end: date | None,
) -> tuple[date, date]:
    """Compute (period_start, period_end) from the submitted parameters."""
    today = timezone.now().date()

    if period_type == PeriodType.BIWEEKLY:
        ps = period_start or (today - timedelta(days=14))
        pe = period_end   or today
        return ps, pe

    if period_type == PeriodType.QUARTERLY:
        # Anchor to end of the given month; start is 3 calendar months before
        y = year  or today.year
        m = month or today.month
        pe = date(y, m, calendar.monthrange(y, m)[1])
        # Go back 3 months
        sm = m - 3
        sy = y
        if sm <= 0:
            sm += 12
            sy -= 1
        ps = date(sy, sm, 1)
        return ps, pe

    # Default: monthly
    y = year  or today.year
    m = month or today.month
    ps = date(y, m, 1)
    pe = date(y, m, calendar.monthrange(y, m)[1])
    return ps, pe


def _period_label(period_type: str, ps: date, pe: date) -> str:
    labels = {
        PeriodType.BIWEEKLY:  f'{ps.day} {ps.strftime("%b")} – {pe.day} {pe.strftime("%b %Y")}',
        PeriodType.QUARTERLY: f'{ps.strftime("%b")} – {pe.strftime("%b %Y")}',
        PeriodType.MONTHLY:   ps.strftime('%B %Y'),
    }
    return labels.get(period_type, f'{ps} – {pe}')


def _generate_file(
    report_type: str,
    fmt: str,
    data: dict,
    narrative: str,
    title: str,
    narrative_source: str = 'template',
) -> tuple[bytes, str]:
    """Dispatch to the correct generator and return (bytes, content_type)."""

    if fmt == ReportFormat.PDF:
        if report_type == ReportType.ONE_PAGER:
            from .generators.one_pager import build_infographic
            return build_infographic(data, narrative, narrative_source=narrative_source), 'application/pdf'

        if report_type == ReportType.NEWSLETTER:
            from .generators.newsletter import build_newsletter
            return build_newsletter(data=data, narrative=narrative, narrative_source=narrative_source), 'application/pdf'

        # monthly_summary
        from .generators.pdf import build_summary_pdf
        rows = [(k['label'], k['value']) for k in data.get('top_kpis', [])]
        return build_summary_pdf(title, rows, narrative), 'application/pdf'

    if fmt == ReportFormat.DOCX:
        from .generators.word import build_summary_docx
        rows = [(k['label'], k['value']) for k in data.get('top_kpis', [])]
        return (
            build_summary_docx(title, rows, narrative),
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

    if fmt == ReportFormat.PPTX:
        from .generators.pptx import build_presentation
        return (
            build_presentation(data, narrative, narrative_source=narrative_source),
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        )

    raise ValueError(f'Unknown format: {fmt}')


def _generate_file_v2(report_type, fmt, content, paras, ai_summary, meta_line):
    """Dispatch into the 2026-08 report family (content.py envelope).

    The newsletter keeps its own legacy generator (a genuinely different,
    email-styled format), so it never reaches this function."""
    if report_type == ReportType.ONE_PAGER:
        from .generators.poster import build_poster_html, render_poster_png
        if fmt == ReportFormat.PDF:
            from .generators.html_render import html_to_pdf
            return (html_to_pdf(build_poster_html(content),
                                width='285.8mm', height='357.2mm'),
                    'application/pdf')
        return render_poster_png(content), 'image/png'
    if fmt == ReportFormat.PPTX:
        from .generators.deck import build_native_deck
        return (build_native_deck(content, paras, meta_line),
                'application/vnd.openxmlformats-officedocument.presentationml.presentation')
    if fmt == ReportFormat.DOCX:
        from .generators.word import build_summary_docx
        rows = [(k['en'], k['value']) for k in content.get('kpis', [])]
        return (build_summary_docx(content['org_label'], rows, chr(10).join(paras)),
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    from .generators.doc_report import render_document_pdf
    return (render_document_pdf(content, paras, ai_summary, meta_line),
            'application/pdf')


class ReportViewSet(ModelViewSet):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    permission_classes = [IsSupervisorOrManager]
    http_method_names = ['get', 'head', 'options', 'post', 'delete']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.can_see_all_orgs:
            qs = qs.filter(partner=user.organisation)
        return qs

    @action(detail=False, methods=['post'])
    def generate(self, request):
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        partner      = d.get('partner', '')
        period_type  = d.get('period_type', PeriodType.MONTHLY)
        fmt          = d['format']
        report_type  = d['report_type']

        # Restrict partner for non-super-admins
        if not request.user.can_see_all_orgs:
            partner = request.user.organisation

        ps, pe = _compute_period(
            period_type,
            d.get('year'),
            d.get('month'),
            d.get('period_start'),
            d.get('period_end'),
        )

        period_lbl = _period_label(period_type, ps, pe)
        title = (
            f'{ReportType(report_type).label} — '
            f'{partner or "All Partners"} · {period_lbl}'
        )

        narrative = ''
        narrative_meta: dict = {'source': NarrativeSource.AI_DISABLED, 'model': ''}

        if report_type == ReportType.NEWSLETTER:
            # The newsletter keeps its legacy email-styled generator.
            prog_data = collect_programme_data(ps, pe, partner)
            prog_data['organisation'] = partner or 'All Partners'
            prog_data['period_label'] = period_lbl
            if d.get('include_narrative', True):
                ai_context = {
                    'organisation':     prog_data['organisation'],
                    'period':           period_lbl,
                    'total_activities': prog_data['total_submissions'],
                    **prog_data['counts'],
                    'fistula_cases':    prog_data['fistula_cases'],
                    'mpdsr_cases':      prog_data['mpdsr_cases'],
                }
                narrative, narrative_meta = generate_newsletter_narrative(ai_context)
            file_bytes, content_type = _generate_file(
                report_type, fmt, prog_data, narrative, title,
                narrative_source=narrative_meta.get('source', NarrativeSource.TEMPLATE),
            )
        else:
            from .generators.content import collect_content
            from .generators.monthly import (_ai_context, _lead_sentences,
                                             _split_paras)
            content = collect_content(partner, ps, pe)
            content['period_label'] = period_lbl
            if d.get('include_narrative', True):
                narrative, narrative_meta = generate_narrative(
                    _ai_context(content, period_lbl))
            paras = _split_paras(narrative)
            src = narrative_meta.get('source', '')
            drafted = ('Narrative drafted by AI' if src == NarrativeSource.AI
                       else 'Narrative from template')
            meta_line = (f'{drafted}, figures from approved submissions only · '
                         f'Generated {date.today():%d %b %Y}')
            file_bytes, content_type = _generate_file_v2(
                report_type, fmt, content, paras,
                _lead_sentences(narrative, 2), meta_line)

        ext      = {'pdf': 'pdf', 'docx': 'docx', 'pptx': 'pptx'}[fmt]
        filename = (
            f'{report_type}_{partner or "all"}_{period_type}'
            f'_{ps.strftime("%Y%m%d")}_{pe.strftime("%Y%m%d")}.{ext}'
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
            generated_by     = request.user,
            file_bytes       = file_bytes,        # durable copy in Postgres
            original_filename = filename,
        )
        report.file.save(filename, ContentFile(file_bytes), save=True)

        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)

    _CONTENT_TYPES = {
        'pdf':  'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'png':  'image/png',
        'html': 'text/html; charset=utf-8',
    }

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        report = self.get_object()
        ctype = self._CONTENT_TYPES.get(report.format, 'application/octet-stream')
        fname = (report.original_filename
                 or (report.file.name.split('/')[-1] if report.file else f'report-{report.id}.{report.format}'))
        # Durable path — serve the bytes persisted in Postgres (survive redeploys).
        if report.file_bytes:
            resp = HttpResponse(bytes(report.file_bytes), content_type=ctype)
            resp['Content-Disposition'] = f'attachment; filename="{fname}"'
            return resp
        # Legacy fallback — a file on disk (may be gone after a Railway redeploy).
        if report.file:
            try:
                return FileResponse(report.file.open('rb'), as_attachment=True, filename=fname)
            except (FileNotFoundError, OSError):
                pass
        return Response({'detail': 'This report file is no longer available — regenerate it.'},
                        status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def hub(self, request):
        """All monthly hub pieces (newest first) — the per-month × per-scope grid.

        Opening the hub as a super-admin also auto-generates the previous month's
        set if it is missing — a built-in monthly cron needing no Railway service.
        """
        if getattr(request.user, 'can_see_all_orgs', False):
            _kickoff_monthly_catchup()
        qs = (self.get_queryset()
              .filter(period_type=PeriodType.MONTHLY)
              .order_by('-period_start', 'partner', 'report_type', 'format'))
        return Response(ReportSerializer(qs, many=True, context={'request': request}).data)

    @action(detail=False, methods=['post'], url_path='generate-monthly')
    def generate_monthly(self, request):
        """Generate the 10-piece monthly set in a background thread (super-admin only).

        Rendering Chromium synchronously would block the gunicorn worker for ~a
        minute, so we detach it; the hub polls for the new pieces. The unattended
        monthly cron (generate_monthly_hub) is the primary path.
        """
        if not request.user.can_see_all_orgs:
            return Response({'detail': 'Only super-admins can generate the monthly hub set.'},
                            status=status.HTTP_403_FORBIDDEN)
        today = timezone.now().date()
        try:
            year  = int(request.data.get('year')  or today.year)
            month = int(request.data.get('month') or today.month)
        except (ValueError, TypeError):
            return Response({'detail': 'Invalid year/month.'}, status=status.HTTP_400_BAD_REQUEST)
        regenerate = bool(request.data.get('regenerate'))
        user_id = request.user.id

        import threading

        def _run():
            from django.contrib.auth import get_user_model
            from django.db import connection
            from .generators.monthly import generate_monthly_set
            try:
                u = get_user_model().objects.filter(id=user_id).first()
                generate_monthly_set(year, month, system_user=u, regenerate=regenerate)
            except Exception:                                       # noqa: BLE001
                import logging
                logging.getLogger(__name__).exception('async monthly hub generation failed')
            finally:
                connection.close()

        threading.Thread(target=_run, daemon=True).start()
        return Response(
            {'detail': f'Generating the {year}-{month:02d} report set in the background — '
                       'refresh in a minute to see the pieces.'},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=['get'], url_path='demo')
    def demo(self, request):
        """
        Generate and immediately download a demo report using static CPE 2022–2026 data.

        Query params:
            type: infographic | newsletter | presentation  (default: infographic)

        The demo data is sourced from reports/demo_data.py and flows through the
        identical generator pipeline as live approved submissions.
        """
        report_type = request.query_params.get('type', 'infographic')

        from .demo_data import get_demo_data, DEMO_NARRATIVE
        data = get_demo_data()

        if report_type == 'infographic':
            from .generators.one_pager import build_infographic
            file_bytes   = build_infographic(data, DEMO_NARRATIVE, narrative_source='hand_written_demo')
            content_type = 'application/pdf'
            filename     = 'demo_infographic_cpe2024.pdf'

        elif report_type == 'newsletter':
            from .generators.newsletter import build_newsletter
            file_bytes   = build_newsletter(data=data, narrative=DEMO_NARRATIVE, narrative_source='hand_written_demo')
            content_type = 'application/pdf'
            filename     = 'demo_newsletter_cpe2024.pdf'

        elif report_type == 'presentation':
            from .generators.pptx import build_presentation
            file_bytes   = build_presentation(data, DEMO_NARRATIVE, narrative_source='hand_written_demo')
            content_type = (
                'application/vnd.openxmlformats-officedocument'
                '.presentationml.presentation'
            )
            filename = 'demo_presentation_cpe2024.pptx'

        else:
            return Response(
                {'detail': (
                    f'Unknown type {report_type!r}. '
                    'Use infographic, newsletter, or presentation.'
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = HttpResponse(file_bytes, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=False, methods=['get'])
    def anomalies(self, request):
        partner   = request.query_params.get('partner', '')
        form_type = request.query_params.get('form_type', FormType.MPDSR)
        try:
            year = int(request.query_params.get('year', timezone.now().year))
        except (ValueError, TypeError):
            year = timezone.now().year

        results = submission_anomalies_for_partner(partner, form_type, year)
        return Response({'year': year, 'partner': partner,
                         'form_type': form_type, 'anomalies': results})


def _kickoff_monthly_catchup():
    """Built-in monthly cron: the first super-admin hub view past month-start
    auto-generates the PREVIOUS month's set if it's missing — so the system
    needs no separate Railway cron service. Gated (≤ once / 6h) and idempotent
    (a present set short-circuits), so it is cheap to call on every hub poll,
    and fully wrapped so it can never break the hub response."""
    try:
        from django.core.cache import cache
        if cache.get('hub_monthly_autocheck'):
            return
        cache.set('hub_monthly_autocheck', 1, 6 * 3600)

        today = timezone.now().date()
        y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        if Report.objects.filter(report_type=ReportType.WEB_REPORT,
                                 period_type=PeriodType.MONTHLY, year=y, month=m).exists():
            return

        import threading

        def _run():
            from django.db import connection
            from .generators.monthly import generate_monthly_set
            try:
                generate_monthly_set(y, m)
            except Exception:                                       # noqa: BLE001
                import logging
                logging.getLogger(__name__).exception('auto monthly hub catch-up failed')
            finally:
                connection.close()

        threading.Thread(target=_run, daemon=True).start()
    except Exception:                                               # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception('monthly catch-up kickoff failed')


def web_report_by_token(request, token):
    """Public shareable web report — serve the stored HTML by its share token.

    Unauthenticated by design: the long random token IS the access control
    (emailed to UNFPA, opens without login, not guessable or listed).
    """
    from django.http import Http404, HttpResponse
    from .models import Report, ReportType
    rep = (Report.objects
           .filter(report_type=ReportType.WEB_REPORT, share_token=token)
           .first())
    if not rep or not rep.file_bytes:
        raise Http404('Report not found')
    return HttpResponse(bytes(rep.file_bytes), content_type='text/html; charset=utf-8')
