import datetime
import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .flatten import flatten_group_keys
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import CanApproveSubmissions, OrgFilterMixin
from .models import FormType, KoboSubmission, SubmissionStatus
from .serializers import KoboSubmissionDetailSerializer, KoboSubmissionSerializer, RejectSerializer, ApproveSerializer
from .notify import send_approval_confirmation, send_rejection_notification, send_submission_alert
from .validators import validate_kobo_signature

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Webhook helpers
# ---------------------------------------------------------------------------

def _form_type_from_payload(payload: dict) -> str | None:
    xform_id = payload.get('_xform_id_string', '')
    # Primary: map by id_string set in XLS form settings sheet
    id_string_map = {
        'spondon_mpdsr_combined_v1': FormType.MPDSR,
        'spondon_baseline_v1': FormType.BASELINE,
        # D5 baseline study (CIPRB-conducted) — two key-population instruments.
        'ciprb_baseline_hijra_v1': FormType.BASELINE,
        'ciprb_baseline_fsw_v1': FormType.BASELINE,
        'spondon_fistula_v1': FormType.FISTULA,
        'spondon_fistula_staged_v1': FormType.FISTULA_STAGED,
        'spondon_mpdsr_response_plan_v1': FormType.MPDSR_RESPONSE_PLAN,
        # CIPRB 10 — the live MPDSR Response Plan form (deployed 2026-06-15).
        'ciprb_mpdsr_response_plan_v1': FormType.MPDSR_RESPONSE_PLAN,
        # Daily Activity / zero-report form — field staff submit once a day,
        # answering "Any activity today?". 'no' is tagged is_zero_report by
        # _is_zero_report(). Routes to ACTIVITY → lands in the manager queue.
        'spondon_daily_activity_v1': FormType.ACTIVITY,
    }
    if xform_id in id_string_map:
        return id_string_map[xform_id]
    # Fallback: some KoboToolbox deployments send asset UID in this field.
    # Hardcoded UIDs for the two new staged forms — these are CIPRB's
    # KoboToolbox asset UIDs delivered 2026-06-02; env-var override still
    # works via the existing settings.
    asset_uid_map = {
        # Hardcoded UIDs for the new staged forms (Rafi confirmed 2026-06-02)
        'aVMRPKVUdwcVAcixBszUKU': FormType.MPDSR_RESPONSE_PLAN,
        'auFCf7bfBDtrP6xeW5F2KJ': FormType.MPDSR_RESPONSE_PLAN,  # CIPRB 10 live asset
        'a4N3C9eZvUM5UJetngf5h7': FormType.FISTULA_STAGED,
        # Daily Activity / zero-report form asset UID (deployed 2026-06-03).
        # Kobo may send the asset UID as _xform_id_string instead of the
        # settings form_id, so accept both.
        'aJrk9VUUy9o6YGipAJ8H5t': FormType.ACTIVITY,
        # D5 baseline study assets (deployed 2026-06-26).
        'aBT7aCL9p4FGcW4WwXZcr6': FormType.BASELINE,  # Hijra / gender-diverse
        'aVsJ7VJ35k8GshpQpnXygC': FormType.BASELINE,  # Female Sex Workers
        # Env-var overrides for older forms
        getattr(settings, 'KOBO_ASSET_UID_MPDSR', ''): FormType.MPDSR,
        getattr(settings, 'KOBO_ASSET_UID_FISTULA', ''): FormType.FISTULA,
        getattr(settings, 'KOBO_ASSET_UID_ACTIVITY', ''): FormType.ACTIVITY,
        getattr(settings, 'KOBO_ASSET_UID_BASELINE', ''): FormType.BASELINE,
    }
    # Drop unconfigured env overrides. Those settings default to the literal
    # 'placeholder' (spondon/settings/base.py), so an unset KOBO_ASSET_UID_*
    # would otherwise leave a GUESSABLE routing key that maps to a real form
    # type: anyone holding the webhook secret could post _xform_id_string=
    # 'placeholder' and have it ingested. Worse, if several were unset they
    # would collide on that one key and last-wins would route it to BASELINE,
    # which is the one form type that auto-approves. Security audit, Oct 2026.
    for _unset in ('', 'placeholder'):
        asset_uid_map.pop(_unset, None)
    return asset_uid_map.get(xform_id)


def _partner_from_payload(payload: dict) -> str:
    raw = (
        payload.get('partner_org') or payload.get('partner') or payload.get('organisation') or ''
    ).strip().upper()
    if 'PHD' in raw:
        return 'PHD'
    if 'BANDHU' in raw or 'BONDHU' in raw or 'BONDU' in raw:
        return 'Bandhu'
    return ''


_ZERO_TRUE = {'yes', 'true', '1', 'no_activity', 'zero', 'none', 'nothing'}
_ZERO_FALSE = {'no', 'false', '0', ''}


def _is_zero_report(payload: dict) -> bool:
    """Detect a daily 'no activity / zero patient' report.

    Accepts several Kobo question conventions so the form author has
    freedom: an explicit `zero_report`/`no_activity` flag set truthy, OR an
    `any_activity`/`had_activity` question answered 'no'. Defaults to False
    (a normal data-bearing submission)."""
    for key in ('zero_report', 'no_activity', 'no_data', 'is_zero_report'):
        v = str(payload.get(key, '')).strip().lower()
        if v in _ZERO_TRUE:
            return True
    for key in ('any_activity', 'had_activity', 'activity_today', 'patients_seen_today'):
        if key in payload:
            v = str(payload.get(key, '')).strip().lower()
            if v in _ZERO_FALSE:
                return True
    return False


def _district_from_payload(payload: dict, form_type: str) -> str:
    if form_type == FormType.MPDSR:
        sub = payload.get('form_type', '')
        field = f'{sub}_district' if sub else ''
        d = payload.get(field) or payload.get('district') or ''
        if d:
            return d
    else:
        d = payload.get('district') or ''
        if d:
            return d

    # Fallback: most PHD/Bandhu forms capture `center_code` instead of asking
    # for district directly. Look up the centre's home district so the
    # submission can still surface in district-level rankings.
    code = (payload.get('center_code') or payload.get('centre_code') or '').strip()
    if code:
        try:
            from programs.models.center import ServiceCenter
            sc = ServiceCenter.objects.filter(code=code).only('district').first()
            if sc and sc.district:
                return sc.district
        except Exception:
            pass
    return ''


def _geolocation(payload: dict) -> tuple[float | None, float | None]:
    geo = payload.get('_geolocation')
    if not isinstance(geo, (list, tuple)) or len(geo) < 2:
        # Kobo sometimes sends _geolocation as an object/null; geo[0] on a dict
        # raises KeyError (not in the old except tuple) → 500 → stranded sub.
        return None, None
    try:
        return float(geo[0]), float(geo[1])
    except (TypeError, ValueError):
        return None, None


def _parse_submitted_at(raw: str) -> datetime.datetime:
    if not raw:
        return timezone.now()
    try:
        dt = datetime.datetime.fromisoformat(raw)
        if timezone.is_naive(dt):
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except (ValueError, TypeError):
        return timezone.now()


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

def _notify_gps_rejection(payload: dict, form_type: str) -> None:
    """Notify managers that a submission was rejected due to missing GPS."""
    try:
        worker_name = (
            payload.get('collector_name') or
            payload.get('worker_name') or
            payload.get('enumerator_name') or
            payload.get('_submitted_by') or 'Field worker'
        )
        from .notify import send_gps_rejection_notice
        send_gps_rejection_notice(worker_name, form_type)
    except Exception as exc:
        logger.debug('GPS rejection Telegram failed: %s', exc)


@csrf_exempt
@require_POST
def kobo_webhook(request):
    """
    POST /webhook/kobo/
    Receives KoboToolbox REST service payloads.
    """
    if not validate_kobo_signature(request):
        logger.warning('Webhook rejected — bad signature from %s', request.META.get('REMOTE_ADDR'))
        return HttpResponse('Forbidden', status=403)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse('Bad Request — expected JSON body', status=400)
    if not isinstance(payload, dict):
        # A non-object body (array/string/number) would AttributeError on
        # payload.get(...) below → 500 → Kobo retries forever and STRANDS the
        # GBV/MPDSR/fistula submission. Reject cleanly instead.
        return HttpResponse('Bad Request — expected a JSON object', status=400)

    # Kobo serialises grouped questions as 'group/field'. Every reader downstream
    # (district/site extraction here, then monitoring, srhr, insights) uses flat
    # leaf names, so add the flat aliases ONCE, here. Originals are KEPT, so no
    # handler that reads a prefixed path can break. Without this the D5 baseline
    # stored 300+ nested keys nothing could read — every indicator returned n=0
    # while the answers sat in the payload. See submissions/flatten.py.
    payload = flatten_group_keys(payload)

    kobo_id = str(payload.get('_id', '')).strip()
    if not kobo_id:
        return HttpResponse('Bad Request — missing _id', status=400)

    if KoboSubmission.objects.filter(kobo_id=kobo_id).exists():
        return HttpResponse('OK', status=200)  # idempotent

    form_type = _form_type_from_payload(payload)
    if not form_type:
        logger.warning('Unknown form UID: %s', payload.get('_xform_id_string'))
        return HttpResponse('Bad Request — unrecognised form UID', status=400)

    lat, lng = _geolocation(payload)

    # GPS location is mandatory on every field submission — reject without it.
    # EXCEPTION: BASELINE is a ~50-minute CAPI interview — never discard a
    # completed interview over a missing GPS fix. Store it (lat/lng may be null)
    # and let the CIPRB verifier flag it; the form still requires a cluster geopoint.
    if (lat is None or lng is None) and form_type != FormType.BASELINE:
        logger.warning(
            'Webhook rejected — GPS missing. form=%s kobo_id=%s',
            form_type, kobo_id,
        )
        _notify_gps_rejection(payload, form_type)
        return HttpResponse(
            'Bad Request — location data is required. '
            'Please enable GPS/location on your phone and resubmit.',
            status=400,
        )

    # Auto-approval list. FISTULA_STAGED and MPDSR_RESPONSE_PLAN are CIPRB-
    # owned, written by trained clinical staff, and flow straight to the
    # dashboard without a manager queue. BASELINE auto-approved until the D5
    # baseline gained a CIPRB verification gate (2026-06-25): it now lands
    # PENDING and a CIPRB supervisor approves each interview in the baseline
    # area before it counts. MPDSR (F1–F6 combined) and FISTULA (legacy
    # campaign) still queue for manager review (broader field-staff submitters).
    # BASELINE auto-approves at ingest (Rafi 2026-07-09: "baseline does not need
    # any approval"). The D5 baseline is a CIPRB-conducted CAPI survey, not
    # field-staff service data — every completed interview counts immediately, so
    # it lands APPROVED and the post_save signal materialises the BaselineResponse
    # right away (no CIPRB verification queue). Everything else still queues for
    # manager review.
    _AUTO_APPROVE = {FormType.BASELINE}
    initial_status = SubmissionStatus.APPROVED if form_type in _AUTO_APPROVE else SubmissionStatus.PENDING

    # MPDSR and Baseline are CIPRB-owned surveillance/survey activities.
    # Always attribute them to CIPRB regardless of the data-collector
    # organisation in the payload (the form offers PHD/Bondhu for the
    # collector, but ownership of the record is CIPRB). Other forms keep
    # their detected partner.
    if form_type in (FormType.MPDSR, FormType.BASELINE, FormType.FISTULA_STAGED, FormType.MPDSR_RESPONSE_PLAN):
        partner = 'CIPRB'
    else:
        partner = _partner_from_payload(payload)

    submission = KoboSubmission.objects.create(
        kobo_id=kobo_id,
        form_type=form_type,
        status=initial_status,
        partner=partner,
        worker_name=(
            payload.get('collector_name') or
            payload.get('worker_name') or
            payload.get('enumerator_name') or
            # KoboToolbox always stamps the submitting account's username on
            # authenticated submissions. Use it so forms without an explicit
            # name question still attribute the submitter (no more "Unknown").
            payload.get('_submitted_by') or ''
        ),
        district=_district_from_payload(payload, form_type),
        region=payload.get('division') or payload.get('region') or '',
        # Denormalise centre code at ingest time so the 74-hour Programme
        # Health Flag system can compute per-centre 'X of N submitted today'
        # without joining through raw_data JSON. Accept both spellings —
        # field forms vary between center_code / centre_code / site_code.
        centre_code=(
            payload.get('center_code')
            or payload.get('centre_code')
            or payload.get('site_code')
            or ''
        ).strip()[:40],
        latitude=lat,
        longitude=lng,
        submitted_at=_parse_submitted_at(payload.get('_submission_time', '')),
        raw_data=payload,
        is_zero_report=_is_zero_report(payload),
    )

    try:
        send_submission_alert(submission)
    except Exception as exc:
        logger.error('Telegram dispatch error: %s', exc)

    # A new baseline interview changes the anomaly report — drop its 5-min cache
    # so the next dashboard load re-scans (best-effort; never block ingest).
    if form_type == FormType.BASELINE:
        try:
            from baseline.anomaly import invalidate_cache
            invalidate_cache()
        except Exception as exc:
            logger.warning('Anomaly cache invalidation skipped: %s', exc)

    logger.info(
        'Submission ingested: %s [%s / %s] status=%s',
        submission.id, form_type, submission.partner, initial_status,
    )
    return HttpResponse('Created', status=201)


# ---------------------------------------------------------------------------
# Manager approval API
# ---------------------------------------------------------------------------

class KoboSubmissionViewSet(OrgFilterMixin, ModelViewSet):
    # Audit FIX C2/H2 — the approval queue exposes the full Kobo `raw_data`
    # blob (unencrypted deceased/patient names, NID, phone, address for
    # MPDSR/Fistula) on retrieve, and the approve/reject actions mutate
    # surveillance data. Both were previously reachable by FIELD_STAFF via
    # IsSupervisorOrManager. Restricting the whole viewset to
    # CanApproveSubmissions (dev/supervisor/org_lead/manager) closes the
    # field-staff raw-PII read AND the unauthorised approve/reject in one
    # gate — field staff, focal and baseline have no business in the queue.
    queryset = KoboSubmission.objects.select_related('reviewed_by').all()
    permission_classes = [CanApproveSubmissions]
    http_method_names = ['get', 'head', 'options', 'post']
    org_field = 'partner'

    def get_queryset(self):
        qs = super().get_queryset()
        # Baseline interviews have their OWN CIPRB verification queue
        # (/baseline/verification/, BaselineVerificationViewSet). They must never
        # surface in this generic approval queue: (1) the frontend renders them
        # as a wrong 'legacy' card in the CIPRB tab, duplicating the Baseline
        # tab; (2) approving via this lane is gated only by CanApproveSubmissions
        # (dev/supervisor/manager) which side-steps the narrower CanApproveBaseline
        # gate (developer + CIPRB manager) — e.g. a UNFPA supervisor could approve
        # a baseline here. Enforce the exclusion the line-311 comment always
        # intended. Shared by list/retrieve/approve/reject, so baseline is
        # unreachable through this viewset entirely (approve it via /baseline/).
        qs = qs.exclude(form_type=FormType.BASELINE)
        status_param = self.request.query_params.get('status')
        form_type = self.request.query_params.get('form_type')
        if status_param:
            qs = qs.filter(status=status_param)
        if form_type:
            qs = qs.filter(form_type=form_type)
        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return KoboSubmissionDetailSerializer
        if self.action == 'reject':
            return RejectSerializer
        return KoboSubmissionSerializer

    def create(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Submissions arrive via KoboToolbox webhook only.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        submission = self.get_object()
        if submission.status != SubmissionStatus.PENDING:
            return Response(
                {'detail': f'Cannot approve — current status is "{submission.status}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        note = ''
        ser = ApproveSerializer(data=request.data)
        if ser.is_valid():
            note = ser.validated_data.get('note', '')
        submission.status = SubmissionStatus.APPROVED
        submission.reviewed_by = request.user
        submission.reviewed_at = timezone.now()
        submission.add_review_entry(user=request.user, action='approved', note=note)
        submission.save()
        try:
            send_approval_confirmation(submission)
        except Exception as exc:
            logger.error('Telegram approval notification error: %s', exc)
        return Response(KoboSubmissionSerializer(submission).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        submission = self.get_object()
        if submission.status != SubmissionStatus.PENDING:
            return Response(
                {'detail': f'Cannot reject — current status is "{submission.status}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = RejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data['rejection_reason']
        submission.status = SubmissionStatus.REJECTED
        submission.reviewed_by = request.user
        submission.reviewed_at = timezone.now()
        submission.rejection_reason = reason
        submission.add_review_entry(user=request.user, action='rejected', note=reason)
        submission.save()
        try:
            send_rejection_notification(submission)
        except Exception as exc:
            logger.error('Telegram rejection notification error: %s', exc)
        return Response(KoboSubmissionSerializer(submission).data)
