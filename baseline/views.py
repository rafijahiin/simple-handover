import csv
from collections import Counter

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ViewSet

from accounts.permissions import (
    IsSupervisorOrManager, CanViewBaseline, CanApproveBaseline, OrgFilterMixin,
)
from submissions.flatten import flatten_group_keys
from submissions.models import KoboSubmission, FormType, SubmissionStatus
from .duplicate_detector import flag_duplicates_for_partner
from .insights import compute_insights
from .monitoring import compute_monitoring
from .derive import derive_fields
from .models import BaselineSurvey, BaselineResponse, SurveyType
from .schema import headline, humanize, load_schema
from .serializers import BaselineSurveySerializer, BaselineResponseSerializer


# ── Legacy generic baseline (kept; old assumed maternal-health survey) ────────
class BaselineSurveyViewSet(OrgFilterMixin, ModelViewSet):
    queryset = BaselineSurvey.objects.select_related('submission').all()
    serializer_class = BaselineSurveySerializer
    permission_classes = [IsSupervisorOrManager]
    http_method_names = ['get', 'head', 'options', 'post']
    org_field = 'partner'

    def get_queryset(self):
        qs = super().get_queryset()
        survey_type = self.request.query_params.get('survey_type')
        if survey_type:
            qs = qs.filter(survey_type=survey_type)
        district = self.request.query_params.get('district')
        if district:
            qs = qs.filter(district__icontains=district)
        duplicates_only = self.request.query_params.get('duplicates_only')
        if duplicates_only == 'true':
            qs = qs.filter(is_duplicate=True)
        return qs

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        return Response({
            'total': qs.count(),
            'baseline': qs.filter(survey_type=SurveyType.BASELINE).count(),
            'endline': qs.filter(survey_type=SurveyType.ENDLINE).count(),
            'duplicates': qs.filter(is_duplicate=True).count(),
        })

    @action(detail=False, methods=['post'])
    def scan_duplicates(self, request):
        partner = request.user.organisation
        flagged = flag_duplicates_for_partner(partner)
        return Response({'flagged': flagged, 'partner': partner})


# ── D5 key-population baseline (Hijra / FSW) — CIPRB-conducted ────────────────

def _pending_baseline():
    """PENDING key-population baseline submissions awaiting CIPRB verification."""
    return KoboSubmission.objects.filter(
        form_type=FormType.BASELINE, status=SubmissionStatus.PENDING,
    )


class BaselineResponseViewSet(OrgFilterMixin, ModelViewSet):
    """Verified D5 baseline responses (read-only) — collection monitoring."""
    queryset = BaselineResponse.objects.select_related('submission').all()
    serializer_class = BaselineResponseSerializer
    permission_classes = [CanViewBaseline]
    http_method_names = ['get', 'head', 'options']
    org_field = 'partner'

    def get_queryset(self):
        qs = super().get_queryset()
        pop = self.request.query_params.get('population')
        if pop:
            qs = qs.filter(population=pop)
        district = self.request.query_params.get('district')
        if district:
            qs = qs.filter(district__icontains=district)
        if self.request.query_params.get('duplicates_only') == 'true':
            qs = qs.filter(is_duplicate=True)
        return qs

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        # Population and dedup key come from the FORM, not the stored columns:
        # older rows misfiled every FSW interview as hijra, and `is_duplicate` was
        # computed against questionnaire_serial — a field neither live form
        # collects — so the stored flag is False on every row ever ingested.
        pops = Counter()
        serials = Counter()
        total = 0
        # NB: no .only() here — the queryset uses select_related('submission'),
        # and deferring a select_related field raises FieldError (500).
        for r in qs:
            total += 1
            d = derive_fields(r.raw_data, fallback_district=r.district)
            pops[d['population'] or r.population] += 1
            key = (d['population'] or r.population, (d['serial'] or '').upper())
            if key[1]:
                serials[key] += 1
        # Count the EXTRA copies: 3 uploads of one interview = 2 duplicates.
        # Same rule as monitoring.py, so the two panels can't disagree.
        duplicates = sum(n - 1 for n in serials.values() if n > 1)
        return Response({
            'verified_total': total,
            'verified_hijra': pops.get('hijra', 0),
            'verified_fsw': pops.get('fsw', 0),
            'duplicates': duplicates,
            'pending': _pending_baseline().count(),
        })

    @action(detail=False, methods=['get'])
    def insights(self, request):
        """Chart-ready aggregation over VERIFIED responses for the /baseline
        analytics section. Honours ?population= / ?district= via get_queryset."""
        return Response(compute_insights(self.get_queryset()))

    @action(detail=False, methods=['get'])
    def srhr(self, request):
        """Major SRHR indicators (CIPRB's Dashbroad list) over verified
        responses, grouped by questionnaire module, per population."""
        from .srhr import compute_srhr
        return Response(compute_srhr(self.get_queryset()))

    @action(detail=False, methods=['get'])
    def monitoring(self, request):
        """Fieldwork + data-quality monitoring over ALL collected baseline
        submissions (pending + approved) — the collection command center. Reads
        the submissions directly (not just verified rows) because monitoring is
        about the collection itself: pace, per-site/enumerator throughput,
        interview duration/outcome, and the quality flags.

        Optional filters (?population= ?enumerator= ?site= ?version=
        ?date_from= ?date_to=) are applied inside compute_monitoring, where
        population and collector name are already resolved. These filters are
        for THIS monitoring surface only — they never touch the verified-
        interview queryset the SRHR/insights endpoints aggregate."""
        from submissions.models import KoboSubmission, FormType
        subs = KoboSubmission.objects.filter(form_type=FormType.BASELINE)
        p = request.query_params
        filters = {k: p.get(k, '').strip() for k in
                   ('population', 'enumerator', 'site', 'version',
                    'date_from', 'date_to')}
        filters = {k: v for k, v in filters.items() if v}
        if filters.get('population') not in (None, 'fsw', 'hijra'):
            filters.pop('population')
        return Response(compute_monitoring(subs, filters=filters))

    @action(detail=False, methods=['get'])
    def schema(self, request):
        """Field labels + choice maps for both instruments — lets the frontend
        render coded answers as real question/answer text. Static; cache it."""
        return Response(load_schema())

    @action(detail=False, methods=['get'])
    def export(self, request):
        qs = self.get_queryset()
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="baseline_responses.csv"'
        w = csv.writer(resp)
        w.writerow(['serial', 'population', 'survey_round', 'district', 'site_code',
                    'age', 'interview_outcome', 'is_duplicate', 'created_at'])
        for r in qs:
            # Derive from raw_data at READ time. Rows ingested before the flatten /
            # population fixes have wrong stored columns (every FSW interview filed
            # as 'hijra', blank district/age/outcome). Deriving here keeps the export
            # correct without a bulk UPDATE of production data. Stored value is used
            # only when the payload cannot answer.
            d = derive_fields(r.raw_data, fallback_district=r.district)
            w.writerow([d['serial'] or r.serial,
                        d['population'] or r.population,
                        d['survey_round'] or r.survey_round,
                        d['district'] or r.district,
                        d['site_code'] or r.site_code,
                        (d['age'] if d['age'] is not None else (r.age or '')),
                        d['interview_outcome'] or r.interview_outcome,
                        r.is_duplicate,
                        r.created_at.isoformat()])
        return resp


class BaselineVerificationViewSet(ViewSet):
    """CIPRB verification gate — list PENDING baseline interviews and
    approve/reject each one. Approving flips the KoboSubmission to APPROVED,
    which materialises the verified BaselineResponse (signal). This is the ONLY
    approval surface for baseline: KoboSubmissionViewSet.get_queryset excludes
    form_type=BASELINE, so baseline never appears in the generic Manager
    Approvals queue (any org tab) and cannot be approved via /submissions/."""

    def get_permissions(self):
        # Split read vs write: anyone in CIPRB/UNFPA (or developer) may VIEW the
        # queue; only the developer and the CIPRB manager (Tanjina) may
        # approve/reject. UNFPA + CIPRB org_lead are view-only here.
        if getattr(self, 'action', None) in ('approve', 'reject'):
            return [CanApproveBaseline()]
        return [CanViewBaseline()]

    def list(self, request):
        pending = list(_pending_baseline().order_by('-submitted_at')[:500])
        # Duplicate preview across ALL baseline submissions (serial+population),
        # so the reviewer sees a likely-duplicate before approving.
        counts = Counter()
        for raw in KoboSubmission.objects.filter(
                form_type=FormType.BASELINE).values_list('raw_data', flat=True):
            d = derive_fields(raw or {})
            ser = d['serial'].upper()
            if ser:
                counts[(d['population'] or '', ser)] += 1
        out = []
        for s in pending:
            # Kobo nests grouped answers as 'group/field' — flatten before reading
            # district / age / the Q&A card, or every one of them renders blank.
            raw = flatten_group_keys(s.raw_data or {})
            d = derive_fields(raw, fallback_district=s.district)
            pop = d['population'] or ''
            ser = d['serial']
            out.append({
                'submission_id': str(s.id),
                'population': pop,
                'serial': ser,
                'district': d['district'],
                'site_code': d['site_code'],
                'age': d['age'] if d['age'] is not None else '',
                'interviewer': s.worker_name,
                'submitted_at': s.submitted_at,
                'gps_missing': s.latitude is None,
                'answer_count': sum(1 for v in raw.values() if v not in ('', None, [])),
                'duplicate_preview': counts.get((pop, ser.upper()), 0) > 1,
                # Curated, readable summary + full grouped Q/A for the review card.
                'headline': headline(pop, raw),
                'answers': humanize(pop, raw),
            })
        return Response(out)

    def _review(self, request, pk, new_status, note_field):
        sub = _pending_baseline().filter(pk=pk).first()
        if not sub:
            return Response({'detail': 'Not found or already reviewed.'}, status=404)
        note = request.data.get(note_field, '') if hasattr(request, 'data') else ''
        sub.status = new_status
        sub.reviewed_by = request.user
        sub.reviewed_at = timezone.now()
        if new_status == SubmissionStatus.REJECTED:
            sub.rejection_reason = note
        if hasattr(sub, 'add_review_entry'):
            sub.add_review_entry(
                user=request.user,
                action='approved' if new_status == SubmissionStatus.APPROVED else 'rejected',
                note=note,
            )
        sub.save()  # post_save signal materialises BaselineResponse on APPROVED
        return Response({'detail': new_status, 'submission_id': str(sub.id)})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._review(request, pk, SubmissionStatus.APPROVED, 'note')

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._review(request, pk, SubmissionStatus.REJECTED, 'reason')


# ── FSW anomaly console (deterministic rule engine) ──────────────────────────
from rest_framework import status as http_status  # noqa: E402

from .anomaly import build_report  # noqa: E402
from .models import AnomalyReview  # noqa: E402

_REVIEW_STATUSES = {c[0] for c in AnomalyReview.STATUS_CHOICES}


class FswAnomalyViewSet(ViewSet):
    """Read-only FSW anomaly report from the deterministic engine, merged with
    the separate review-decision table. Never edits raw Kobo data."""

    def get_permissions(self):
        if getattr(self, 'action', None) == 'review':
            return [CanViewBaseline()]
        return [CanViewBaseline()]

    def list(self, request):
        """Engine report merged with review decisions, then filtered.

        Filters: ?population=all|fsw|hijra (default all), plus record-scoped
        ?enumerator= ?site= ?version= ?date_from= ?date_to=, and flag-scoped
        ?severity= ?rule= ?review_status= ?q= (search across rule / message /
        record id / enumerator). KPI definitions (deliberate, do not merge):
        critical/high/medium/low count FLAGS — one interview with five problems
        is five flags; interviews_affected counts UNIQUE interviews with >= 1
        flag; flags_reviewed counts FLAGS whose review status is not 'new'."""
        p = request.query_params
        population = p.get('population', 'all')
        if population not in ('all', 'fsw', 'hijra'):
            return Response({'detail': 'population must be all, fsw or hijra.'},
                            status=http_status.HTTP_400_BAD_REQUEST)
        pops = ('fsw', 'hijra') if population == 'all' else (population,)

        anomalies, records_index = [], []
        current_versions = {}
        for pop in pops:
            rep = build_report(pop)
            anomalies.extend(rep['anomalies'])
            records_index.extend(rep.get('records_index', []))
            current_versions[pop] = rep.get('current_version')

        # Merge review decisions before filtering, so review_status is filterable.
        reviews = {
            (r.submission_id, r.rule_id): r
            for r in AnomalyReview.objects.select_related('reviewed_by')
        }
        for anomaly in anomalies:
            review = reviews.get((anomaly.get('record_id'), anomaly['rule_id']))
            anomaly['review_status'] = review.status if review else 'new'
            anomaly['review_note'] = review.note if review else ''
            anomaly['reviewed_by'] = (
                review.reviewed_by.full_name
                if review and review.reviewed_by else None)
            anomaly['reviewed_at'] = (
                review.reviewed_at.isoformat()
                if review and review.reviewed_at else None)

        # Record-scoped filters narrow BOTH the scanned denominator and the flags.
        rec_filters = {k: p.get(k, '').strip() for k in
                       ('enumerator', 'site', 'version', 'date_from', 'date_to')}
        rec_filters = {k: v for k, v in rec_filters.items() if v}

        def rec_ok(r):
            if rec_filters.get('enumerator') and r['enumerator'] != rec_filters['enumerator']:
                return False
            if rec_filters.get('site') and r['site'] != rec_filters['site']:
                return False
            if rec_filters.get('version') and r['version'] != rec_filters['version']:
                return False
            if rec_filters.get('date_from') and (not r['date'] or r['date'] < rec_filters['date_from']):
                return False
            if rec_filters.get('date_to') and (not r['date'] or r['date'] > rec_filters['date_to']):
                return False
            return True

        records_index = [r for r in records_index if rec_ok(r)]
        kept_ids = {r['record_id'] for r in records_index}
        if rec_filters:
            # Dataset-level flags without a record id can't satisfy a record-
            # scoped filter — they drop out rather than leak through.
            anomalies = [a for a in anomalies if a.get('record_id') in kept_ids]

        # Flag-scoped filters.
        severity = p.get('severity', '').strip().lower()
        rule = p.get('rule', '').strip()
        review_status = p.get('review_status', '').strip()
        q = p.get('q', '').strip().lower()
        if severity:
            anomalies = [a for a in anomalies if a['severity'] == severity]
        if rule:
            anomalies = [a for a in anomalies if a['rule_id'] == rule]
        if review_status:
            anomalies = [a for a in anomalies if a['review_status'] == review_status]
        if q:
            anomalies = [a for a in anomalies
                         if q in (str(a['rule_id']) + ' ' + str(a['message']) + ' '
                                  + str(a.get('record_id') or '') + ' '
                                  + str(a.get('enumerator') or '')).lower()]

        # Enrich each flag with its record's site / interview date so the queue
        # can show them without a second lookup.
        id_map = {r['record_id']: r for r in records_index}
        for a in anomalies:
            idx = id_map.get(a.get('record_id'))
            a['site'] = idx['site'] if idx else ''
            a['date'] = idx['date'] if idx else ''
            a['population'] = idx['population'] if idx else ''

        sev = Counter(a['severity'] for a in anomalies)
        affected = {a['record_id'] for a in anomalies if a.get('record_id')}
        reviewed_flags = sum(1 for a in anomalies if a['review_status'] != 'new')
        by_rule = Counter(a['rule_id'] for a in anomalies)

        return Response({
            'population': population,
            'records_scanned': len(records_index),
            'anomaly_count': len(anomalies),
            'current_version': current_versions,
            'summary': {
                'by_severity': {k: sev.get(k, 0)
                                for k in ('critical', 'high', 'medium', 'low')},
                'top_rules': dict(by_rule.most_common(20)),
            },
            'kpis': {
                # FLAG counts — never collapsed to unique interviews.
                'critical': sev.get('critical', 0),
                'high': sev.get('high', 0),
                'medium': sev.get('medium', 0),
                'low': sev.get('low', 0),
                # Unique interview records with at least one (filtered) flag.
                'interviews_affected': len(affected),
                # FLAGS with a review decision (not 'new'), out of flags_total.
                'flags_reviewed': reviewed_flags,
                'flags_total': len(anomalies),
            },
            'anomalies': anomalies,
        })

    @action(detail=False, methods=['post'])
    def review(self, request):
        """Record/replace a review decision for one (submission_id, rule_id)."""
        sid = (request.data.get('submission_id') or '').strip()
        rid = (request.data.get('rule_id') or '').strip()
        new_status = (request.data.get('status') or '').strip()
        note = request.data.get('note', '') or ''
        if not sid or not rid:
            return Response({'detail': 'submission_id and rule_id are required.'},
                            status=http_status.HTTP_400_BAD_REQUEST)
        if new_status not in _REVIEW_STATUSES:
            return Response({'detail': f'status must be one of {sorted(_REVIEW_STATUSES)}.'},
                            status=http_status.HTTP_400_BAD_REQUEST)
        obj, _created = AnomalyReview.objects.update_or_create(
            submission_id=sid, rule_id=rid,
            defaults={'status': new_status, 'note': note,
                      'reviewed_by': request.user, 'reviewed_at': timezone.now()},
        )
        return Response({
            'submission_id': obj.submission_id, 'rule_id': obj.rule_id,
            'status': obj.status, 'note': obj.note,
            'reviewed_by': obj.reviewed_by.full_name if obj.reviewed_by else None,
            'reviewed_at': obj.reviewed_at.isoformat() if obj.reviewed_at else None,
        })
