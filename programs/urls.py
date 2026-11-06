from rest_framework.routers import DefaultRouter
from django.urls import path, include

from .views import (
    ServiceCenterViewSet, ClientViewSet,
    ClinicVisitViewSet, HIVSTITestResultViewSet, ADRRecordViewSet,
    AutoclaveLogViewSet, AntenatalCardViewSet,
    HTCCounsellingViewSet, IndividualCounsellingViewSet, MHScreeningViewSet,
    GBVCaseViewSet,
    IECMaterialViewSet,
    OutreachSessionViewSet, GroupEducationSessionViewSet, WellnessLogbookEntryViewSet,
    PHDCounsellingReportViewSet,
    ReferralViewSet,
    StockEntryViewSet, TemperatureLogViewSet,
    SafetyHygieneKitViewSet, StoreRequisitionViewSet,
    TrainingEventViewSet, CoordMeetingViewSet,
    MobileHealthCampViewSet, VisitorRegisterViewSet,
    PendingApprovalsView, NilReportView,
    CIPRBFistulaCaseViewSet,
    FistulaCampaignViewSet,
    MPDSRCaseApprovalViewSet,
    MPDSRDeathNotificationViewSet,
    MaternalNearMissViewSet,
    SafeSurgeryChecklistViewSet,
    MPDSRActionViewSet,
)

router = DefaultRouter()
router.register('centers',             ServiceCenterViewSet,          basename='center')
router.register('clients',             ClientViewSet,                 basename='client')
router.register('clinic-visits',       ClinicVisitViewSet,            basename='clinic-visit')
router.register('hiv-sti-results',     HIVSTITestResultViewSet,       basename='hiv-sti-result')
router.register('adr-records',         ADRRecordViewSet,              basename='adr-record')
router.register('autoclave-logs',      AutoclaveLogViewSet,           basename='autoclave-log')
router.register('antenatal-cards',     AntenatalCardViewSet,          basename='antenatal-card')
router.register('htc-counselling',     HTCCounsellingViewSet,         basename='htc-counselling')
router.register('individual-counselling', IndividualCounsellingViewSet, basename='individual-counselling')
router.register('mh-screening',        MHScreeningViewSet,            basename='mh-screening')
router.register('gbv-cases',           GBVCaseViewSet,                basename='gbv-case')
router.register('iec-materials',       IECMaterialViewSet,            basename='iec-material')
router.register('outreach-sessions',   OutreachSessionViewSet,        basename='outreach-session')
router.register('wellness-logbook',    WellnessLogbookEntryViewSet,   basename='wellness-logbook')
router.register('counselling-reports', PHDCounsellingReportViewSet,   basename='counselling-report')
router.register('group-education',     GroupEducationSessionViewSet,  basename='group-education')
router.register('referrals',           ReferralViewSet,               basename='referral')
router.register('stock-entries',       StockEntryViewSet,             basename='stock-entry')
router.register('temperature-logs',    TemperatureLogViewSet,         basename='temperature-log')
router.register('hygiene-kits',        SafetyHygieneKitViewSet,       basename='hygiene-kit')
router.register('store-requisitions',  StoreRequisitionViewSet,       basename='store-requisition')
router.register('training-events',     TrainingEventViewSet,          basename='training-event')
router.register('coord-meetings',      CoordMeetingViewSet,           basename='coord-meeting')
router.register('mobile-camps',        MobileHealthCampViewSet,       basename='mobile-camp')
router.register('visitor-register',    VisitorRegisterViewSet,        basename='visitor-register')
router.register('fistula-cases',       CIPRBFistulaCaseViewSet,       basename='fistula-case')
router.register('fistula-campaigns',   FistulaCampaignViewSet,        basename='fistula-campaign')
router.register('mpdsr-cases',         MPDSRCaseApprovalViewSet,      basename='prog-mpdsr-case')
router.register('mpdsr-notifications', MPDSRDeathNotificationViewSet, basename='prog-mpdsr-notification')
router.register('near-miss-cases',     MaternalNearMissViewSet,       basename='prog-near-miss')
router.register('surgery-checklists',  SafeSurgeryChecklistViewSet,   basename='prog-surgery-checklist')
router.register('mpdsr-actions',       MPDSRActionViewSet,            basename='prog-mpdsr-action')

urlpatterns = [
    path('', include(router.urls)),
    path('pending-approvals/', PendingApprovalsView.as_view(), name='pending-approvals'),
    path('nil-reports/', NilReportView.as_view(), name='nil-reports'),
]
