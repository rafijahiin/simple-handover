"""
Indicators API views.

GET    /api/indicators/targets/          → list all IndicatorTarget records
                                            (filtered to user's partner if
                                            not can_see_all_orgs)
PATCH  /api/indicators/targets/<id>/     → edit target_value or other fields
                                            (CanConfigureTargets — Org Lead
                                            is restricted to own partner)
GET    /api/indicators/progress/         → live actual-vs-target per indicator
GET    /api/indicators/progress/<code>/  → single indicator progress

Query params for progress endpoints:
  org          — override org (developer / supervisor / org_lead only)
  period_start — YYYY-MM-DD
  period_end   — YYYY-MM-DD
"""
import logging
from datetime import date, datetime

from rest_framework import status, viewsets, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import CanConfigureTargets
from .models import IndicatorTarget, KoboFormMapping
from .serializers import (
    IndicatorProgressSerializer,
    IndicatorTargetSerializer,
    KoboFormMappingSerializer,
)
from .service import get_partner_indicator_progress, get_indicator_progress

logger = logging.getLogger(__name__)

DEFAULT_PERIOD_START = date(2026, 5, 21)
DEFAULT_PERIOD_END   = date(2026, 11, 20)


def _resolve_params(request):
    """Extract org + period from query params, applying permission constraints."""
    user = request.user

    requested_org = request.query_params.get('org')
    if user.can_see_all_orgs and requested_org:
        org = requested_org
    elif user.can_see_all_orgs:
        org = None  # caller must handle None → "all orgs"
    elif user.can_read_other_orgs and requested_org:
        # Org Lead can request any org for read; their writes are gated
        # elsewhere via can_configure_targets.
        org = requested_org
    else:
        org = user.organisation

    def _parse_date(param, default):
        raw = request.query_params.get(param)
        if raw:
            try:
                return datetime.strptime(raw, '%Y-%m-%d').date()
            except ValueError:
                pass
        return default

    period_start = _parse_date('period_start', DEFAULT_PERIOD_START)
    period_end   = _parse_date('period_end',   DEFAULT_PERIOD_END)
    return org, period_start, period_end


class IndicatorTargetViewSet(viewsets.ModelViewSet):
    """
    Read + write for IndicatorTarget rows. Used by the Target Config screen
    at /admin/targets.

    Permission model:
      List + retrieve — any authenticated user; queryset is partner-filtered
        for users without `can_read_other_orgs`.
      Create + update + patch + delete — gated by `CanConfigureTargets`,
        which permits Developer + Supervisor for any partner and Org Lead
        only for their own partner.
    """
    queryset = IndicatorTarget.objects.select_related('partner', 'source_form', 'updated_by').all()
    serializer_class = IndicatorTargetSerializer
    permission_classes = [CanConfigureTargets]
    http_method_names = ['get', 'head', 'options', 'post', 'patch', 'delete']

    def get_queryset(self):
        qs = (
            IndicatorTarget.objects
            .select_related('partner', 'source_form', 'updated_by')
            .filter(is_active=True)
        )
        user = self.request.user
        # Read filter: managers, field staff, focals see only own partner.
        # Org Lead and Supervisor and Developer see all.
        if not user.can_read_other_orgs:
            qs = qs.filter(partner__code=user.organisation)
        return qs.order_by('partner__code', 'objective_number', 'activity_code')

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class KoboFormMappingViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only registry of Kobo forms. Filled at the validation workshop
    via Django admin or a follow-up management command."""
    queryset = KoboFormMapping.objects.filter(is_active=True).select_related('partner').order_by('form_slug')
    serializer_class = KoboFormMappingSerializer
    permission_classes = [IsAuthenticated]


class IndicatorProgressView(views.APIView):
    """
    GET /api/indicators/progress/
    Returns all indicators for the resolved org(s) with actual vs target.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        org, period_start, period_end = _resolve_params(request)
        today = timezone.now().date()

        if org is None:
            results = []
            # Iterate all three partners so the homepage roll-up can pull
            # the same shape and aggregate. CIPRB rows are all unlinked
            # for now (no compute functions) but still surface.
            for o in ('CIPRB', 'Bandhu', 'PHD'):
                rows = get_partner_indicator_progress(o, period_start, period_end, today=today)
                for r in rows:
                    r['organisation'] = o
                results.extend(rows)
        else:
            results = get_partner_indicator_progress(org, period_start, period_end, today=today)
            for r in results:
                r['organisation'] = org

        serializer = IndicatorProgressSerializer(results, many=True)
        return Response(serializer.data)


class PhdRegistryKpiView(views.APIView):
    """
    GET /api/indicators/phd-registry/
    The PHD "FSWs reached" headline = the Mother List registry (distinct
    approved, non-stub PHD clients), returned as one IndicatorProgress-shaped
    row (code SL1R). Deliberately kept out of /progress/ so the SIDA framework
    table and roll-ups are unaffected; only the PHD headline card reads this.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        from .service import get_phd_registry_kpi

        org, period_start, period_end = _resolve_params(request)
        # PHD-only KPI: all-orgs users (org is None) and PHD readers may see it;
        # a Bandhu-only manager may not.
        if org not in (None, 'PHD'):
            return Response({'detail': 'Access denied.'},
                            status=status.HTTP_403_FORBIDDEN)
        row = get_phd_registry_kpi(period_start, period_end,
                                   timezone.now().date())
        row['organisation'] = 'PHD'
        return Response(row)


class SingleIndicatorProgressView(views.APIView):
    """
    GET /api/indicators/progress/<code>/
    Returns progress for a single indicator.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        from django.utils import timezone
        org, period_start, period_end = _resolve_params(request)
        if org is None:
            return Response(
                {'detail': 'Specify ?org=Bandhu or ?org=PHD for single indicator lookup.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = get_indicator_progress(org, code, period_start, period_end,
                                        today=timezone.now().date())
        result['organisation'] = org
        return Response(result)


class IndicatorRecordsView(views.APIView):
    """
    GET /api/indicators/records/?partner=PHD&activity_code=1.1

    Per-indicator record drill-down for the /records page (audit FIX 6.5).
    Returns approved records that contribute to this indicator's achievement
    count, paginated and ordered newest-first.

    Forbidden for field_staff, focal, and ciprb_baseline (UI guards the route
    too — defence-in-depth). Org-scoped users see only own partner's data.

    Until KoboFormMapping → IndicatorTarget links are seeded at the workshop,
    the underlying compute function may not expose a record-level queryset.
    In that case we return an empty list + a `module_pending` flag so the UI
    can render a "wired at workshop" notice instead of an error.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        # Defence-in-depth — field staff / focal / baseline get 403.
        from accounts.models import Role
        if u.role in (Role.FIELD_STAFF, Role.FOCAL, Role.CIPRB_BASELINE):
            return Response(
                {'detail': 'Forbidden — your role does not have record-list access.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        partner_code = request.query_params.get('partner', '').strip()
        activity_code = request.query_params.get('activity_code', '').strip()
        if not partner_code or not activity_code:
            return Response(
                {'detail': 'partner and activity_code query params are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Org isolation — non-cross-org users can only query their own partner.
        if not u.can_read_other_orgs and partner_code != u.organisation:
            return Response(
                {'detail': 'Forbidden — cannot query another partner.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Look up the indicator definition.
        try:
            target = (
                IndicatorTarget.objects
                .select_related('partner', 'source_form')
                .get(partner__code=partner_code, activity_code=activity_code)
            )
        except IndicatorTarget.DoesNotExist:
            return Response(
                {'detail': f'No indicator at {partner_code}/{activity_code}.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Module-pending = no compute function wired yet, or source_form
        # not set. Return empty list with metadata so UI can show the
        # "wired at workshop" state instead of erroring.
        from .service import _REGISTRIES
        registry, _org_only = _REGISTRIES.get(partner_code, ({}, set()))
        has_compute = activity_code in registry
        if not has_compute:
            return Response({
                'partner':         partner_code,
                'activity_code':   activity_code,
                'activity_label':  target.activity_label,
                'indicator_label': target.indicator_label,
                'target_value':    target.target_value,
                'unit':            target.unit,
                'module_pending':  True,
                'count':           0,
                'results':         [],
            })

        # Compute function exists — but the unified record-list contract isn't
        # standardised across all activity codes yet. For Step 8 we return the
        # achievement total (computed via the existing compute function) and
        # an empty `results` array with `awaiting_workshop_wiring=True`. The
        # workshop will confirm which model rows roll up into each indicator;
        # at that point a per-activity-code records adapter can be wired here
        # without a new endpoint.
        result = get_indicator_progress(
            partner_code, activity_code,
            DEFAULT_PERIOD_START, DEFAULT_PERIOD_END,
        )
        return Response({
            'partner':                  partner_code,
            'activity_code':            activity_code,
            'activity_label':           target.activity_label,
            'indicator_label':          target.indicator_label,
            'target_value':             target.target_value,
            'unit':                     target.unit,
            'achievement':              result.get('achievement', 0),
            'percentage':               result.get('percentage'),
            'module_pending':           False,
            'awaiting_workshop_wiring': True,
            'count':                    0,
            'results':                  [],
        })
