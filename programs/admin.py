from django.contrib import admin
from .models import (
    ServiceCenter, Client,
    ClinicVisit, HIVSTITestResult, ADRRecord, AutoclaveLog, AntenatalCard,
    HTCCounselling, IndividualCounselling, MHScreening,
    GBVCase, GBVAccessLog,
    IECMaterial,
    OutreachSession, GroupEducationSession,
    Referral,
    StockEntry, TemperatureLog, SafetyHygieneKit, StoreRequisition,
    TrainingEvent, CoordMeeting, MobileHealthCamp, VisitorRegister,
    PHDCounsellingReport,
)


# ─── Service Centres ───────────────────────────────────────────────────────────

@admin.register(ServiceCenter)
class ServiceCenterAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'organisation', 'center_type', 'district', 'is_active']
    list_filter = ['organisation', 'center_type', 'is_active', 'district']
    search_fields = ['name', 'code', 'district']
    ordering = ['organisation', 'code']


# ─── Clients ───────────────────────────────────────────────────────────────────

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['client_id', 'name', 'organisation', 'target_group_code', 'current_status', 'enrolled_date']
    list_filter = ['organisation', 'target_group_code', 'current_status', 'gender']
    search_fields = ['client_id', 'name']
    ordering = ['-enrolled_date']


# ─── Clinic ────────────────────────────────────────────────────────────────────

@admin.register(ClinicVisit)
class ClinicVisitAdmin(admin.ModelAdmin):
    list_display = ['client', 'organisation', 'visit_date', 'visit_type', 'approval_status', 'submitted_by_kobo_user']
    list_filter = ['organisation', 'approval_status', 'visit_type', 'visit_date']
    search_fields = ['client__client_id', 'submitted_by_kobo_user']
    date_hierarchy = 'visit_date'
    ordering = ['-visit_date']
    readonly_fields = ['kobo_submission_id', 'raw_payload', 'created_at', 'approved_at']


@admin.register(HIVSTITestResult)
class HIVSTITestResultAdmin(admin.ModelAdmin):
    list_display = ['client', 'organisation', 'testing_date', 'hiv_result', 'syphilis_result', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'hiv_result', 'syphilis_result']
    date_hierarchy = 'testing_date'
    ordering = ['-testing_date']


@admin.register(ADRRecord)
class ADRRecordAdmin(admin.ModelAdmin):
    list_display = ['client', 'organisation', 'report_date', 'adverse_effect_present', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'adverse_effect_present']
    ordering = ['-report_date']


@admin.register(AutoclaveLog)
class AutoclaveLogAdmin(admin.ModelAdmin):
    list_display = ['center', 'organisation', 'log_date', 'log_type', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'log_type']
    date_hierarchy = 'log_date'


@admin.register(AntenatalCard)
class AntenatalCardAdmin(admin.ModelAdmin):
    list_display = ['client', 'organisation', 'visit_date', 'anc_visit_number', 'trimester', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'trimester', 'anc_visit_number']
    date_hierarchy = 'visit_date'


# ─── Counselling ───────────────────────────────────────────────────────────────

@admin.register(HTCCounselling)
class HTCCounsellingAdmin(admin.ModelAdmin):
    list_display = ['client', 'organisation', 'session_date', 'session_type', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'session_type']
    date_hierarchy = 'session_date'


@admin.register(IndividualCounselling)
class IndividualCounsellingAdmin(admin.ModelAdmin):
    list_display = ['client', 'organisation', 'session_date', 'issue_psychosocial', 'issue_gbv', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'issue_psychosocial', 'issue_gbv']
    date_hierarchy = 'session_date'


@admin.register(MHScreening)
class MHScreeningAdmin(admin.ModelAdmin):
    list_display = ['client', 'organisation', 'screening_date', 'screening_type', 'severity_category', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'screening_type', 'severity_category']
    date_hierarchy = 'screening_date'


# ─── GBV ───────────────────────────────────────────────────────────────────────

@admin.register(GBVCase)
class GBVCaseAdmin(admin.ModelAdmin):
    list_display = ['organisation', 'incident_date', 'gbv_sexual', 'gbv_physical', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'gbv_sexual', 'gbv_physical']
    date_hierarchy = 'incident_date'
    readonly_fields = ['kobo_submission_id', 'raw_payload', 'created_at', 'approved_at']
    # Encrypted sensitive fields — excluded from admin
    exclude = ['survivor_name', 'survivor_contact', 'survivor_address',
               'perpetrator_name', 'perpetrator_address']


@admin.register(GBVAccessLog)
class GBVAccessLogAdmin(admin.ModelAdmin):
    list_display = ['case', 'user', 'action', 'timestamp', 'ip_address']
    list_filter = ['action']
    readonly_fields = ['case', 'user', 'action', 'timestamp', 'ip_address']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ─── Outreach ──────────────────────────────────────────────────────────────────

@admin.register(OutreachSession)
class OutreachSessionAdmin(admin.ModelAdmin):
    list_display = ['center', 'organisation', 'session_date', 'individual_contacts',
                    'condoms_distributed_free', 'approval_status']
    list_filter = ['organisation', 'approval_status']
    date_hierarchy = 'session_date'


@admin.register(GroupEducationSession)
class GroupEducationSessionAdmin(admin.ModelAdmin):
    list_display = ['center', 'organisation', 'session_date', 'topic', 'participant_count', 'approval_status']
    list_filter = ['organisation', 'approval_status']
    date_hierarchy = 'session_date'


# ─── Referrals ─────────────────────────────────────────────────────────────────

@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ['client', 'organisation', 'referral_date', 'referral_type',
                    'referred_to', 'outcome', 'outcome_date', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'referral_type', 'outcome']
    date_hierarchy = 'referral_date'
    search_fields = ['client__client_id', 'referred_to']


# ─── Supply ────────────────────────────────────────────────────────────────────

@admin.register(StockEntry)
class StockEntryAdmin(admin.ModelAdmin):
    list_display = ['center', 'organisation', 'reporting_month', 'item_name',
                    'item_category', 'opening_balance', 'quantity_received',
                    'quantity_issued', 'closing_balance']
    list_filter = ['organisation', 'item_category', 'reporting_month']
    search_fields = ['item_name']
    ordering = ['-reporting_month', 'item_name']


@admin.register(TemperatureLog)
class TemperatureLogAdmin(admin.ModelAdmin):
    list_display = ['center', 'organisation', 'log_date', 'morning_temp_celsius',
                    'afternoon_temp_celsius', 'is_out_of_range']
    list_filter = ['organisation']
    date_hierarchy = 'log_date'


@admin.register(SafetyHygieneKit)
class SafetyHygieneKitAdmin(admin.ModelAdmin):
    list_display = ['center', 'organisation', 'distribution_date', 'condom_count', 'approval_status']
    list_filter = ['organisation', 'approval_status']
    date_hierarchy = 'distribution_date'


@admin.register(StoreRequisition)
class StoreRequisitionAdmin(admin.ModelAdmin):
    list_display = ['center', 'organisation', 'requisition_date', 'requested_by', 'status']
    list_filter = ['organisation', 'status']
    date_hierarchy = 'requisition_date'


# ─── Operations ────────────────────────────────────────────────────────────────

@admin.register(TrainingEvent)
class TrainingEventAdmin(admin.ModelAdmin):
    list_display = ['organisation', 'event_date', 'event_type', 'participant_type',
                    'topic', 'total_participants', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'event_type', 'participant_type']
    date_hierarchy = 'event_date'
    search_fields = ['topic', 'facilitator']


@admin.register(CoordMeeting)
class CoordMeetingAdmin(admin.ModelAdmin):
    list_display = ['organisation', 'meeting_date', 'meeting_type', 'participant_count',
                    'district', 'approval_status']
    list_filter = ['organisation', 'approval_status', 'meeting_type']
    date_hierarchy = 'meeting_date'


@admin.register(MobileHealthCamp)
class MobileHealthCampAdmin(admin.ModelAdmin):
    list_display = ['center', 'organisation', 'camp_date', 'brothel_name',
                    'clients_served', 'hiv_tests_done', 'approval_status']
    list_filter = ['organisation', 'approval_status']
    date_hierarchy = 'camp_date'
    search_fields = ['brothel_name']


@admin.register(VisitorRegister)
class VisitorRegisterAdmin(admin.ModelAdmin):
    list_display = ['center', 'organisation', 'visit_date', 'visitor_name',
                    'designation_and_address', 'iec_bcc_distributed']
    list_filter = ['organisation', 'iec_bcc_distributed']
    date_hierarchy = 'visit_date'
    search_fields = ['visitor_name']


@admin.register(IECMaterial)
class IECMaterialAdmin(admin.ModelAdmin):
    """Audit FIX 12.2 — IEC/SBCC distribution log. Feeds PHD 3.1a-d and
    Bandhu 4.1 / 4.3 indicators."""
    list_display = ['partner', 'organisation', 'material_type', 'quantity',
                    'date_distributed', 'district', 'approval_status']
    list_filter = ['organisation', 'material_type', 'approval_status']
    date_hierarchy = 'date_distributed'
    search_fields = ['district', 'notes']
    raw_id_fields = ['center', 'submitted_by', 'approved_by']


@admin.register(PHDCounsellingReport)
class PHDCounsellingReportAdmin(admin.ModelAdmin):
    """PHD monthly counselling aggregate (phd_service_log `sec_counsel`).
    mh_count is the source for indicator SL3 (MH counselling sessions)."""
    list_display = ['organisation', 'report_date', 'prepared_by', 'mh_count',
                    'group_mh_count', 'gbv_count', 'total_count', 'approval_status']
    list_filter = ['organisation', 'approval_status']
    date_hierarchy = 'report_date'
    search_fields = ['prepared_by', 'note']
