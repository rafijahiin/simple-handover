"""
Bandhu (SOGIEC) indicator compute functions.
All filter on approval_status='APPROVED' only.
Period args: period_start, period_end are date objects.
"""
from django.db.models import Q, Sum
from programs.models import (
    Client, ClinicVisit, HIVSTITestResult, HTCCounselling,
    IndividualCounselling, GroupEducationSession, OutreachSession,
    GBVCase, Referral, ServiceCenter, TrainingEvent, CoordMeeting, MobileHealthCamp,
    IECMaterial, WellnessLogbookEntry,
)


def _logbook(org, period_start, period_end):
    """APPROVED F-01 logbook rows in the period — the canonical Bandhu service
    source. Bandhu files no F-05/F-06, so counting these plus the (near-empty)
    specific-form models is a single source, not a double-count."""
    return WellnessLogbookEntry.objects.filter(
        organisation=org, approval_status=APPROVED,
        service_date__range=(period_start, period_end),
    )
from ._centers import active_center_ids

ORG = 'Bandhu'
APPROVED = 'APPROVED'


def compute_I_BND_1_1(org, period_start, period_end):
    """KP individuals reached — the Mother List registry. Target: 4,000.

    Rafi's M&E decision (2026-07-01): 'KP reached' is measured by the Mother
    List (F-1.1 registration) — the register of KP individuals the programme has
    enrolled — NOT the F-05/F-06 service sub-counts. HIV/STI/HTC service delivery
    is tracked separately by 1.5a (STI services) and 1.5b (HIV testing), so this
    no longer double-reads those forms.

    Counts registered, APPROVED, non-stub Bandhu clients by registration date
    (Client.created_at). Cumulative = the whole registry; monthly = new
    registrations that month. Registration is auto-approved for Bandhu, so the
    number reflects the live Mother List (stubs — name ''/'Unknown' created by a
    service log citing an unregistered ID — are excluded, mirroring the client
    lookup-CSV exporter)."""
    return (
        Client.objects.filter(
            organisation=org, approval_status=Client.APPROVED,
            created_at__date__range=(period_start, period_end),
        )
        .exclude(name='').exclude(name='Unknown')
        .values('client_id').distinct().count()
    )


def compute_I_BND_1_2(org, period_start, period_end):
    """GBV survivors screened and referred. Target: 120 (MIS doc).

    SINGLE SOURCE — the F-01 logbook gbv tick. Bandhu records GBV only in the
    logbook (the F-02 record type is removed from the Bandhu Service Log), so the
    logbook is counted alone — never summed with GBVCase — to guarantee no
    double-count if a stray/legacy F-02 row ever coexists."""
    return _logbook(org, period_start, period_end).filter(gbv=True).count()


def compute_I_BND_1_3(org, period_start, period_end):
    """Individuals receiving MHPSS counselling. Target: 48 persons (MIS doc).

    M2: counts ONLY IndividualCounselling(issue_psychosocial=True) — the F-03
    Mental Health Counseling tool is the single canonical source. The previous
    GroupEducationSession(topic~'mental') term was dead weight (no Bandhu
    handler writes GroupEducationSession) that could inflate 1.3 if a generic
    group-ed row ever landed under org=Bandhu, so it is removed."""
    # SINGLE SOURCE — the F-01 logbook mental_health tick (F-03 record type is
    # removed from the Bandhu Service Log), counted alone to avoid any double-count.
    return _logbook(org, period_start, period_end).filter(mental_health=True).count()


def compute_I_BND_1_4A(org, period_start, period_end):
    """Outreach + health-education sessions conducted. Target: 480 (MIS doc).

    Counts both the daily outreach monitoring submissions (OutreachSession,
    F-04) and any group health-education sessions (GroupEducationSession) —
    each row is one session conducted."""
    outreach = OutreachSession.objects.filter(
        organisation=org, approval_status=APPROVED,
        session_date__range=(period_start, period_end),
    ).count()
    group = GroupEducationSession.objects.filter(
        organisation=org, approval_status=APPROVED,
        session_date__range=(period_start, period_end),
    ).count()
    return outreach + group


# NOTE: indicator 1.4b ("KP reached via outreach", 4,000) was retired per the
# framework review — it duplicated 1.1 (KP receiving services, also 4,000).
# Only 1.4a (outreach sessions conducted) remains for the outreach activity.


def compute_I_BND_1_5_hiv(org, period_start, period_end):
    """KP receiving HIV testing services. Target: 2,000 (MIS doc, code 1.5b).

    Counts EVERY HTC Service Register (F-06) row as one HIV test received —
    there is NO hiv_result gate, so records with any result (or no result yet)
    are all counted as a testing-service delivered. M4: this is the M&E
    framework's definition of "received HIV testing services" and is a
    DEFINITION choice for UNFPA to confirm, not a bug — do not add a result
    filter without their sign-off."""
    # SINGLE SOURCE — the F-01 logbook htc tick (F-06 record type is removed from
    # the Bandhu Service Log), counted alone to avoid any double-count.
    return _logbook(org, period_start, period_end).filter(htc=True).count()


def compute_I_BND_1_5_sti(org, period_start, period_end):
    """KP receiving STI services. Target: 2,000 (MIS doc, code 1.5a).

    Counts clinic visits where STI screening was done (Patient Record Register
    F-05, sti_screening_done=True). M3: sti_screening_done is used as the proxy
    for "received STI services" — this is a DEFINITION choice for UNFPA to
    confirm (screening vs treatment/case), not a bug. Do not narrow to
    STI-case/treatment fields without their sign-off."""
    # SINGLE SOURCE — the F-01 logbook sti_screening tick (F-05 record type is
    # removed from the Bandhu Service Log), counted alone to avoid any double-count.
    return _logbook(org, period_start, period_end).filter(sti_screening=True).count()


def compute_I_BND_1_6(org, period_start, period_end):
    """KP clinic (Dhaka) functional. Target: 1.

    Counts the Dhaka KP-clinic centre only once it is actually delivering
    services in the period (>=1 approved record). A configured-but-idle centre
    reads 0 until real activity arrives — see indicators/_centers.py."""
    base = ServiceCenter.objects.filter(
        organisation=org, is_active=True, district__icontains='Dhaka'
    )
    return len(active_center_ids(period_start, period_end, base))


def compute_I_BND_1_7(org, period_start, period_end):
    """KP referred and linked to ART/treatment. Target: 25 (MIS doc)."""
    return Referral.objects.filter(
        organisation=org, approval_status=APPROVED,
        referral_date__range=(period_start, period_end),
        referral_type__in=['art', 'hiv', 'sti_kp'],
        outcome='completed',
    ).values('client').distinct().count()


def compute_I_BND_1_8(org, period_start, period_end):
    """Community-friendly drop-in centres established/strengthened.
    Target: 8 (MIS doc — one per project district).

    Counts DIC centres actually delivering services in the period (>=1 approved
    record). A configured-but-idle DIC reads 0 until real activity arrives, so a
    pre-launch system shows 0/8, not 8/8 — see indicators/_centers.py."""
    base = ServiceCenter.objects.filter(
        organisation=org, is_active=True, center_type='DIC'
    )
    return len(active_center_ids(period_start, period_end, base))


def compute_I_BND_1_9(org, period_start, period_end):
    """Mobile outreach health camps conducted. Target: 40 camps (MIS doc).

    The F-10 form records one row per patient, so a camp = a distinct
    (centre, date) pair — count those, not patient rows."""
    return MobileHealthCamp.objects.filter(
        organisation=org, approval_status=APPROVED,
        camp_date__range=(period_start, period_end),
    ).values('center', 'camp_date').distinct().count()


def compute_I_BND_2_1(org, period_start, period_end):
    """Health managers oriented. Target: 150"""
    return TrainingEvent.objects.filter(
        organisation=org, approval_status=APPROVED,
        event_date__range=(period_start, period_end),
        participant_type__in=['HM', 'GOB'],
        event_type='orientation',
    ).aggregate(t=Sum('total_participants'))['t'] or 0


def compute_I_BND_2_2(org, period_start, period_end):
    """Midwives/frontline providers trained. Target: 150"""
    return TrainingEvent.objects.filter(
        organisation=org, approval_status=APPROVED,
        event_date__range=(period_start, period_end),
        participant_type='MW',
        event_type='training',
    ).aggregate(t=Sum('total_participants'))['t'] or 0


def compute_I_BND_2_3(org, period_start, period_end):
    """GOB coordination meetings. Target: 12"""
    return CoordMeeting.objects.filter(
        organisation=org, approval_status=APPROVED,
        meeting_date__range=(period_start, period_end),
        meeting_type='GOB',
    ).count()


def compute_I_BND_2_4(org, period_start, period_end):
    """CBO coordination meetings. Target: 10"""
    return CoordMeeting.objects.filter(
        organisation=org, approval_status=APPROVED,
        meeting_date__range=(period_start, period_end),
        meeting_type='CBO',
    ).count()


def compute_I_BND_2_5(org, period_start, period_end):
    """Community leaders/PEs trained. Target: 125"""
    return TrainingEvent.objects.filter(
        organisation=org, approval_status=APPROVED,
        event_date__range=(period_start, period_end),
        participant_type__in=['PE', 'CL'],
    ).aggregate(t=Sum('total_participants'))['t'] or 0


def compute_I_BND_2_6(org, period_start, period_end):
    """Day-observance / awareness events supported. Target: 2.

    Counts CoordMeeting rows of type DAY_OBSERVANCE (added in audit FIX 12.4).
    World AIDS Day, Hijra Pride, Human Rights Day, etc. all flow through
    this single meeting_type so the indicator has one clean source."""
    return CoordMeeting.objects.filter(
        organisation=org, approval_status=APPROVED,
        meeting_date__range=(period_start, period_end),
        meeting_type=CoordMeeting.DAY_OBSERVANCE,
    ).count()


def compute_I_BND_4_1(org, period_start, period_end):
    """IEC/SBCC materials distributed. Target: 50,000.

    Canonical source is IECMaterial, plus IEC quantities recorded on outreach
    (F-04 or_iec). Clinic-visit condoms are NOT counted here — condoms are not
    IEC/SBCC materials (Ashis / CIPRB MIS review, 2026-07-07); counting them
    under 4.1 over-stated the indicator, so the ClinicVisit.condoms_distributed
    term was removed."""
    iec = IECMaterial.objects.filter(
        organisation=org, approval_status=APPROVED,
        date_distributed__range=(period_start, period_end),
        material_type__in=[
            IECMaterial.LEAFLET, IECMaterial.POSTER, IECMaterial.MESSAGE_BOARD,
            IECMaterial.SIGNBOARD, IECMaterial.OTHER,
        ],
    ).aggregate(t=Sum('quantity'))['t'] or 0

    outreach = OutreachSession.objects.filter(
        organisation=org, approval_status=APPROVED,
        session_date__range=(period_start, period_end),
    ).aggregate(t=Sum('iec_bcc_materials_distributed'))['t'] or 0

    logbook = _logbook(org, period_start, period_end).aggregate(
        t=Sum('iec'))['t'] or 0

    return iec + outreach + logbook


def compute_I_BND_4_2(org, period_start, period_end):
    """Public messaging displays installed. Target: 56 (MIS doc, code 4.2 —
    40 printed billboards + 16 e-billboards).

    The framework lists displays as ONE indicator, so this sums both the
    printed (BILLBOARD) and digital (DIGITAL) IEC material types."""
    return IECMaterial.objects.filter(
        organisation=org, approval_status=APPROVED,
        date_distributed__range=(period_start, period_end),
        material_type__in=[IECMaterial.BILLBOARD, IECMaterial.DIGITAL],
    ).aggregate(t=Sum('quantity'))['t'] or 0


# ─── Activity-code registry ──────────────────────────────────────────────────
#
# Maps the canonical `activity_code` from IndicatorTarget rows (set by data
# migration 0004_load_target_fixtures) to the compute function above.
#
# Codes absent from this registry are treated as UNLINKED by the service
# layer — the row still renders on the org page with achievement=0 and a
# small "module not built yet" badge, never a crash.
#
# Every Bandhu indicator now has a compute function — the previous gaps
# at 2.6 (day observance) and 4.3 (e-billboards) closed when the
# DAY_OBSERVANCE meeting type and IECMaterial model landed in Commits 1
# and 2 respectively.

ACTIVITY_REGISTRY = {
    '1.1':  compute_I_BND_1_1,
    '1.2':  compute_I_BND_1_2,
    '1.3':  compute_I_BND_1_3,
    '1.4a': compute_I_BND_1_4A,
    '1.5a': compute_I_BND_1_5_sti,      # STI services (clinic)
    '1.5b': compute_I_BND_1_5_hiv,      # HIV testing (HTC register)
    '1.6':  compute_I_BND_1_6,          # functional Dhaka KP clinic (activity-gated)
    '1.7':  compute_I_BND_1_7,
    '1.8':  compute_I_BND_1_8,          # functional DICs (activity-gated)
    '1.9':  compute_I_BND_1_9,
    '2.1':  compute_I_BND_2_1,
    '2.2':  compute_I_BND_2_2,
    '2.3':  compute_I_BND_2_3,
    '2.4':  compute_I_BND_2_4,
    '2.5':  compute_I_BND_2_5,
    '2.6':  compute_I_BND_2_6,
    '4.1':  compute_I_BND_4_1,
    '4.2':  compute_I_BND_4_2,
}

# Codes whose compute function takes only (org) — no period args.
ORG_ONLY_CODES = set()  # 1.6/1.8 are now period-aware (activity-gated functional centres)
