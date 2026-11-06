"""
Programs API views.

Organisation filtering:
  - developer / supervisor (can_see_all_orgs) → no org filter
  - CIPRB org_lead (can_read_other_orgs) → no filter (read-only on other
    partners); a PHD/Bandhu org_lead is org-bound like a manager
  - manager / field_staff → filtered to their own org

Approval:
  POST /<model>/<pk>/approve/  or  POST /<model>/<pk>/reject/
  Only managers (of the same org), supervisors, developers, and org_leads
  (own partner only) can approve/reject.
"""
import json
import logging
import uuid as _uuid

import requests as _requests
from django.conf import settings as _settings
from django.db import transaction as _tx
from django.utils import timezone
from rest_framework import viewsets, views, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from accounts.permissions import (
    CanWriteFieldRecord, CanWriteOutreach, CanWriteOrgRecord,
    CanAccessFistulaCases, CanAccessMPDSR, CanApproveCIPRBAction,
)

from .models import (
    GBVCornerRecord,
    ServiceCenter, Client,
    ClinicVisit, HIVSTITestResult, ADRRecord, AutoclaveLog, AntenatalCard,
    HTCCounselling, IndividualCounselling, MHScreening,
    GBVCase, GBVAccessLog,
    OutreachSession, GroupEducationSession, WellnessLogbookEntry,
    Referral,
    IECMaterial,
    StockEntry, TemperatureLog, SafetyHygieneKit, StoreRequisition,
    TrainingEvent, CoordMeeting, MobileHealthCamp, VisitorRegister,
    NilReport, PHDCounsellingReport,
)
from fistula.ciprb_models import CIPRBFistulaCase
from fistula.models import FistulaCampaign
from mpdsr.models import MPDSRCase, MPDSRAction, STUB_ACTIVITY_SENTINEL
from mpdsr.ciprb_models import (MPDSRDeathNotification, MaternalNearMissCase,
                                SurgeryChecklist)
from .serializers import CIPRBFistulaCaseSerializer, FistulaCampaignApprovalSerializer
from .serializers import (
    MPDSRCaseApprovalSerializer,
    MPDSRDeathNotificationApprovalSerializer,
    MaternalNearMissApprovalSerializer,
    SafeSurgeryApprovalSerializer,
    MPDSRActionSerializer,
)
from .serializers import (
    ServiceCenterSerializer, ClientSerializer,
    ClinicVisitSerializer, HIVSTITestResultSerializer, ADRRecordSerializer,
    AutoclaveLogSerializer, AntenatalCardSerializer,
    HTCCounsellingSerializer, IndividualCounsellingSerializer, MHScreeningSerializer,
    GBVCaseSerializer, GBVCaseDetailSerializer,
    IECMaterialSerializer,
    OutreachSessionSerializer, GroupEducationSessionSerializer,
    WellnessLogbookEntrySerializer, PHDCounsellingReportSerializer,
    ReferralSerializer, ReferralOutcomeSerializer,
    StockEntrySerializer, TemperatureLogSerializer,
    SafetyHygieneKitSerializer, StoreRequisitionSerializer,
    TrainingEventSerializer, CoordMeetingSerializer,
    MobileHealthCampSerializer, VisitorRegisterSerializer,
)

logger = logging.getLogger(__name__)


def _send_approval_telegram(org: str, form_label: str, reviewer_name: str, approved: bool, reason: str = '') -> None:
    """
    Notify the org's Telegram chat when a programs submission is approved/rejected.
    Field workers and managers are in the same org group chat.
    """
    token = getattr(_settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token:
        return
    try:
        chat_ids = json.loads(getattr(_settings, 'TELEGRAM_CHAT_IDS', '{}'))
    except Exception:
        return
    chat_id = chat_ids.get(org)
    if not chat_id:
        return
    if approved:
        text = (
            f'<b>✅ Submission Approved</b>\n\n'
            f'Organisation: {org}\n'
            f'Form: {form_label}\n'
            f'Approved by: {reviewer_name}'
        )
    else:
        text = (
            f'<b>❌ Submission Rejected</b>\n\n'
            f'Organisation: {org}\n'
            f'Form: {form_label}\n'
            f'Rejected by: {reviewer_name}'
            + (f'\nReason: {reason}' if reason else '')
        )
    try:
        _requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            timeout=5,
        ).raise_for_status()
    except Exception as exc:
        logger.error('Programs approval Telegram error: %s', exc)


def _authorise_review(obj, user):
    """May this user act on this record? Shared by approve, reject and delete.

    A developer is the system super-admin (acts on any stage or org) even
    though their org is UNFPA. UNFPA non-developers are the dedicated stage-2
    gate for Bandhu.
    """
    uorg = user.organisation
    urole = getattr(user, 'role', '')
    is_super = (urole == 'developer') or (
        bool(getattr(user, 'can_see_all_orgs', False)) and uorg != 'UNFPA')
    is_unfpa = (uorg == 'UNFPA') and urole != 'developer'
    if not user.can_approve_submissions:
        return Response({'detail': 'Not authorised.'}, status=status.HTTP_403_FORBIDDEN)
    if not (is_super or obj.organisation == uorg
            or (is_unfpa and obj.organisation == 'Bandhu')):
        return Response({'detail': 'Not authorised.'}, status=status.HTTP_403_FORBIDDEN)
    return None


def _delete_record(obj, user, reason=''):
    """Remove a record from Spondon for good, with a trail.

    Rejecting takes a record out of every figure and keeps it visible. Deleting
    is for data that should never have been submitted at all, which partners
    previously had to do in KoboToolbox and which then left the row here still
    counted. Doing it from the approval queue keeps both sides in one action.

    The KoboToolbox copy is deliberately left alone: it is the raw submission
    and the only remaining evidence of what was removed. Nothing re-imports it,
    so the record does not come back.
    """
    from django.db.models import ProtectedError
    from programs.kobo_withdrawals import _snapshot
    from programs.models import KoboWithdrawal

    err = _authorise_review(obj, user)
    if err is not None:
        return err
    if not (reason or '').strip():
        return Response(
            {'detail': 'Say why this record is being deleted. The reason is '
                       'kept as the only record of what was removed.'},
            status=status.HTTP_400_BAD_REQUEST)

    entry = KoboWithdrawal(
        model_label=obj._meta.label,
        record_pk=str(obj.pk),
        kobo_submission_id=str(getattr(obj, 'kobo_submission_id', '') or ''),
        organisation=str(getattr(obj, 'organisation', '') or ''),
        approval_status=str(getattr(obj, 'approval_status', '') or ''),
        snapshot=_snapshot(obj),
        # The user model logs in by email; there is no username, and a
        # blank actor would make the trail useless.
        actor=(getattr(user, 'email', '') or
               getattr(user, 'full_name', '') or 'dashboard'),
        reason=(reason or '').strip(),
    )
    try:
        with _tx.atomic():
            entry.save()
            obj.delete()
    except ProtectedError:
        # Service records point at this row. Deleting would leave a woman's
        # clinic or counselling history attached to nobody, so it is refused
        # here exactly as it is refused in the Kobo sweep.
        return Response(
            {'detail': 'This record cannot be deleted because service records '
                       'are attached to it. Remove those first, or reject it '
                       'instead so it stops being counted.'},
            status=status.HTTP_409_CONFLICT)
    return None


def _apply_decision(obj, user, action_type, reason):
    """Apply an approve/reject decision with the org-aware two-stage rules.

    Bandhu Service Log + Activity & Operations (and NilReport) are two-stage:
        PENDING --manager--> MANAGER_APPROVED --UNFPA--> APPROVED
    PHD / CIPRB are single-stage (PENDING --> APPROVED). Used by BOTH approval
    entrypoints (PendingApprovalsView and the per-model viewset action) so a
    Bandhu record can never bypass the UNFPA gate.

    Mutates `obj` in place on success and returns None; returns a DRF Response
    on any authorisation / state error (caller returns it as-is).
    """
    err = _authorise_review(obj, user)
    if err is not None:
        return err
    uorg = user.organisation
    urole = getattr(user, 'role', '')
    is_super = (urole == 'developer') or (bool(getattr(user, 'can_see_all_orgs', False)) and uorg != 'UNFPA')
    is_unfpa = (uorg == 'UNFPA') and urole != 'developer'

    # Two-stage (Bandhu manager → UNFPA) applies ONLY to models that carry the
    # manager-stage fields, i.e. SubmissionBase records. Client (the Mother List
    # registry) is a plain TimestampedModel with PENDING/APPROVED/REJECTED only
    # and NO manager_approved_by/at — so a Bandhu registration is single-stage:
    # the manager's approval finalises it. Without this guard, approving a Bandhu
    # Client ran `obj.manager_approved_by = user` → AttributeError → 500 (the
    # "approve button does nothing" bug, exposed once registration stopped
    # auto-approving). hasattr keeps every real SubmissionBase model two-stage.
    two_stage = (obj.organisation == 'Bandhu') and hasattr(obj, 'manager_approved_by')
    cur = obj.approval_status
    now = timezone.now()

    if action_type == 'approve':
        if two_stage and cur == 'PENDING':
            if not (is_super or uorg == 'Bandhu'):
                return Response({'detail': 'Manager-stage approval is for the Bandhu manager.'},
                                status=status.HTTP_403_FORBIDDEN)
            obj.approval_status = 'MANAGER_APPROVED'
            obj.manager_approved_by = user
            obj.manager_approved_at = now
            obj.rejected_reason = ''
        elif two_stage and cur == 'MANAGER_APPROVED':
            # Stage 2 is UNFPA-ONLY. A developer/super may do stage 1 (support),
            # but must NOT finalise a Bandhu record — otherwise one actor (or the
            # developer) bypasses the UNFPA gate the two-stage flow exists to
            # enforce. Only UNFPA closes stage 2. (Bug 2026-06: a developer could
            # self-approve both stages because is_super was accepted here too.)
            if not is_unfpa:
                return Response({'detail': 'Final approval is for UNFPA only.'},
                                status=status.HTTP_403_FORBIDDEN)
            obj.approval_status = 'APPROVED'
            obj.approved_by = user
            obj.approved_at = now
            obj.rejected_reason = ''
        elif cur == 'PENDING':
            obj.approval_status = 'APPROVED'
            obj.approved_by = user
            obj.approved_at = now
            obj.rejected_reason = ''
        else:
            return Response({'status': cur, 'detail': 'Already processed.'},
                            status=status.HTTP_409_CONFLICT)
    elif action_type == 'reject':
        if not str(reason).strip():
            return Response({'detail': 'A reason is required to reject.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if two_stage and cur == 'MANAGER_APPROVED':
            if not (is_super or is_unfpa):
                return Response({'detail': 'Not authorised.'}, status=status.HTTP_403_FORBIDDEN)
            obj.approval_status = 'PENDING'
            obj.manager_approved_by = None
            obj.manager_approved_at = None
            obj.rejected_reason = reason
        elif cur == 'PENDING':
            # Symmetric with the approve guard above: for a two-stage (Bandhu)
            # record only the Bandhu manager / super may issue the STAGE-1
            # rejection. UNFPA acts strictly at stage 2 — without this it could
            # reject a PENDING item its GET lane never showed it (TOCTOU),
            # skipping the manager gate entirely.
            if two_stage and not (is_super or uorg == 'Bandhu'):
                return Response({'detail': 'Stage-1 rejection is for the Bandhu manager.'},
                                status=status.HTTP_403_FORBIDDEN)
            obj.approval_status = 'REJECTED'
            obj.rejected_reason = reason
        else:
            return Response({'status': cur, 'detail': 'Already processed.'},
                            status=status.HTTP_409_CONFLICT)
    else:
        return Response({'detail': "action must be 'approve', 'reject' or 'delete'."},
                        status=status.HTTP_400_BAD_REQUEST)

    # Record the decision in the object's own durable audit trail when it keeps
    # one (MPDSRAction / MPDSRCase). The approve/reject decision otherwise lives
    # only in approved_by/approved_at — which a later edit nulls — so WHO signed
    # off on which version, and the rejection reason, would be lost (audit FIX
    # 2026-06). The caller's obj.save() persists this.
    if hasattr(obj, 'add_audit_entry') and hasattr(obj, 'audit_trail'):
        _note = reason if action_type == 'reject' else obj.approval_status
        obj.add_audit_entry(getattr(user, 'email', '') or str(user),
                            f'{action_type}d', _note or '')

    # Decision is valid and about to be committed by the caller. Once it commits,
    # invalidate THIS partner's cached indicator achievements so the dashboard
    # recomputes the new totals on its next load — instant with a shared Redis
    # cache (the bump is seen by every worker); CACHE_TTL backstops the per-worker
    # LocMem fallback. on_commit so we never invalidate ahead of a rolled-back txn.
    from django.db import transaction as _txn
    from indicators.service import bump_partner_version
    _org = obj.organisation
    _txn.on_commit(lambda: bump_partner_version(_org))
    return None


def _org_filter(queryset, request):
    """Apply organisation filter based on user permissions.

    Audit FIX 15.7 — field staff additionally restricted to own entries
    via the submitted_by FK on SubmissionBase. Models without a
    submitted_by field (ServiceCenter / Client) fall back to plain org
    isolation, which is correct — those are reference tables, not
    field-submitted records."""
    from accounts.models import Role
    user = request.user
    if user.can_see_all_orgs or user.can_read_other_orgs:
        return queryset
    queryset = queryset.filter(organisation=user.organisation)
    if user.role == Role.FIELD_STAFF:
        # Probe the model for submitted_by before filtering — keeps the
        # filter a no-op on reference tables that don't carry the FK.
        if any(f.name == 'submitted_by' for f in queryset.model._meta.get_fields()):
            queryset = queryset.filter(submitted_by=user)
    return queryset


class OrgFilteredViewSet(viewsets.ModelViewSet):
    """Base viewset that filters by org and handles approval actions.

    Default permission is CanWriteOrgRecord (fail-closed): reads open to all
    authenticated users, writes denied to focal (view-only) and ciprb_baseline
    (survey-only). Subclasses carrying stricter rules (CanWriteFieldRecord /
    CanWriteOutreach) override below; the ones that previously relied on the
    bare IsAuthenticated default now inherit this safe gate instead of letting
    any logged-in role POST/PATCH/DELETE records that feed the indicators."""
    permission_classes = [CanWriteOrgRecord]

    def get_queryset(self):
        return _org_filter(super().get_queryset(), self.request)

    def _approve_or_reject(self, request, pk, action_type):
        user = request.user
        with _tx.atomic():
            qs = self.get_queryset()
            try:
                # of=('self',) locks ONLY the base row. Several querysets here
                # select_related('approved_by'), a nullable FK → LEFT OUTER JOIN;
                # a bare select_for_update() would try to lock that join's
                # nullable side and Postgres raises NotSupportedError, which a
                # blanket except would mask as a misleading 404. Lock self only,
                # and only treat a genuine missing row as 404.
                obj = qs.select_for_update(of=('self',)).get(pk=pk)
            except qs.model.DoesNotExist:
                return Response({'detail': 'Record not found.'}, status=status.HTTP_404_NOT_FOUND)

            # Shared two-stage decision (Bandhu manager → UNFPA; PHD/CIPRB
            # single-stage). Defence-in-depth: same rules as the queue endpoint.
            reason = request.data.get('reason', '')
            err = _apply_decision(obj, user, action_type, reason)
            if err is not None:
                return err
            obj.save()

        # Email the partner's managers/focal + the submitter (resolved from
        # the User FK OR the raw_payload's email-shaped field) about the
        # decision. Rejection emails carry the Enketo collect link for the
        # same form so the worker can submit a corrected entry in one click.
        try:
            from submissions.email_notify import _recipients_for, _send
            label = _humanise_label(obj._meta.verbose_name)
            recipients = _recipients_for(obj.organisation)
            # Worker notification: pull the email out of the User FK first,
            # then fall back to whatever the form captured in raw_payload.
            sub_email = getattr(getattr(obj, 'submitted_by', None), 'email', '') or ''
            if not sub_email:
                payload = getattr(obj, 'raw_payload', None) or {}
                for k in ('email', 'enumerator_email', 'submitter_email',
                          'your_email', 'respondent_email'):
                    v = str(payload.get(k, '') or '').strip()
                    if '@' in v:
                        sub_email = v
                        break
            if sub_email and sub_email not in recipients:
                recipients = recipients + [sub_email]
            # Three-way guard: only a FINAL decision emails anyone. A Bandhu
            # stage-1 manager approve sets MANAGER_APPROVED (not yet APPROVED) —
            # it must NOT fall through to the rejected branch and blast everyone
            # a false "rejected" notice. It silently awaits UNFPA stage-2.
            if recipients and obj.approval_status in ('APPROVED', 'REJECTED'):
                if obj.approval_status == 'APPROVED':
                    subj = f'[SIMPLE] ✓ {label} approved — {obj.organisation}'
                    body = (
                        f'A {label} submission for {obj.organisation} has been approved '
                        f'by {getattr(user, "full_name", "") or user.email}.'
                    )
                else:
                    # Resubmit link — for PHD models route to the new merged
                    # Service Log / Registration; for legacy partners we leave
                    # the link blank (their workflow predates this notifier).
                    resubmit = _program_resubmit_url(_MODEL_TO_SLUG.get(type(obj), ''), obj.organisation)
                    link_line = f'\nResubmit corrected entry: {resubmit}\n' if resubmit else ''
                    subj = f'[SIMPLE] ✗ {label} rejected — {obj.organisation}'
                    body = (
                        f'A {label} submission for {obj.organisation} was rejected '
                        f'by {getattr(user, "full_name", "") or user.email}.\n\n'
                        f'Reviewer note: {obj.rejected_reason or "No reason provided"}\n'
                        f'{link_line}\n'
                        f'Please open the form again, fix the flagged field, and submit '
                        f'a corrected entry. The rejected record is kept as the audit trail.'
                    )
                _send(subj, body, recipients)
        except Exception as exc:
            logger.warning('Per-model decision email failed: %s', exc)

        return Response({'status': obj.approval_status})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._approve_or_reject(request, pk, 'approve')

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._approve_or_reject(request, pk, 'reject')

    def perform_create(self, serializer):
        user = self.request.user
        # Force organisation to the writer's own org for every org-bound role
        # (manager, field_staff, focal). Only cross-org oversight roles
        # (developer/supervisor, and CIPRB org leads) may set it explicitly —
        # otherwise a non-oversight user could POST organisation=<other partner>
        # in the body (serializers use fields='__all__' and don't mark
        # organisation read-only) and forge a record under a foreign org.
        if user.can_see_all_orgs or user.can_read_other_orgs:
            serializer.save()
        else:
            serializer.save(organisation=user.organisation)


def _save_org_pinned(serializer, user):
    """Save, FORCING organisation to the writer's own org for org-bound roles so
    they can never create OR move a record under another partner. Only cross-org
    oversight roles (developer/supervisor, CIPRB org-leads) may set it explicitly.
    Mirrors OrgFilteredViewSet.perform_create; used by the reference/identity
    viewsets (Client, ServiceCenter) that don't inherit it."""
    if user.can_see_all_orgs or user.can_read_other_orgs:
        serializer.save()
    else:
        serializer.save(organisation=user.organisation)


# ─── Service Centres ───────────────────────────────────────────────────────────

class ServiceCenterViewSet(viewsets.ModelViewSet):
    # CanWriteOrgRecord (not bare IsAuthenticated): blocks focal/baseline writes;
    # perform_create/update pin organisation so a low-privilege or cross-org user
    # can't forge / move a reference centre under another partner.
    queryset = ServiceCenter.objects.all()
    serializer_class = ServiceCenterSerializer
    permission_classes = [CanWriteOrgRecord]

    def get_queryset(self):
        return _org_filter(ServiceCenter.objects.filter(is_active=True), self.request)

    def perform_create(self, serializer):
        _save_org_pinned(serializer, self.request.user)

    def perform_update(self, serializer):
        _save_org_pinned(serializer, self.request.user)


# ─── Clients ───────────────────────────────────────────────────────────────────

class ClientViewSet(viewsets.ModelViewSet):
    # Client rows feed the indicator/dashboard pipeline (default APPROVED), so the
    # write path MUST be org-pinned + write-gated — otherwise any org-bound user
    # could POST organisation=<other partner> and forge a live foreign-org client.
    queryset = Client.objects.select_related('center').all()
    serializer_class = ClientSerializer
    permission_classes = [CanWriteOrgRecord]

    def get_queryset(self):
        return _org_filter(Client.objects.select_related('center').all(), self.request)

    def perform_create(self, serializer):
        _save_org_pinned(serializer, self.request.user)

    def perform_update(self, serializer):
        _save_org_pinned(serializer, self.request.user)


# ─── Clinic ────────────────────────────────────────────────────────────────────

class ClinicVisitViewSet(OrgFilteredViewSet):
    queryset = ClinicVisit.objects.select_related('client', 'center', 'approved_by').all()
    serializer_class = ClinicVisitSerializer
    permission_classes = [CanWriteFieldRecord]  # Clinic visit is field-staff data

    def get_queryset(self):
        qs = ClinicVisit.objects.select_related('client', 'center', 'approved_by').all()
        qs = _org_filter(qs, self.request)
        approval = self.request.query_params.get('approval_status')
        if approval:
            qs = qs.filter(approval_status=approval)
        return qs.order_by('-visit_date')


class HIVSTITestResultViewSet(OrgFilteredViewSet):
    queryset = HIVSTITestResult.objects.select_related('client', 'center').all()
    serializer_class = HIVSTITestResultSerializer
    permission_classes = [CanWriteFieldRecord]


class ADRRecordViewSet(OrgFilteredViewSet):
    queryset = ADRRecord.objects.select_related('client', 'center').all()
    serializer_class = ADRRecordSerializer
    permission_classes = [CanWriteFieldRecord]


class AutoclaveLogViewSet(OrgFilteredViewSet):
    queryset = AutoclaveLog.objects.select_related('center').all()
    serializer_class = AutoclaveLogSerializer


class AntenatalCardViewSet(OrgFilteredViewSet):
    queryset = AntenatalCard.objects.select_related('client', 'center').all()
    serializer_class = AntenatalCardSerializer


# ─── Counselling ───────────────────────────────────────────────────────────────

class HTCCounsellingViewSet(OrgFilteredViewSet):
    queryset = HTCCounselling.objects.select_related('client', 'center').all()
    serializer_class = HTCCounsellingSerializer
    permission_classes = [CanWriteFieldRecord]  # Field-staff write; manager blocked


class IndividualCounsellingViewSet(OrgFilteredViewSet):
    queryset = IndividualCounselling.objects.select_related('client', 'center').all()
    serializer_class = IndividualCounsellingSerializer
    permission_classes = [CanWriteFieldRecord]


class MHScreeningViewSet(OrgFilteredViewSet):
    queryset = MHScreening.objects.select_related('client', 'center').all()
    serializer_class = MHScreeningSerializer
    permission_classes = [CanWriteFieldRecord]


# ─── GBV ───────────────────────────────────────────────────────────────────────

class GBVCaseViewSet(OrgFilteredViewSet):
    queryset = GBVCase.objects.select_related('center', 'approved_by').all()
    permission_classes = [CanWriteFieldRecord]  # GBV is field-staff data

    def get_serializer_class(self):
        user = self.request.user
        if user.role in ('developer', 'supervisor', 'org_lead') or getattr(user, 'is_gbv_officer', False):
            return GBVCaseDetailSerializer
        return GBVCaseSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        GBVAccessLog.objects.create(
            case=instance,
            user=request.user,
            action='VIEW',
            ip_address=request.META.get('REMOTE_ADDR', ''),
        )
        return super().retrieve(request, *args, **kwargs)


# ─── Outreach ──────────────────────────────────────────────────────────────────

class OutreachSessionViewSet(OrgFilteredViewSet):
    queryset = OutreachSession.objects.select_related('center').all()
    serializer_class = OutreachSessionSerializer
    permission_classes = [CanWriteOutreach]  # Manager-only write per handoff


class WellnessLogbookEntryViewSet(OrgFilteredViewSet):
    """F-01 Wellness Centre Service Logbook — approval detail (register table).
    Bandhu service record; carries no decrypted-PII columns, only client_id +
    raw_payload. Reviewed via the standard two-stage Bandhu flow."""
    queryset = WellnessLogbookEntry.objects.select_related('center').all()
    serializer_class = WellnessLogbookEntrySerializer
    permission_classes = [CanWriteFieldRecord]  # field-worker service data


class PHDCounsellingReportViewSet(OrgFilteredViewSet):
    """PHD monthly counselling summary — approval detail (register table).
    A self-reported aggregate; lands PENDING and a PHD manager approves it
    before its counts feed the dashboard. raw_payload retained for review."""
    queryset = PHDCounsellingReport.objects.select_related('center').all()
    serializer_class = PHDCounsellingReportSerializer
    permission_classes = [CanWriteFieldRecord]  # PHD counsellor data


class GroupEducationSessionViewSet(OrgFilteredViewSet):
    queryset = GroupEducationSession.objects.select_related('center').all()
    serializer_class = GroupEducationSessionSerializer
    permission_classes = [CanWriteOutreach]  # Community session — manager-only


# ─── IEC / SBCC materials ──────────────────────────────────────────────────────
#
# Feeds PHD 3.1a-d + Bandhu 4.1 / 4.3 indicators. CanWriteOutreach is the
# right permission class — IEC distribution is a community-facing activity
# the manager owns. Field staff get read-only via OrgFilterMixin filter.

class IECMaterialViewSet(OrgFilteredViewSet):
    queryset = IECMaterial.objects.select_related('center', 'partner').all()
    serializer_class = IECMaterialSerializer
    permission_classes = [CanWriteOutreach]

    def get_queryset(self):
        qs = super().get_queryset()
        material_type = self.request.query_params.get('material_type')
        if material_type:
            qs = qs.filter(material_type=material_type)
        return qs.order_by('-date_distributed', '-created_at')

    def perform_create(self, serializer):
        # Same org-forgery guard as OrgFilteredViewSet.perform_create — this
        # override must NOT reopen the hole: pin organisation for org-bound
        # roles, let only cross-org oversight set it explicitly.
        user = self.request.user
        if user.can_see_all_orgs or user.can_read_other_orgs:
            serializer.save(submitted_by=user)
        else:
            serializer.save(submitted_by=user, organisation=user.organisation)


# ─── Referrals ─────────────────────────────────────────────────────────────────

class ReferralViewSet(OrgFilteredViewSet):
    queryset = Referral.objects.select_related('client', 'center').all()
    serializer_class = ReferralSerializer

    @action(detail=True, methods=['patch'])
    def update_outcome(self, request, pk=None):
        """PATCH .../referrals/<pk>/update_outcome/ to update referral outcome."""
        obj = self.get_object()
        serializer = ReferralOutcomeSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(outcome_updated_by=request.user)
        return Response(serializer.data)


# ─── Supply ────────────────────────────────────────────────────────────────────

class StockEntryViewSet(OrgFilteredViewSet):
    queryset = StockEntry.objects.select_related('center').all()
    serializer_class = StockEntrySerializer

    def get_queryset(self):
        qs = StockEntry.objects.select_related('center').all()
        qs = _org_filter(qs, self.request)
        month = self.request.query_params.get('month')
        if month:
            qs = qs.filter(reporting_month=month)
        return qs


class TemperatureLogViewSet(OrgFilteredViewSet):
    queryset = TemperatureLog.objects.select_related('center').all()
    serializer_class = TemperatureLogSerializer


class SafetyHygieneKitViewSet(OrgFilteredViewSet):
    queryset = SafetyHygieneKit.objects.select_related('center').all()
    serializer_class = SafetyHygieneKitSerializer


class StoreRequisitionViewSet(OrgFilteredViewSet):
    queryset = StoreRequisition.objects.select_related('center').all()
    serializer_class = StoreRequisitionSerializer


# ─── Operations ────────────────────────────────────────────────────────────────

class TrainingEventViewSet(OrgFilteredViewSet):
    queryset = TrainingEvent.objects.select_related('center').all()
    serializer_class = TrainingEventSerializer


class CoordMeetingViewSet(OrgFilteredViewSet):
    queryset = CoordMeeting.objects.select_related('center').all()
    serializer_class = CoordMeetingSerializer


class MobileHealthCampViewSet(OrgFilteredViewSet):
    queryset = MobileHealthCamp.objects.select_related('center').all()
    serializer_class = MobileHealthCampSerializer
    permission_classes = [CanWriteOutreach]  # Mobile camp = community outreach


class VisitorRegisterViewSet(viewsets.ModelViewSet):
    queryset = VisitorRegister.objects.select_related('center').all()
    serializer_class = VisitorRegisterSerializer
    permission_classes = [CanWriteOrgRecord]

    def get_queryset(self):
        return _org_filter(VisitorRegister.objects.select_related('center').all(), self.request)


# ─── Aggregated Pending Approvals ──────────────────────────────────────────────

# Resubmit-link map per (model_type, partner). Points the field worker
# at the Enketo form that produced the rejected record so they can submit
# a corrected entry without hunting for the right link. PHD: Form 1 for
# Client registrations, Form 2 (Service Log) for every other PHD model.
_PHD_REG_URL  = 'https://ee.kobotoolbox.org/x/NesXOMsL'
_PHD_LOG_URL  = 'https://ee.kobotoolbox.org/x/o7GhleIk'


def _program_resubmit_url(model_type: str, organisation: str) -> str:
    if organisation != 'PHD':
        return ''
    if model_type == 'client_reg':
        return _PHD_REG_URL
    return _PHD_LOG_URL  # every PHD service/activity flows through Service Log


# Acronyms kept upper-cased when a snake_case slug or a model verbose_name is
# humanised for display — a plain .title() renders 'MPDSR' as 'Mpdsr', 'CIPRB'
# as 'Ciprb', 'HIV STI' as 'Hiv Sti', etc.
_LABEL_ACRONYMS = {
    'Hiv': 'HIV', 'Sti': 'STI', 'Hiv/Sti': 'HIV/STI', 'Mpdsr': 'MPDSR',
    'Adr': 'ADR', 'Htc': 'HTC', 'Mh': 'MH', 'Gbv': 'GBV', 'Anc': 'ANC',
    'Iec': 'IEC', 'Fsw': 'FSW', 'Mnm': 'MNM', 'Ciprb': 'CIPRB', 'Phd': 'PHD',
}


def _humanise_label(text: str) -> str:
    """Title-case a snake_case slug (or tidy a verbose_name) for display, keeping
    known acronyms upper-cased (MPDSR / HIV / STI / GBV / CIPRB / …)."""
    titled = text.replace('_', ' ').title()
    return ' '.join(_LABEL_ACRONYMS.get(w, w) for w in titled.split())


def _build_summary(obj, model_type: str) -> str:
    """Build a human-readable one-line summary for each model type."""
    try:
        if model_type == 'mpdsr_action':
            who = obj.creator_name or obj.submitted_by_kobo_user or '–'
            edit = (f" · edited by {obj.last_edited_by_name}"
                    if obj.last_edited_by_name and obj.last_edited_by_name != obj.creator_name
                    else "")
            activity = (obj.activity or '').strip()
            activity = ('⚠ awaiting plan record'
                        if activity == STUB_ACTIVITY_SENTINEL else activity[:50])
            # Status + completion% are the two fields an approver is actually
            # deciding on for an update submission — show them, and drop any
            # blank segment rather than rendering an empty ' ·  · '.
            parts = [obj.action_id, activity, obj.district,
                     obj.get_status_display(), f"{obj.completion_pct}%"]
            base = ' · '.join(p for p in parts if p)
            return f"{base} · created by {who}{edit}"
        if model_type == 'clinic_visit':
            parts = [f"Visit {obj.visit_date}"]
            if obj.hiv_screening_done:
                parts.append('HIV screen')
            if obj.sti_screening_done:
                parts.append('STI screen')
            if obj.condoms_distributed:
                parts.append(f'Condoms: {obj.condoms_distributed}')
            return ' · '.join(parts)
        if model_type == 'hiv_sti_result':
            return f"Test {obj.testing_date} · HIV: {obj.hiv_result} · Syphilis: {obj.syphilis_result}"
        if model_type == 'adr_record':
            return f"ADR {obj.report_date} · Effect: {'Yes' if obj.adverse_effect_present else 'No'}"
        if model_type == 'autoclave_log':
            return f"{obj.log_type.title()} log {obj.log_date}"
        if model_type == 'antenatal_card':
            return f"ANC Visit #{obj.anc_visit_number} · {obj.visit_date} · Trimester: {obj.trimester or '–'}"
        if model_type == 'htc_counselling':
            return f"HTC {obj.session_type} · {obj.session_date}"
        if model_type == 'individual_counselling':
            issues = [k.replace('issue_', '') for k in [
                'issue_sti', 'issue_psychosocial', 'issue_gbv', 'issue_drug_use', 'issue_fp'
            ] if getattr(obj, k, False)]
            return f"Counselling {obj.session_date}" + (f" · {', '.join(issues)}" if issues else '')
        if model_type == 'mh_screening':
            return f"{obj.screening_type.title()} screening {obj.screening_date} · {obj.severity_category or 'pending score'}"
        if model_type == 'gbv_case':
            types = [t for t, f in [('Sexual', 'gbv_sexual'), ('Physical', 'gbv_physical'),
                                      ('Economic', 'gbv_economic'), ('Psychological', 'gbv_psychological')]
                     if getattr(obj, f, False)]
            return f"GBV case {obj.incident_date}" + (f" · {', '.join(types)}" if types else '')
        if model_type == 'wellness_logbook':
            return f"F-01 logbook {obj.service_date} · client {obj.client_id or '–'}"
        if model_type == 'counselling_report':
            return f"Counselling report {obj.report_date} · {obj.total_count} sessions"
        if model_type == 'outreach_session':
            # individual_contacts is 0 for Bandhu (F-04 has no such field), so
            # only show the parts that carry a value — avoids a uniform, useless
            # "0 contacts · 0 condoms" on every Bandhu card.
            bits = []
            if getattr(obj, 'individual_contacts', 0):
                bits.append(f"{obj.individual_contacts} contacts")
            if getattr(obj, 'condoms_distributed_free', 0):
                bits.append(f"{obj.condoms_distributed_free} condoms")
            if getattr(obj, 'hiv_aids_sti_knowledge_sessions', 0):
                bits.append(f"{obj.hiv_aids_sti_knowledge_sessions} awareness")
            spot = (getattr(obj, 'spot_name', '') or '').strip()
            if spot:
                bits.append(spot)
            return f"Outreach {obj.session_date}" + (' · ' + ' · '.join(bits) if bits else '')
        if model_type == 'group_education':
            return f"Group session {obj.session_date} · {obj.topic[:40]} · {obj.participant_count} participants"
        if model_type == 'referral':
            # Defensive — `referred_to` and `outcome` are routinely blank on
            # PHD referrals (the field worker fills only "Referred for") and
            # used to render as the broken "Referral 2026-06-04 → · other ·
            # pending" string. Drop the missing pieces instead of the dot.
            parts = [f"Referral {obj.referral_date}"]
            if (obj.referred_to or '').strip():
                parts.append(f"→ {obj.referred_to[:40]}")
            if (obj.referral_reason or '').strip():
                parts.append(obj.referral_reason[:40])
            if (obj.referral_type or '').strip() and obj.referral_type != 'other':
                parts.append(obj.referral_type)
            return ' · '.join(parts)
        if model_type == 'phd_counselling':
            return (f"Counselling report {obj.report_date} · "
                    f"{obj.total_count} individual · {obj.group_mh_count} group MH")
        if model_type == 'safety_hygiene_kit':
            return f"Kit distribution {obj.distribution_date} · {obj.condom_count} condoms"
        if model_type == 'training_event':
            return f"{obj.event_type.title()} {obj.event_date} · {obj.participant_type} · {obj.total_participants} participants"
        if model_type == 'coord_meeting':
            return f"{obj.meeting_type} meeting {obj.meeting_date} · {obj.participant_count} attendees"
        if model_type == 'mobile_camp':
            return f"Mobile camp {obj.camp_date} · {obj.clients_served} clients · {obj.brothel_name or obj.center}"
        if model_type == 'client_reg':
            parts = [f"Client ID: {obj.client_id}", obj.name or '–']
            if obj.target_group_code:
                parts.append(obj.get_target_group_code_display())
            if obj.enrolled_date:
                parts.append(f"Enrolled: {obj.enrolled_date}")
            return ' · '.join(parts)
        # ── CIPRB single-stage forms ────────────────────────────────────────
        if model_type == 'fistula_case':
            parts = [f"Fistula — {obj.get_current_stage_display()}", obj.district]
            if (obj.name or '').strip():
                parts.append(obj.name + (f" ({obj.age})" if obj.age else ''))
            return ' · '.join(p for p in parts if p)
        if model_type == 'fistula_campaign':
            return (f"Fistula campaign {obj.campaign_date} · {obj.district} · "
                    f"{obj.households_visited} HH / {obj.population_covered} pop")
        if model_type == 'mpdsr_case':
            parts = [obj.sub_form_label or 'MPDSR review',
                     obj.get_death_type_display(), obj.district,
                     str(obj.date_of_death)]
            return ' · '.join(p for p in parts if p)
        if model_type == 'mpdsr_notification':
            parts = [obj.get_death_kind_display(), obj.district,
                     f"died {obj.date_of_death}"]
            if (obj.deceased_name or '').strip():
                parts.append(obj.deceased_name)
            return ' · '.join(p for p in parts if p)
        if model_type == 'near_miss_case':
            parts = ['Maternal near-miss', obj.district]
            if obj.woman_age:
                parts.append(f"age {obj.woman_age}")
            parts.append(str(obj.event_date))
            if (obj.cause_of_near_miss or '').strip():
                parts.append(obj.cause_of_near_miss)
            return ' · '.join(p for p in parts if p)
        if model_type == 'surgery_checklist':
            # Keep patient_name OUT of the queue summary (PII) — show the
            # operation, where, when, and the phase-completion state.
            phases = f"{obj.phases_complete_count}/3 phases"
            when = (obj.op_datetime.date().isoformat() if obj.op_datetime
                    else (str(obj.collection_date) if obj.collection_date else ''))
            parts = ['Safe Surgery', obj.operation_name,
                     obj.facility_name or obj.district, when, phases]
            return ' · '.join(p for p in parts if p)
        if model_type == 'nil_report':
            # Was falling through to a dateless "Nil report record" in the queue
            # (the date + centre + reason only existed in the UNFPA narrative).
            # Surface them in the summary every reviewer sees. (Fault F4.)
            where = obj.center.name if obj.center_id else 'all centres'
            parts = ['Nil report', where, str(obj.report_date)]
            if (obj.reason or '').strip():
                parts.append(obj.reason)
            return ' · '.join(p for p in parts if p)
    except Exception as exc:
        logger.warning('_build_summary(%s, pk=%s): %s', model_type, getattr(obj, 'id', '?'), exc)
    return f"{_humanise_label(model_type)} record"


_TG_LABELS = {'01': 'MSM', '02': 'MSW', '03': 'FSW', '04': 'EVA',
              '05': 'TG/Hijra', '06': 'Others'}


def _tg_phrase(obj) -> str:
    """Decode the target group from the raw payload (or client) to a label."""
    rp = getattr(obj, 'raw_payload', None) or {}
    for k in ('pr_tg', 'htc_tg', 'hv_tg', 'mc_tg', 'tg', 'target_group'):
        v = str(rp.get(k, '') or '').strip()
        if v:
            return _TG_LABELS.get(v, v)
    c = getattr(obj, 'client', None)
    if c is not None and getattr(c, 'target_group_code', None):
        try:
            return c.get_target_group_code_display()
        except Exception:
            return ''
    return ''


def _build_narrative(obj, model_type: str) -> str:
    """One-paragraph, plain-language description of the activity for the UNFPA
    final reviewer — so they understand what they are signing off, not just a
    field table. Falls back to the short summary for unmapped types."""
    try:
        tg = _tg_phrase(obj)
        who = f"a {tg} client" if tg else "a client"
        rp = getattr(obj, 'raw_payload', None) or {}
        if model_type == 'clinic_visit':
            bits = []
            screens = [s for s, f in [('HIV', 'hiv_screening_done'),
                                      ('STI', 'sti_screening_done'),
                                      ('TB', 'tb_screening_done')] if getattr(obj, f, False)]
            if screens:
                bits.append(f"{', '.join(screens)} screening was carried out")
            if getattr(obj, 'sti_counselling_provided', False):
                bits.append("STI counselling was provided")
            services = []
            if getattr(obj, 'condoms_distributed', 0):
                services.append(f"{obj.condoms_distributed} condoms")
            lub = str(rp.get('pr_lubricant', '') or '').strip()
            if lub and lub != '0':
                services.append(f"{lub} lubricants")
            if services:
                bits.append("distributed " + " and ".join(services))
            refs = [r for r, f in [('TB', 'referral_tb'), ('STI (KP)', 'referral_sti_kp'),
                                   ('general health', 'referral_general_health'),
                                   ('HIV testing', 'referral_hiv_testing'),
                                   ('mental health', 'referral_mental_health'),
                                   ('GBV', 'referral_gbv'), ('family planning', 'referral_fp')]
                    if getattr(obj, f, False)]
            if refs:
                bits.append("referred to " + ", ".join(refs))
            if (getattr(obj, 'treatment_provided', '') or '').strip():
                bits.append(f"treatment was given ({obj.treatment_provided.strip()})")
            body = "; ".join(bits) if bits else "no further services were recorded"
            fu = f" A follow-up is due on {obj.follow_up_due_date}." if getattr(obj, 'follow_up_due_date', None) else ""
            return f"On {obj.visit_date}, a clinical patient visit (F-05) was recorded for {who}: {body}.{fu}"
        if model_type == 'hiv_sti_result':
            return (f"On {obj.testing_date}, an HIV/STI test was recorded for {who} — "
                    f"HIV result {obj.hiv_result or 'not stated'}, syphilis {obj.syphilis_result or 'not stated'}.")
        if model_type == 'outreach_session':
            spot = (getattr(obj, 'spot_name', '') or '').strip()
            at = f" at {spot}" if spot else ""
            dist = []
            for lab, f in [('condom', 'condoms_distributed_free'),
                           ('lubricant', 'lubricants_distributed_free'),
                           ('awareness session', 'hiv_aids_sti_knowledge_sessions'),
                           ('IEC material', 'iec_bcc_materials_distributed')]:
                v = getattr(obj, f, 0) or 0
                if v:
                    dist.append(f"{v} {lab}" + ("s" if v != 1 else ""))
            refs = sum(getattr(obj, f, 0) or 0 for f in (
                'referral_mental_health', 'referral_gbv', 'referral_legal_services',
                'referral_htc_hts', 'referral_other'))
            parts = []
            if getattr(obj, 'individual_contacts', 0):
                parts.append(f"reached {obj.individual_contacts} individual contact(s)")
            if dist:
                parts.append("distributed " + ", ".join(dist))
            if refs:
                parts.append(f"made {refs} referral" + ("s" if refs != 1 else ""))
            body = "; ".join(parts) if parts else "recorded no distributions or referrals"
            return f"On {obj.session_date}, an outreach session{at} {body}."
        if model_type == 'wellness_logbook':
            tg_lab = _TG_LABELS.get((getattr(obj, 'tg_code', '') or '').strip(), '')
            who = f"a {tg_lab} client" if tg_lab else "a client"
            ticks = [lab for lab, f in [
                ('HIV test', 'htc'), ('STI screening', 'sti_screening'),
                ('clinical care', 'clinical'), ('GBV support', 'gbv'),
                ('mental-health support', 'mental_health'), ('counselling', 'counseling'),
                ('legal support', 'legal'), ('recreation', 'recreation'),
                ('group education', 'group_edu'),
            ] if getattr(obj, f, False)]
            counts = []
            for lab, f in [('condom', 'condom'), ('condom demo', 'condom_demo'),
                           ('lubricant', 'lubricant'), ('awareness session', 'awareness'),
                           ('IEC material', 'iec')]:
                v = getattr(obj, f, 0) or 0
                if v:
                    counts.append(f"{v} {lab}" + ("s" if v != 1 else ""))
            given = ticks + counts
            where = obj.center.name if obj.center_id else 'the wellness centre'
            body = ("received " + ", ".join(given)) if given else "no services were recorded"
            refs = (getattr(obj, 'referral_codes', '') or '').strip()
            if refs:
                body += f"; referred (code {refs})"
            cid = obj.client_id or '–'
            return f"On {obj.service_date}, {who} (ID {cid}) at {where} {body}."
        if model_type == 'referral':
            dest = (getattr(obj, 'referred_to', '') or '').strip() or 'a service'
            reason = (getattr(obj, 'referral_reason', '') or '').strip()
            return f"On {obj.referral_date}, {who} was referred to {dest}" + (f" for {reason}" if reason else "") + "."
        if model_type == 'gbv_case':
            types = [t for t, f in [('sexual', 'gbv_sexual'), ('physical', 'gbv_physical'),
                                    ('economic', 'gbv_economic'), ('psychological', 'gbv_psychological')]
                     if getattr(obj, f, False)]
            return (f"On {obj.incident_date}, a GBV case was recorded for {who}"
                    + (f" ({', '.join(types)} violence)" if types else "") + ".")
        if model_type == 'mobile_camp':
            return f"On {obj.camp_date}, a mobile health camp served {obj.clients_served} client(s)."
        if model_type == 'nil_report':
            where = obj.center.name if obj.center_id else 'all centres'
            return f"No activity was reported for {where} on {obj.report_date}. Reason given: {obj.reason}."
    except Exception as exc:
        logger.warning('_build_narrative(%s): %s', model_type, exc)
    return _build_summary(obj, model_type)


def _pending_for_model(queryset, model_type: str, org_filter_org=None,
                       statuses=('PENDING',), reviewed_only=False,
                       count_only=False):
    """Return approval dicts for a queryset at the given approval stage(s).

    statuses lets the queue show stage-1 (PENDING) and/or stage-2
    (MANAGER_APPROVED) items depending on who is looking — see
    PendingApprovalsView.get for the per-role lanes.

    reviewed_only (for the Reviewed tab) keeps only records a PERSON actually
    decided — approved_by set, or rejected — so auto-approved records (e.g. FSW
    registrations, which never go through a manual review) don't flood the
    audit trail with decisions nobody made."""
    # MPDSRAction (and any future centre-less model) has no `center` FK — only
    # select_related it when the model has it, else DRF raises FieldError.
    qs = queryset.filter(approval_status__in=list(statuses))
    _sel = ['approved_by']
    try:
        qs.model._meta.get_field('center')
        _sel.insert(0, 'center')
    except Exception:
        pass
    qs = qs.select_related(*_sel)
    if org_filter_org:
        qs = qs.filter(organisation=org_filter_org)
    if reviewed_only:
        from django.db.models import Q
        qs = qs.filter(Q(approved_by__isnull=False) | Q(approval_status='REJECTED'))
    # True backlog size BEFORE the display cap, so the queue can report an
    # honest total (and flag truncation) even when more than `_CAP` rows of a
    # single model are pending. (Fault F1: previously `total` was the already-
    # truncated row count, silently undercounting the backlog.)
    _CAP = 200
    full_count = qs.count()
    # TRUE per-organisation backlog (before the display cap) so the queue's
    # partner tabs (Bandhu / PHD / CIPRB) count the real pending total, not the
    # capped page. Without this the tab badge was computed from the returned
    # rows: approving one just back-filled a hidden row and the number never
    # moved ("317 won't go down even after I approve"). (Fault F1 follow-up.)
    from django.db.models import Count as _Count
    counts_by_org = {
        row['organisation']: row['n']
        for row in qs.values('organisation').annotate(n=_Count('id'))
    }
    # The badge caller wants the numbers above and nothing else. Both counts are
    # already computed, so stop here rather than fetching up to _CAP rows per
    # model and building a summary + narrative for each.
    if count_only:
        return [], full_count, counts_by_org
    results = []
    for obj in qs.order_by('created_at')[:_CAP]:
        results.append({
            'id': str(obj.id),
            'model_type': model_type,
            'model_label': _humanise_label(model_type),
            'endpoint': model_type.replace('_', '-') + 's',
            'organisation': obj.organisation,
            'approval_status': obj.approval_status,
            # Two-stage flag + which gate this item is waiting on, so the UI
            # can split the Manager queue from the UNFPA queue.
            'two_stage': obj.organisation == 'Bandhu',
            'stage': ('unfpa' if obj.approval_status == 'MANAGER_APPROVED'
                      else 'manager'),
            'manager_approved_at': (obj.manager_approved_at.isoformat()
                                    if getattr(obj, 'manager_approved_at', None) else None),
            # getattr: browser-entered models (StockEntry) have no Kobo user.
            'submitted_by': getattr(obj, 'submitted_by_kobo_user', '') or '–',
            'center_name': (getattr(obj, 'center', None).name
                            if getattr(obj, 'center', None)
                            else getattr(obj, 'district', '') or '–'),
            'center_code': (getattr(obj, 'center', None).code
                            if getattr(obj, 'center', None) else ''),
            # Per-creator surfacing for the MPDSR action gate (blank for other models).
            'created_by_name': getattr(obj, 'creator_name', '') or '',
            'edited_by_name': getattr(obj, 'last_edited_by_name', '') or '',
            'created_at': obj.created_at.isoformat(),
            'summary': _build_summary(obj, model_type),
            # One-paragraph plain-language narrative — the frontend shows it
            # ONLY to UNFPA (the stage-2 reviewer), alongside the field table.
            'narrative': _build_narrative(obj, model_type),
            'latitude': float(getattr(obj, 'latitude', None)) if getattr(obj, 'latitude', None) else None,
            'longitude': float(getattr(obj, 'longitude', None)) if getattr(obj, 'longitude', None) else None,
            'kobo_submission_id': getattr(obj, 'kobo_submission_id', '') or '',
        })
    return results, full_count, counts_by_org


# endpoint → (queryset, model_type)
class CIPRBFistulaCaseViewSet(OrgFilteredViewSet):
    """CIPRB Fistula cases — detail + approve/reject for the manager queue.
    Single-stage (Tanjina / Setu approve CIPRB). These rows carry DECRYPTED
    survivor PII (name/husband/phone) + raw_payload, so reads are gated by
    CanAccessFistulaCases — CIPRB-scoped + monitoring-org read-only only; PHD/
    Bandhu staff and CIPRB focal/baseline/field_staff are 403 (audit FIX C1,
    carried to this viewset)."""
    permission_classes = [CanAccessFistulaCases]
    queryset = CIPRBFistulaCase.objects.select_related('approved_by').all()
    serializer_class = CIPRBFistulaCaseSerializer


class FistulaCampaignViewSet(OrgFilteredViewSet):
    """CIPRB Fistula Campaign (daily CHW activity) — detail + approve/reject for
    the manager queue. Single-stage CIPRB (Tanjina / Setu). These are aggregate
    daily reach reports (no row-level patient PII), but they carry raw_payload
    and feed the CIPRB dashboard, so reads stay gated by CanAccessFistulaCases —
    the same CIPRB-scoped gate as CIPRBFistulaCase."""
    permission_classes = [CanAccessFistulaCases]
    queryset = FistulaCampaign.objects.select_related('approved_by').all()
    serializer_class = FistulaCampaignApprovalSerializer


class MPDSRCaseApprovalViewSet(OrgFilteredViewSet):
    """MPDSR review cases — detail + approve/reject for the manager queue
    (single-stage CIPRB). Distinct from mpdsr.MPDSRCaseViewSet (the post-approval
    Tracker); this serves the /programs approval detail endpoint. Gated by
    CanAccessMPDSR — carries case PII + raw_payload."""
    permission_classes = [CanAccessMPDSR]
    queryset = MPDSRCase.objects.select_related('approved_by', 'submission').all()
    serializer_class = MPDSRCaseApprovalSerializer


class MPDSRDeathNotificationViewSet(OrgFilteredViewSet):
    """MPDSR death-notification slips — detail + approve/reject (single-stage).
    Carries deceased_name/address + reporter PII; gated by CanAccessMPDSR."""
    permission_classes = [CanAccessMPDSR]
    queryset = MPDSRDeathNotification.objects.select_related('approved_by').all()
    serializer_class = MPDSRDeathNotificationApprovalSerializer


class MaternalNearMissViewSet(OrgFilteredViewSet):
    """Maternal near-miss audits — detail + approve/reject (single-stage).
    Carries woman_name + raw_payload; gated by CanAccessMPDSR."""
    permission_classes = [CanAccessMPDSR]
    queryset = MaternalNearMissCase.objects.select_related('approved_by').all()
    serializer_class = MaternalNearMissApprovalSerializer


class SafeSurgeryChecklistViewSet(OrgFilteredViewSet):
    """Safe Surgery Checklists (CIPRB-11) — detail + approve/reject (single-stage
    CIPRB: Tanjina / Setu). Carries decrypted patient_name + raw_payload, so the
    approval drawer reads are gated by CanAccessMPDSR — the CIPRB-scoped PII gate
    used for the other case-level CIPRB surveillance records."""
    permission_classes = [CanAccessMPDSR]
    queryset = SurgeryChecklist.objects.select_related('approved_by').all()
    serializer_class = SafeSurgeryApprovalSerializer


class MPDSRActionViewSet(OrgFilteredViewSet):
    """CIPRB-10 MPDSR Action-Plan rows — detail + approve/reject for the queue
    (single-stage CIPRB: Tanjina / Setu). District-level programme actions, NOT
    patient PII, so gated by CanApproveCIPRBAction (approval capability + CIPRB
    scope) rather than CanAccessMPDSR (the survivor/death-PII gate)."""
    permission_classes = [CanApproveCIPRBAction]
    queryset = MPDSRAction.objects.select_related('approved_by').all()
    serializer_class = MPDSRActionSerializer


_APPROVAL_MODELS = [
    ('client_reg',           lambda: Client.objects),
    ('clinic_visit',         lambda: ClinicVisit.objects),
    ('hiv_sti_result',       lambda: HIVSTITestResult.objects),
    ('adr_record',           lambda: ADRRecord.objects),
    ('autoclave_log',        lambda: AutoclaveLog.objects),
    ('antenatal_card',       lambda: AntenatalCard.objects),
    ('htc_counselling',      lambda: HTCCounselling.objects),
    ('individual_counselling', lambda: IndividualCounselling.objects),
    ('mh_screening',         lambda: MHScreening.objects),
    ('gbv_case',             lambda: GBVCase.objects),
    ('outreach_session',     lambda: OutreachSession.objects),
    ('wellness_logbook',     lambda: WellnessLogbookEntry.objects),
    ('group_education',      lambda: GroupEducationSession.objects),
    ('referral',             lambda: Referral.objects),
    ('safety_hygiene_kit',   lambda: SafetyHygieneKit.objects),
    ('training_event',       lambda: TrainingEvent.objects),
    ('coord_meeting',        lambda: CoordMeeting.objects),
    ('mobile_camp',          lambda: MobileHealthCamp.objects),
    ('nil_report',           lambda: NilReport.objects),
    # Monthly commodity stock (browser-entered). Was counted by the
    # dashboard's pending banner but absent from this registry, so 51 PHD
    # entries sat unapprovable and SL5a-e (condoms/kits, APPROVED-only)
    # stayed at zero while the data existed (found 2026-08-14).
    ('stock_entry',          lambda: StockEntry.objects),
    # Same latent trap as stock_entry, sealed preemptively 2026-08-14:
    # both default to PENDING and are created by webhook handlers, so
    # the first field submission would have been counted-but-invisible.
    ('iec_material',         lambda: IECMaterial.objects),
    ('gbv_corner_record',    lambda: GBVCornerRecord.objects),
    ('counselling_report',   lambda: PHDCounsellingReport.objects),
    ('fistula_case',         lambda: CIPRBFistulaCase.objects),
    ('fistula_campaign',     lambda: FistulaCampaign.objects),
    ('mpdsr_case',           lambda: MPDSRCase.objects),
    ('mpdsr_notification',   lambda: MPDSRDeathNotification.objects),
    ('near_miss_case',       lambda: MaternalNearMissCase.objects),
    ('surgery_checklist',    lambda: SurgeryChecklist.objects),
    # Exclude '[awaiting plan record]' stubs — placeholders left by an
    # out-of-order update, not real actions an approver should ever see.
    ('mpdsr_action',         lambda: MPDSRAction.objects.exclude(activity=STUB_ACTIVITY_SENTINEL)),
]

# Reverse map model class → slug, for code paths that hold a model INSTANCE but
# not its slug (e.g. the per-model viewset reject-email resubmit link).
_MODEL_TO_SLUG = {qs_fn().model: mt for mt, qs_fn in _APPROVAL_MODELS}

# Fix endpoint slugs for DRF router (plural URLs)
_ENDPOINT_OVERRIDES = {
    'stock_entry': 'stock-entries',
    'iec_material': 'iec-materials',
    'client_reg': 'clients',
    'clinic_visit': 'clinic-visits',
    'hiv_sti_result': 'hiv-sti-results',
    'adr_record': 'adr-records',
    'autoclave_log': 'autoclave-logs',
    'antenatal_card': 'antenatal-cards',
    'htc_counselling': 'htc-counselling',
    'individual_counselling': 'individual-counselling',
    'mh_screening': 'mh-screening',
    'gbv_case': 'gbv-cases',
    'outreach_session': 'outreach-sessions',
    'wellness_logbook': 'wellness-logbook',
    'counselling_report': 'counselling-reports',
    'group_education': 'group-education',
    'referral': 'referrals',
    'safety_hygiene_kit': 'hygiene-kits',
    'training_event': 'training-events',
    'coord_meeting': 'coord-meetings',
    'mobile_camp': 'mobile-camps',
    'nil_report': 'nil-reports',
    'fistula_case': 'fistula-cases',
    'fistula_campaign': 'fistula-campaigns',
    'mpdsr_case': 'mpdsr-cases',
    'mpdsr_notification': 'mpdsr-notifications',
    'near_miss_case': 'near-miss-cases',
    'surgery_checklist': 'surgery-checklists',
    'mpdsr_action': 'mpdsr-actions',
}


class PendingApprovalsView(views.APIView):
    """
    GET  /api/programs/pending-approvals/
    Returns all pending programs submissions across all model types.
    Org-filtered per user role.

    POST /api/programs/pending-approvals/
    Body: { id, model_type, action: "approve"|"reject", reason: "" }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        org = user.organisation
        urole = getattr(user, 'role', '')
        is_super = (urole == 'developer') or (bool(getattr(user, 'can_see_all_orgs', False)) and org != 'UNFPA')
        is_unfpa = (org == 'UNFPA') and urole != 'developer'

        # Per-role review lanes (two-stage Bandhu flow):
        #   UNFPA  → stage-2 queue: Bandhu items at MANAGER_APPROVED only.
        #   super  → everything actionable: all PENDING + Bandhu MANAGER_APPROVED.
        #   Bandhu manager → stage-1: own-org PENDING.
        #   PHD/CIPRB manager/org_lead → own-org PENDING (single stage).
        # ?status=reviewed → the final-decision history (APPROVED/REJECTED) for
        # this user's org scope, so the Approvals "Reviewed" tab surfaces the
        # programs-model audit trail (registrations, clinic visits, referrals,
        # etc.) — not just legacy KoboSubmissions, which left the tab empty even
        # after dozens of decisions.
        review_mode = request.query_params.get('status', '') == 'reviewed'
        REVIEWED = ('APPROVED', 'REJECTED')

        # ?count_only=1 → the counts, without the rows. The Spine badge polls
        # this endpoint every 30s on every page for every signed-in user and
        # reads one field (`total`), but was being served the whole queue: ~86 KB
        # an answer, 57% of measured HTTP egress and the largest single line on
        # the Railway bill. The counts come from queries that run either way.
        count_only = (request.query_params.get('count_only', '').strip().lower()
                      in ('1', 'true', 'yes', 'on'))

        def lane(qs, model_type):
            if review_mode:
                scope = None if is_super else ('Bandhu' if is_unfpa else org)
                return _pending_for_model(qs, model_type, scope,
                                          statuses=REVIEWED, reviewed_only=True,
                                          count_only=count_only)
            if is_unfpa:
                return _pending_for_model(qs, model_type, 'Bandhu',
                                          statuses=('MANAGER_APPROVED',),
                                          count_only=count_only)
            if is_super:
                # Stage-1 / single-stage only. A super can no longer finalise a
                # Bandhu MANAGER_APPROVED item (that is UNFPA-only), so it must
                # not sit in their action queue as an un-actionable row.
                return _pending_for_model(qs, model_type, None,
                                          statuses=('PENDING',),
                                          count_only=count_only)
            return _pending_for_model(qs, model_type, org, statuses=('PENDING',),
                                      count_only=count_only)

        all_pending = []
        grand_total = 0
        full_counts_by_org = {}   # TRUE pre-cap backlog per partner (drives tabs)
        full_counts_by_type = {}  # TRUE pre-cap backlog per model (count_only)
        for model_type, qs_fn in _APPROVAL_MODELS:
            items, full_count, counts_by_org = lane(qs_fn(), model_type)
            grand_total += full_count
            if full_count:
                full_counts_by_type[model_type] = (
                    full_counts_by_type.get(model_type, 0) + full_count)
            for _org, _n in counts_by_org.items():
                full_counts_by_org[_org] = full_counts_by_org.get(_org, 0) + _n
            for item in items:
                item['endpoint'] = _ENDPOINT_OVERRIDES.get(model_type, model_type + 's')
            all_pending.extend(items)

        if review_mode:
            # Newest decision first; cap so the history stays bounded as it grows.
            all_pending.sort(key=lambda x: x['created_at'], reverse=True)
            all_pending = all_pending[:100]
        else:
            # Oldest first — work the queue FIFO.
            all_pending.sort(key=lambda x: x['created_at'])

        # Summary counts by model_type (over the rows actually returned). In
        # count_only mode there are no rows, so report the TRUE pre-cap backlog
        # per model instead of an empty dict.
        if count_only:
            counts = full_counts_by_type
        else:
            counts = {}
            for item in all_pending:
                counts[item['model_type']] = counts.get(item['model_type'], 0) + 1

        # `total` is the TRUE backlog (pre-cap); `returned` is how many rows this
        # response actually carries. `truncated` tells the UI to show "showing N
        # of M" instead of silently implying the queue is fully drained. (F1.)
        # `count_only` says the rows were dropped on purpose, so an empty
        # `items` can never be read as a drained queue either.
        return Response({
            'total': grand_total,
            'returned': len(all_pending),
            'truncated': grand_total > len(all_pending),
            'count_only': count_only,
            'counts_by_type': counts,
            # TRUE per-partner backlog (pre-cap). The frontend tabs use this so
            # the Bandhu/PHD/CIPRB badge reflects the real pending count and
            # drops on every approval, instead of counting the capped page.
            'counts_by_org': full_counts_by_org,
            'items': all_pending,
        })

    def post(self, request):
        """Approve, reject or delete a single pending item."""
        pk = request.data.get('id')
        model_type = request.data.get('model_type')
        action_type = request.data.get('action')  # approve | reject | delete
        reason = request.data.get('reason', '')

        if not all([pk, model_type, action_type]):
            return Response({'detail': 'id, model_type, and action are required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Find the model manager
        model_mgr = None
        for mt, qs_fn in _APPROVAL_MODELS:
            if mt == model_type:
                model_mgr = qs_fn()
                break

        if model_mgr is None:
            return Response({'detail': f'Unknown model_type: {model_type}'}, status=status.HTTP_400_BAD_REQUEST)

        if action_type == 'delete':
            try:
                obj = model_mgr.get(id=pk)
            except Exception:
                return Response({'detail': 'Record not found.'},
                                status=status.HTTP_404_NOT_FOUND)
            err = _delete_record(obj, request.user, reason)
            if err is not None:
                return err
            return Response({'detail': 'Record deleted.', 'deleted': True})

        with _tx.atomic():
            try:
                obj = model_mgr.select_for_update().get(id=pk)
            except Exception:
                return Response({'detail': 'Record not found.'}, status=status.HTTP_404_NOT_FOUND)

            user = request.user
            err = _apply_decision(obj, user, action_type, reason)
            if err is not None:
                return err
            obj.save()

        # Telegram — notify org chat of approval/rejection
        try:
            from .webhook import _FORM_LABELS
            # Reverse-look up form label from model_type
            _model_to_form = {
                'client_reg': 'spondon_client_reg_v1',
                'clinic_visit': 'spondon_clinic_visit_v1',
                'hiv_sti_result': 'spondon_hiv_sti_test_v1',
                'adr_record': 'spondon_adr_record_v1',
                'autoclave_log': 'spondon_autoclave_log_v1',
                'antenatal_card': 'spondon_antenatal_card_v1',
                'htc_counselling': 'spondon_htc_counsel_v1',
                'individual_counselling': 'spondon_counselling_v1',
                'mh_screening': 'spondon_mh_screening_v1',
                'gbv_case': 'spondon_gbv_case_v1',
                'outreach_session': 'spondon_outreach_v1',
                'wellness_logbook': 'bandhu_service_log_v1',
                'counselling_report': 'phd_service_log_v1',
                'group_education': 'spondon_group_edu_v1',
                'referral': 'spondon_referral_v1',
                'safety_hygiene_kit': 'spondon_hygiene_kit_v1',
                'training_event': 'spondon_training_event_v1',
                'coord_meeting': 'spondon_coord_meeting_v1',
                'mobile_camp': 'spondon_mobile_camp_v1',
            }
            form_key = _model_to_form.get(model_type, '')
            form_label = _FORM_LABELS.get(form_key, _humanise_label(model_type))
            reviewer_name = getattr(user, 'full_name', None) or user.email
            # Only announce a TERMINAL decision to the org chat. A Bandhu
            # stage-1 manager-approval (MANAGER_APPROVED) is still awaiting
            # UNFPA, so we must not yet tell the field chat it is "approved".
            if obj.approval_status in ('APPROVED', 'REJECTED'):
                _send_approval_telegram(
                    org=obj.organisation,
                    form_label=form_label,
                    reviewer_name=reviewer_name,
                    approved=(obj.approval_status == 'APPROVED'),
                    reason=reason,
                )
        except Exception as exc:
            logger.error('Telegram notification failed after approval: %s', exc)

        return Response({'status': obj.approval_status, 'id': str(obj.id)})


class NilReportView(views.APIView):
    """
    GET  /api/programs/nil-reports/   — list nil-reports the user can see
                                        (own org; super sees all).
    POST /api/programs/nil-reports/   — a Bandhu manager logs a "no reporting
                                        today" entry { center_id, report_date,
                                        reason }. It is created already at the
                                        manager gate (MANAGER_APPROVED) and then
                                        flows to the UNFPA approval queue.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        qs = NilReport.objects.select_related('center', 'approved_by', 'manager_approved_by')
        if not getattr(user, 'can_see_all_orgs', False):
            qs = qs.filter(organisation=user.organisation)
        out = []
        for n in qs.order_by('-report_date', '-created_at')[:300]:
            out.append({
                'id': str(n.id),
                'organisation': n.organisation,
                'center_name': n.center.name if n.center_id else 'All centres',
                'center_code': n.center.code if n.center_id else '',
                'report_date': n.report_date.isoformat(),
                'reason': n.reason,
                'approval_status': n.approval_status,
                'created_at': n.created_at.isoformat(),
            })
        return Response({'count': len(out), 'items': out})

    # Orgs allowed to log a nil-report — the field-collecting partners only.
    # Bandhu is two-stage (manager logs → awaiting UNFPA); PHD is single-stage.
    # CIPRB (monitoring) and UNFPA (oversight) do not file zero-day returns.
    NIL_ALLOWED_ORGS = ('Bandhu', 'PHD')

    def post(self, request):
        user = request.user
        if not user.can_approve_submissions:
            return Response({'detail': 'Only managers can log nil-reports.'},
                            status=status.HTTP_403_FORBIDDEN)

        # Org is derived STRICTLY from the user for everyone except oversight
        # super-admins (developer/supervisor). A single-org manager can never
        # write another team's nil-report — any client-supplied organisation is
        # ignored for them. This is the org-isolation boundary.
        if getattr(user, 'can_see_all_orgs', False):
            org = (request.data.get('organisation') or user.organisation or 'Bandhu')
            if org not in self.NIL_ALLOWED_ORGS:
                return Response({'detail': f'organisation must be one of {self.NIL_ALLOWED_ORGS}.'},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            org = user.organisation
            if org not in self.NIL_ALLOWED_ORGS:
                return Response({'detail': 'Your organisation cannot log nil-reports.'},
                                status=status.HTTP_403_FORBIDDEN)

        center_id = request.data.get('center_id')
        report_date = request.data.get('report_date')
        reason = (request.data.get('reason') or '').strip()
        if not report_date or not reason:
            return Response({'detail': 'report_date and reason are required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Resolve the centre WITHIN the report's org so a manager cannot
        # attribute a nil-report to another team's centre (cross-org integrity).
        center = None
        if center_id:
            # Match on CODE first — the form always sends the centre code. Only
            # try the UUID primary key when center_id actually parses as a UUID:
            # comparing a code like 'BND-DIC-01' against the UUID id column
            # raises ValidationError, which DRF surfaces as an uncaught 500.
            center = ServiceCenter.objects.filter(organisation=org, code=center_id).first()
            if center is None:
                try:
                    _uuid.UUID(str(center_id))
                except (ValueError, TypeError, AttributeError):
                    pass
                else:
                    center = ServiceCenter.objects.filter(organisation=org, id=center_id).first()
            if center is None:
                return Response({'detail': 'Centre not found for your organisation.'},
                                status=status.HTTP_400_BAD_REQUEST)

        # Two-stage (Bandhu) → created at the manager gate, awaiting UNFPA.
        # Single-stage (PHD/CIPRB) → recorded as APPROVED immediately.
        two_stage = (org == 'Bandhu')
        now = timezone.now()

        # Idempotent on (organisation, centre, date) — but a re-POST must NEVER
        # downgrade a record that already passed (or is awaiting) its gate, nor
        # rewrite its audit FKs. So we get_or_create and guard the update path.
        obj, created = NilReport.objects.get_or_create(
            organisation=org, center=center, report_date=report_date,
            defaults={
                'reason': reason,
                'submitted_by': user,
                'manager_approved_by': user,
                'manager_approved_at': now,
                'approval_status': 'MANAGER_APPROVED' if two_stage else 'APPROVED',
                **({} if two_stage else {'approved_by': user, 'approved_at': now}),
            },
        )
        if not created:
            if obj.approval_status in ('MANAGER_APPROVED', 'APPROVED'):
                return Response(
                    {'detail': 'A nil-report for this centre and date already exists.'},
                    status=status.HTTP_409_CONFLICT)
            # Re-logging a previously rejected/pending entry — re-arm it.
            obj.reason = reason
            obj.submitted_by = user
            obj.manager_approved_by = user
            obj.manager_approved_at = now
            obj.rejected_reason = ''
            if two_stage:
                obj.approval_status = 'MANAGER_APPROVED'
            else:
                obj.approval_status = 'APPROVED'
                obj.approved_by = user
                obj.approved_at = now
            obj.save()

        return Response(
            {'id': str(obj.id), 'created': created, 'status': obj.approval_status},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request):
        """Remove a nil-report (?id=). Own org only (or oversight). A Bandhu
        record UNFPA has already APPROVED is immutable to a stage-1 manager —
        only oversight (developer/supervisor/UNFPA) may delete a finalised,
        UNFPA-signed record, so a stage-1 actor can't erase a stage-2 decision.
        PHD/CIPRB records are single-stage, so their own manager may delete them.
        """
        user = request.user
        pk = request.query_params.get('id') or request.data.get('id')
        if not pk:
            return Response({'detail': 'id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        obj = NilReport.objects.filter(id=pk).first()
        if not obj:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        is_oversight = (getattr(user, 'can_see_all_orgs', False)
                        or user.organisation == 'UNFPA')
        if not (is_oversight or obj.organisation == user.organisation):
            return Response({'detail': 'Not authorised.'}, status=status.HTTP_403_FORBIDDEN)
        if (not is_oversight and obj.organisation == 'Bandhu'
                and obj.approval_status == 'APPROVED'):
            return Response(
                {'detail': 'This nil-report has been approved by UNFPA and cannot be deleted here.'},
                status=status.HTTP_403_FORBIDDEN)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
