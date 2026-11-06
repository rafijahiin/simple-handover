"""
DRF serializers for the programs app.
All write operations validate organisation matches the authenticated user's org
(enforced in the views — serializers stay lean).
"""
from rest_framework import serializers
from .models import (
    ServiceCenter, Client,
    ClinicVisit, HIVSTITestResult, ADRRecord, AutoclaveLog, AntenatalCard,
    HTCCounselling, IndividualCounselling, MHScreening,
    GBVCase,
    IECMaterial,
    OutreachSession, GroupEducationSession, WellnessLogbookEntry,
    Referral,
    StockEntry, TemperatureLog, SafetyHygieneKit, StoreRequisition,
    TrainingEvent, CoordMeeting, MobileHealthCamp, VisitorRegister,
    PHDCounsellingReport,
)
from fistula.ciprb_models import CIPRBFistulaCase
from fistula.models import FistulaCampaign
from mpdsr.models import MPDSRCase, MPDSRAction
from mpdsr.ciprb_models import (MPDSRDeathNotification, MaternalNearMissCase,
                                SurgeryChecklist)


class CIPRBFistulaCaseSerializer(serializers.ModelSerializer):
    """Detail serializer for the CIPRB Fistula approval queue. Exposes
    raw_payload (drives the manager 'What was submitted' readout) and the full
    row; the approval columns are read-only (set via approve/reject)."""
    class Meta:
        model = CIPRBFistulaCase
        fields = '__all__'
        read_only_fields = [
            'id', 'approval_status', 'approved_by', 'approved_at',
            'rejected_reason', 'kobo_submission_id', 'submitted_by_kobo_user',
            'created_at', 'updated_at',
        ]


class FistulaCampaignApprovalSerializer(serializers.ModelSerializer):
    """Detail serializer for the Fistula Campaign (daily CHW activity) approval
    queue. Exposes raw_payload for the manager 'What was submitted' readout; the
    approval columns are read-only (set via approve/reject)."""
    class Meta:
        model = FistulaCampaign
        fields = '__all__'
        read_only_fields = [
            'id', 'approval_status', 'approved_by', 'approved_at',
            'rejected_reason', 'kobo_submission_id', 'submitted_by_kobo_user',
            'case_hash', 'created_at', 'updated_at',
        ]


class MPDSRCaseApprovalSerializer(serializers.ModelSerializer):
    """Detail serializer for the MPDSR-case approval queue. MPDSRCase keeps its
    raw Kobo answers on the linked submission (no local raw_payload), so surface
    them as raw_payload for the manager 'What was submitted' readout."""
    raw_payload = serializers.SerializerMethodField()

    class Meta:
        model = MPDSRCase
        fields = '__all__'
        read_only_fields = [
            'id', 'approval_status', 'approved_by', 'approved_at',
            'rejected_reason', 'kobo_submission_id', 'submitted_by_kobo_user',
            'organisation', 'created_at', 'updated_at',
        ]

    def get_raw_payload(self, obj):
        # Priority: the case's own stored Kobo answers (verbatim-form path),
        # then the legacy linked submission, then a summary synthesised from
        # the model fields — so the approver ALWAYS has something real to
        # review. "No payload data" on a death review meant blind approval.
        own = getattr(obj, 'raw_payload', None)
        if own:
            return own
        sub = getattr(obj, 'submission', None)
        legacy = getattr(sub, 'raw_data', None)
        if legacy:
            return legacy
        summary = {
            'form': obj.sub_form_label,
            'death_type': obj.get_death_type_display(),
            'date_of_death': str(obj.date_of_death or ''),
            'district': obj.district,
            'upazila': obj.upazila,
            'union': obj.union,
            'case_serial': getattr(obj, 'case_serial', ''),
            'place_of_death': obj.get_place_of_death_display()
                              if obj.place_of_death else '',
            'cause_of_death': obj.cause_of_death,
            'age_years': getattr(obj, 'age_years', None),
            'admission_date': str(getattr(obj, 'admission_date', '') or ''),
            'narrative_notes': obj.notes,
            'action_plan': obj.action_plan,
        }
        return {k: v for k, v in summary.items() if v not in ('', None)}


class MPDSRDeathNotificationApprovalSerializer(serializers.ModelSerializer):
    """Detail serializer for the MPDSR death-notification approval queue."""
    class Meta:
        model = MPDSRDeathNotification
        fields = '__all__'
        read_only_fields = [
            'id', 'approval_status', 'approved_by', 'approved_at',
            'rejected_reason', 'kobo_submission_id', 'submitted_by_kobo_user',
            'created_at', 'updated_at',
        ]


class MaternalNearMissApprovalSerializer(serializers.ModelSerializer):
    """Detail serializer for the maternal-near-miss approval queue."""
    class Meta:
        model = MaternalNearMissCase
        fields = '__all__'
        read_only_fields = [
            'id', 'approval_status', 'approved_by', 'approved_at',
            'rejected_reason', 'kobo_submission_id', 'submitted_by_kobo_user',
            'created_at', 'updated_at',
        ]


class SafeSurgeryApprovalSerializer(serializers.ModelSerializer):
    """Detail serializer for the Safe Surgery Checklist (CIPRB-11) approval
    queue. Shown only in the PII-gated approval drawer, so patient_name
    (decrypted) is included for the reviewer who is signing it off."""
    class Meta:
        model = SurgeryChecklist
        fields = '__all__'
        read_only_fields = [
            'id', 'approval_status', 'approved_by', 'approved_at',
            'rejected_reason', 'kobo_submission_id', 'submitted_by_kobo_user',
            'system_ref', 'signin_total', 'signin_done', 'signin_complete',
            'timeout_total', 'timeout_done', 'timeout_complete',
            'signout_total', 'signout_done', 'signout_complete',
            'fully_compliant', 'created_at', 'updated_at',
        ]


class MPDSRActionSerializer(serializers.ModelSerializer):
    """Detail serializer for the CIPRB-10 MPDSR Action-Plan approval queue.
    Surfaces creator_name / last_edited_by_name so the approver can see who
    created vs who edited the action and reject a non-creator's edit.

    `raw_payload` is EXCLUDED (audit FIX 2026-06): it carries enumerator contact
    PII + GPS and is not needed to review an action. `reviewed_by`/`reviewed_at`/
    `review_history` are mapped from approved_by/approved_at/audit_trail so the
    approval UI's reviewer + history blocks render for an action the same way they
    do for a KoboSubmission."""
    reviewed_by = serializers.SerializerMethodField()
    reviewed_at = serializers.DateTimeField(source='approved_at', read_only=True)
    review_history = serializers.SerializerMethodField()

    class Meta:
        model = MPDSRAction
        exclude = ['raw_payload']
        read_only_fields = [
            'id', 'approval_status', 'approved_by', 'approved_at',
            'rejected_reason', 'kobo_submission_id', 'submitted_by_kobo_user',
            'creator_name', 'last_edited_by_name', 'organisation',
            'created_at', 'updated_at',
        ]

    def get_reviewed_by(self, obj):
        u = obj.approved_by
        if not u:
            return None
        return getattr(u, 'full_name', '') or getattr(u, 'email', '') or None

    def get_review_history(self, obj):
        return [
            {
                'reviewer': e.get('user', ''),
                'action': e.get('action', ''),
                'note': e.get('notes', ''),
                'timestamp': e.get('timestamp', ''),
            }
            for e in (obj.audit_trail or [])
        ]


class ServiceCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCenter
        fields = [
            'id', 'organisation', 'name', 'name_bangla', 'code',
            'center_type', 'district', 'upazila', 'address',
            'latitude', 'longitude', 'is_active',
        ]
        read_only_fields = ['id']


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = [
            'id', 'approval_status', 'approved_by', 'approved_at',
            'kobo_submission_id', 'submitted_at',
        ]


class ClientSummarySerializer(serializers.ModelSerializer):
    """Lean patient identity slice for Manager Approvals.

    Every service submission (visit, referral, screening, kit) carries a
    `client` FK to Client. The approval UI surfaces the linked patient
    prominently above the raw form data so reviewers can identify her
    without scrolling through field-by-field readouts.

    Only safe identity + status fields are exposed — no PII beyond what
    appears on the patient's PHD enrolment card, and nothing that
    duplicates the encrypted GBVCase survivor fields.
    """
    status_label = serializers.CharField(source='get_current_status_display',
                                          read_only=True)
    target_group_label = serializers.CharField(
        source='get_target_group_code_display', read_only=True)

    class Meta:
        model = Client
        fields = [
            'id', 'client_id', 'name', 'mother_name',
            'birth_year', 'current_address',
            'current_status', 'status_label',
            'target_group_code', 'target_group_label',
            'organisation',
        ]
        read_only_fields = fields


class ClinicVisitSerializer(serializers.ModelSerializer):
    patient = ClientSummarySerializer(source='client', read_only=True)

    class Meta:
        model = ClinicVisit
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class ClinicVisitApprovalSerializer(serializers.ModelSerializer):
    """Used by manager approve/reject endpoints."""
    class Meta:
        model = ClinicVisit
        fields = ['approval_status', 'rejected_reason']


class HIVSTITestResultSerializer(serializers.ModelSerializer):
    patient = ClientSummarySerializer(source='client', read_only=True)

    class Meta:
        model = HIVSTITestResult
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class ADRRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ADRRecord
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class AutoclaveLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoclaveLog
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class AntenatalCardSerializer(serializers.ModelSerializer):
    patient = ClientSummarySerializer(source='client', read_only=True)

    class Meta:
        model = AntenatalCard
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class HTCCounsellingSerializer(serializers.ModelSerializer):
    patient = ClientSummarySerializer(source='client', read_only=True)

    class Meta:
        model = HTCCounselling
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class IndividualCounsellingSerializer(serializers.ModelSerializer):
    patient = ClientSummarySerializer(source='client', read_only=True)

    class Meta:
        model = IndividualCounselling
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class MHScreeningSerializer(serializers.ModelSerializer):
    patient = ClientSummarySerializer(source='client', read_only=True)

    class Meta:
        model = MHScreening
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class GBVCaseSerializer(serializers.ModelSerializer):
    """
    Sensitive encrypted fields (survivor_name etc.) are excluded by default.
    A separate GBVCaseDetailSerializer exposes them to GBV officer / super admin.
    """
    class Meta:
        model = GBVCase
        exclude = [
            'raw_payload',
            'survivor_name', 'survivor_contact', 'survivor_address',
            'perpetrator_name', 'perpetrator_address',
        ]
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class GBVCaseDetailSerializer(serializers.ModelSerializer):
    """Full serializer — only for GBV officers and super admins."""
    class Meta:
        model = GBVCase
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class OutreachSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutreachSession
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class WellnessLogbookEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WellnessLogbookEntry
        # raw_payload kept — the approver needs the full F-01 submission to
        # review before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id']


class PHDCounsellingReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = PHDCounsellingReport
        # raw_payload kept — the approver reviews the full monthly summary.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id']


class GroupEducationSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupEducationSession
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class ReferralSerializer(serializers.ModelSerializer):
    is_overdue = serializers.BooleanField(read_only=True)
    patient = ClientSummarySerializer(source='client', read_only=True)

    class Meta:
        model = Referral
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at',
                            'outcome_updated_by']


class ReferralOutcomeSerializer(serializers.ModelSerializer):
    """Used for outcome update endpoint."""
    class Meta:
        model = Referral
        fields = ['outcome', 'outcome_date', 'outcome_notes']


class StockEntrySerializer(serializers.ModelSerializer):
    closing_balance = serializers.IntegerField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockEntry
        fields = '__all__'


class TemperatureLogSerializer(serializers.ModelSerializer):
    is_out_of_range = serializers.BooleanField(read_only=True)

    class Meta:
        model = TemperatureLog
        fields = '__all__'


class SafetyHygieneKitSerializer(serializers.ModelSerializer):
    patient = ClientSummarySerializer(source='client', read_only=True)

    class Meta:
        model = SafetyHygieneKit
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id']


class StoreRequisitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreRequisition
        fields = '__all__'


def _validate_photo_under_2mb(uploaded_file):
    """Serializer-level photo size check. Mirrors the model's
    validate_photo_size() so the gate holds regardless of code path."""
    if uploaded_file in (None, ''):
        return uploaded_file
    size = getattr(uploaded_file, 'size', None)
    max_bytes = 2 * 1024 * 1024
    if size is not None and size > max_bytes:
        raise serializers.ValidationError(
            f'Photo too large ({size / 1024 / 1024:.2f} MiB). '
            f'Maximum allowed is 2 MiB.'
        )
    return uploaded_file


class TrainingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrainingEvent
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']

    def validate_report_file(self, value):
        """Step 5 hard gate: training report upload is mandatory."""
        if not value:
            raise serializers.ValidationError(
                'A training report file is required.'
            )
        return value

    def validate_photo(self, value):
        return _validate_photo_under_2mb(value)


class CoordMeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoordMeeting
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']

    def validate_meeting_notes(self, value):
        """Step 5 hard gate: meeting notes upload is mandatory.

        Blocks PATCH/POST when the file is missing or empty, with a
        clear, user-facing error. Never silently accepts a meeting
        record without supporting documentation."""
        if not value:
            raise serializers.ValidationError(
                'A meeting notes file is required.'
            )
        return value

    def validate_photo(self, value):
        return _validate_photo_under_2mb(value)


class MobileHealthCampSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileHealthCamp
        # raw_payload kept in the response — Manager Approvals needs the
        # full submitted form data so reviewers can verify before approving.
        fields = '__all__'
        read_only_fields = ['approval_status', 'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_at']


class VisitorRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitorRegister
        fields = '__all__'


class IECMaterialSerializer(serializers.ModelSerializer):
    """IEC/SBCC distribution record. Feeds PHD 3.1a-d and Bandhu 4.1/4.3
    indicators. partner FK + organisation discriminator both required so
    queryset filters (OrgFilterMixin) work."""

    class Meta:
        model = IECMaterial
        exclude = ['raw_payload', 'submitted_by_kobo_user', 'rejected_reason']
        read_only_fields = ['id', 'created_at', 'updated_at',
                            'approved_by', 'approved_at',
                            'kobo_submission_id', 'submitted_by',
                            'latitude', 'longitude']
