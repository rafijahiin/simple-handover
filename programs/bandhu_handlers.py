"""
Webhook handlers for the 2 consolidated Bandhu XLSForms.

  bandhu_service_log_v1   → ClinicVisit | HIVSTITestResult | GBVCase |
                            IndividualCounselling | Referral
  bandhu_activity_ops_v1  → OutreachSession | MobileHealthCamp |
                            TrainingEvent | CoordMeeting | IECMaterial

Design (agreed with Rafi 2026-06-08):
  - ONE canonical tool per indicator → no double-counting.
  - For rows that ARE persisted, the FULL form payload is kept in raw_payload
    (Manager Approvals shows the complete readout).
  - Only fields the 18 indicators need are mapped to model columns; nothing
    invented.

NOT RETAINED IN SIMPLE (audit H1):
  - F-01 Wellness Centre Service Logbook (_bnd_logbook), F-11 Attendance
    (_bnd_attendance) and F-13 Stock Register (_bnd_stock) return 200 with NO
    database write. The programs webhook does not persist a KoboSubmission
    either, so these three forms currently live ONLY in KoboToolbox — they are
    NOT retained anywhere in SIMPLE (the earlier "kept in raw_payload" claim was
    inaccurate). Their service/participant volumes are counted via the canonical
    tools (F-05/F-06 for logbook, F-12 Event Report for attendance), and no
    indicator counts stock. Proper retention needs a new raw-payload model +
    migration — see the per-function TODOs.
"""
import logging
import uuid as _uuid

from django.http import HttpResponse
from django.utils import timezone

from .webhook import (
    _str, _bool, _int, _int_or_none, _nullable_bool, _date,
    _already_exists, _base_kwargs, _get_center,
)
from .models import (
    Client, ClinicVisit, HIVSTITestResult, IndividualCounselling,
    GBVCase, Referral, OutreachSession, MobileHealthCamp, WellnessLogbookEntry,
    TrainingEvent, CoordMeeting, IECMaterial,
)
from ._base_choices import BANDHU_DISTRICT_CODE

logger = logging.getLogger(__name__)

ORG = 'Bandhu'


# ─── helpers ──────────────────────────────────────────────────────────────────

def _client(payload, center, id_value):
    """Resolve the Bandhu Client by the inline ID typed on the service tool.
    The Mother List (F-1.1 → handle_bandhu_mother_list) is the registration
    tool, so a registered ID resolves to that real client (get_or_create finds
    the existing row). A service that references an UNREGISTERED ID still gets a
    placeholder 'Unknown' stub (auto-approved) so the FK holds and the
    submission is never lost — it surfaces as 'Unknown' until the client is
    registered via the Mother List. The service forms also warn the worker
    in-form when the ID is not in bandhu_clients.csv (see build_bandhu_forms
    _id_lookup), and bandhu_clients.csv is kept current by the Client post_save
    signal → export_bandhu_clients."""
    cid = (str(id_value or '').strip().upper()
           or f'STUB_{_uuid.uuid4().hex[:8].upper()}')
    client, _ = Client.objects.get_or_create(
        client_id=cid,
        defaults={
            'organisation': ORG, 'center': center,
            'name': 'Unknown', 'current_status': Client.ACTIVE,
            'approval_status': Client.APPROVED,
        },
    )
    return client


def _sub_date(payload):
    """Date for tools that have no date column (e.g. F-02 GBV) — use the
    Kobo submission date. Not invented data: it is submission metadata."""
    raw = str(payload.get('_submission_time', ''))[:10]
    return _date(raw) or timezone.now().date()


def _multi(payload, key):
    """select_multiple → list of selected codes (Kobo sends space-joined)."""
    return [t for t in _str(payload.get(key)).split() if t]


# ─── Form 1: Service Log ──────────────────────────────────────────────────────

def _bnd_patient(payload, lat, lng):
    """F-05 Patient Record → ClinicVisit. Drives 1.1 (HIV/STI screening) and
    1.5a (STI services)."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(ClinicVisit, payload):
        return HttpResponse('OK', status=200)
    refs = _multi(payload, 'pr_referral')
    screened = _bool(payload.get('pr_screening_sti_hiv'))
    ClinicVisit.objects.create(
        organisation=ORG, center=center,
        client=_client(payload, center, payload.get('pr_client_id')),
        visit_date=_date(payload.get('pr_date')) or _sub_date(payload),
        sti_screening_done=screened or bool(_str(payload.get('pr_sti_case'))),
        hiv_screening_done=screened,
        tb_screening_done=_bool(payload.get('pr_tb_screening')),
        gbv_screening_done=False,
        treatment_provided=_str(payload.get('pr_treatment')),
        condoms_distributed=_int(payload.get('pr_condom_demo')),
        sti_counselling_provided=_bool(payload.get('pr_sti_counseling')),
        follow_up_due_date=_date(payload.get('pr_followup_due')),
        follow_up_done_date=_date(payload.get('pr_followup_done')),
        referral_tb=('tb' in refs),
        referral_sti_kp=('sti_kp' in refs),
        referral_general_health=('general_health' in refs),
        referral_hiv_testing=('hiv_testing' in refs),
        referral_mental_health=('mental_health' in refs),
        referral_gbv=('gbv' in refs),
        referral_fp=('fp' in refs),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _bnd_htc(payload, lat, lng):
    """F-06 HTC → HIVSTITestResult. Drives 1.5b (HIV tests) and feeds 1.1."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(HIVSTITestResult, payload):
        return HttpResponse('OK', status=200)
    HIVSTITestResult.objects.create(
        organisation=ORG, center=center,
        client=_client(payload, center, payload.get('htc_client_id')),
        testing_date=_date(payload.get('htc_date_tested')) or _sub_date(payload),
        target_group=_str(payload.get('htc_tg')),
        hiv_result=_str(payload.get('htc_result')),
        referred=_bool(payload.get('htc_referred_art')),
        art_linkage_status=('referred' if _bool(payload.get('htc_referred_art')) else ''),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _bnd_gbv(payload, lat, lng):
    """F-02 GBV Register → GBVCase. Drives 1.2."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(GBVCase, payload):
        return HttpResponse('OK', status=200)
    d = _sub_date(payload)
    GBVCase.objects.create(
        organisation=ORG, center=center,
        interview_date=d, incident_date=d,
        survivor_age=_int_or_none(payload.get('gbv_age')) or _int_or_none(payload.get('gbv_age_manual')),
        needs_legal=_bool(payload.get('gbv_ref_legal')),
        needs_psychosocial=_bool(payload.get('gbv_ref_mental_health')),
        local_action_taken=_str(payload.get('gbv_primary_service')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _bnd_counsel_common(payload, lat, lng, date_key, client_id_key, issues, *, extra=None):
    """Shared writer for F-03 + Counseling → IndividualCounselling. Drives 1.3
    (issue_psychosocial). `extra` carries any tool-specific column values
    (e.g. F-03's drug-history fields) the caller wants persisted."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(IndividualCounselling, payload):
        return HttpResponse('OK', status=200)
    IndividualCounselling.objects.create(
        organisation=ORG, center=center,
        client=_client(payload, center, payload.get(client_id_key)),
        session_date=_date(payload.get(date_key)) or _sub_date(payload),
        issue_sti=('sti' in issues),
        issue_general_health=('general_health' in issues),
        issue_fp=('fp' in issues),
        issue_drug_use=('harmful_drug' in issues),
        issue_psychosocial=('psychosocial' in issues or 'mental_health' in issues),
        issue_gbv=('gbv' in issues),
        issue_other=('other' in issues),
        **(extra or {}),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _bnd_mh(payload, lat, lng):
    """F-03 Mental Health Counseling → IndividualCounselling (psychosocial)."""
    issues = ['mental_health'] + _multi(payload, 'mh_counsel_type')
    # F-03 drug-history fields persisted onto the model's existing columns.
    drug_noted = _bool(payload.get('mh_drug_history'))
    extra = {
        'drug_habit_noted': drug_noted,
        'drug_names': _str(payload.get('mh_drug_names')),
    }
    return _bnd_counsel_common(payload, lat, lng, 'mh_date', 'mh_client_id', issues, extra=extra)


def _bnd_counsel(payload, lat, lng):
    """Daily Counseling form → IndividualCounselling."""
    return _bnd_counsel_common(payload, lat, lng, 'cn_date', 'cn_client_id',
                               _multi(payload, 'cn_issues'))


def _bnd_referral(payload, lat, lng):
    """Referral Register → Referral. Drives 1.7 when an ART referral links."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(Referral, payload):
        return HttpResponse('OK', status=200)
    targets = _multi(payload, 'rf_referred_for')
    rtype = 'art' if 'art' in targets else (targets[0] if targets else 'other')
    received = _date(payload.get('rf_receiving_date'))
    Referral.objects.create(
        organisation=ORG, center=center,
        client=_client(payload, center, payload.get('rf_client_id')),
        referral_date=_date(payload.get('rf_date')) or _sub_date(payload),
        referral_type=rtype,
        referral_reason=_str(payload.get('rf_reason')),
        referred_to=_str(payload.get('rf_where')),
        follow_up_date=_date(payload.get('rf_followup_date')),
        outcome=('completed' if received else 'pending'),
        outcome_date=received,
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _bnd_hiv_identified(payload, lat, lng):
    """F-08 HIV identified → Referral(type=art) when linked to care. Drives 1.7
    (deduped by client). Full detail kept in raw_payload."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(Referral, payload):
        return HttpResponse('OK', status=200)
    linked = _bool(payload.get('hv_linked_care')) or \
        _str(payload.get('hv_receiving_art')) == 'yes'
    Referral.objects.create(
        organisation=ORG, center=center,
        client=_client(payload, center, payload.get('hv_client_uid')),
        referral_date=_date(payload.get('hv_date_testing')) or _sub_date(payload),
        referral_type='art',
        referral_reason='HIV positive — ART linkage',
        referred_to=_str(payload.get('hv_linked_with')),
        outcome=('completed' if linked else 'pending'),
        outcome_date=_date(payload.get('hv_art_start')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _norm_client_id(raw, center):
    """Normalise a logbook client ID to DD-NNNN. A bare 4-digit serial gets the
    centre's district-code prefix (repairs the free-text IDs like '0002' that
    never matched the Mother List). Anything already in DD-NNNN form is kept."""
    raw = str(raw or '').strip().upper()
    # Only a BARE 4-digit serial gets the district prefix. Anything else — already
    # DD-NNNN, or a malformed typo like '070002' — is left verbatim rather than
    # emitting a fake ID that matches no Mother List row.
    if '-' in raw or not (raw.isdigit() and len(raw) == 4):
        return raw
    dd = BANDHU_DISTRICT_CODE.get(getattr(center, 'district', ''), '00')  # match the form fallback
    return f'{dd}-{raw}'


def _log_service_fields(payload):
    """Map the F-01 services block → WellnessLogbookEntry flag/count columns.
    Shared by the live handler and the backfill command."""
    yn = lambda k: _str(payload.get(k)).lower() == 'yes'
    # Counts are PositiveIntegerField — clamp to >=0 (some legacy rows carry a
    # stray negative that violates the DB check constraint).
    n = lambda k: max(0, _int_or_none(payload.get(k)) or 0)
    return dict(
        tg_code=_str(payload.get('log_tg')),
        sti_screening=yn('log_sti_screening'),
        htc=yn('log_htc'),
        clinical=yn('log_clinical'),
        gbv=yn('log_gbv'),
        mental_health=yn('log_mental_health'),
        counseling=yn('log_counseling'),
        legal=yn('log_legal'),
        recreation=yn('log_recreation'),
        group_edu=yn('log_group_edu'),
        referral_codes=' '.join(_multi(payload, 'log_referral')),
        condom=n('log_condom'), condom_demo=n('log_condom_demo'),
        lubricant=n('log_lubricant'), awareness=n('log_awareness'), iec=n('log_iec'),
    )


def _outreach_service_fields(payload):
    """Map the F-04 Daily Outreach block → OutreachSession count columns.
    Shared by the live handler and the backfill command so the mapping never
    drifts. F-04 has no individual-contacts field, so that column is not set
    here (it stays 0 for Bandhu; only CIPRB/spondon outreach captures it)."""
    return dict(
        condoms_distributed_free=_int(payload.get('or_condom')),
        lubricants_distributed_free=_int(payload.get('or_lubricant')),
        hiv_aids_sti_knowledge_sessions=_int(payload.get('or_awareness')),
        iec_bcc_materials_distributed=_int(payload.get('or_iec')),
        # OutreachSession has no STI/GH/counseling/recreation columns, so those
        # referral counts fold into referral_other rather than being aliased onto
        # the wrong field (H2: or_ref_sti was previously mis-written to htc).
        referral_mental_health=_int(payload.get('or_ref_mental_health')),
        referral_gbv=_int(payload.get('or_ref_gbv')),
        referral_other=(
            _int(payload.get('or_ref_sti'))
            + _int(payload.get('or_ref_gh'))
            + _int(payload.get('or_ref_counseling'))
            + _int(payload.get('or_ref_recreation'))
            + _int(payload.get('or_ref_single_education'))
        ),
    )


def _bnd_logbook(payload, lat, lng):
    """F-01 Wellness Centre Service Logbook → WellnessLogbookEntry.

    Now the CANONICAL Bandhu per-client service record. The service flags are
    mapped to columns and READ by the Bandhu service indicators (1.2/1.3/1.5a/
    1.5b/4.1). Because Bandhu files no F-05/F-06 rows, this logbook is the single
    source and cannot double-count. The client ID is normalised to DD-NNNN so the
    service always links to its Mother List registration. Full payload kept in
    raw_payload for the reviewer."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(WellnessLogbookEntry, payload):
        return HttpResponse('OK', status=200)
    raw_id = _str(payload.get('log_client_id'))
    norm_id = _norm_client_id(raw_id, center)
    # Consolidated F-01 registers a NEW client inline (the ml_* registration
    # fields are present only when the ID was not found in the Mother List).
    # Reuse the tested Mother List handler so registration behaves identically.
    if _str(payload.get('ml_name')):
        reg = dict(payload)
        reg['ml_id_no'] = norm_id or raw_id
        resp = handle_bandhu_mother_list(reg, lat, lng)
        if getattr(resp, 'status_code', 200) >= 400:
            logger.warning('F-01 inline registration failed (%s) for id %r',
                           getattr(resp, 'status_code', '?'), reg['ml_id_no'])
    WellnessLogbookEntry.objects.create(
        organisation=ORG, center=center,
        service_date=_date(payload.get('log_date')) or _sub_date(payload),
        client_id=raw_id, client_id_norm=norm_id,
        **_log_service_fields(payload),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def handle_bandhu_service_log(payload, lat, lng):
    dispatch = {
        'patient_record':   _bnd_patient,
        'htc':              _bnd_htc,
        'gbv':              _bnd_gbv,
        'mh_counseling':    _bnd_mh,
        'counseling_daily': _bnd_counsel,
        'referral':         _bnd_referral,
        'hiv_identified':   _bnd_hiv_identified,
        'wellness_logbook': _bnd_logbook,
    }
    fn = dispatch.get(_str(payload.get('record_type')))
    if not fn:
        return HttpResponse('unknown record_type', status=400)
    return fn(payload, lat, lng)


# ─── Form 2: Activity & Operations ────────────────────────────────────────────

def _bnd_outreach(payload, lat, lng):
    """F-04 Daily Outreach → OutreachSession. Drives 1.4a (sessions) and feeds
    4.1 (IEC distributed)."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(OutreachSession, payload):
        return HttpResponse('OK', status=200)
    OutreachSession.objects.create(
        organisation=ORG, center=center,
        session_date=_date(payload.get('or_date')) or _sub_date(payload),
        peer_educator_name=_str(payload.get('or_peer_educator')),
        spot_name=_str(payload.get('or_spot')),
        **_outreach_service_fields(payload),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _bnd_camp(payload, lat, lng):
    """F-10 Mobile Camp patient record → MobileHealthCamp (one row per patient;
    1.9 counts distinct centre+date = camps conducted)."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(MobileHealthCamp, payload):
        return HttpResponse('OK', status=200)
    MobileHealthCamp.objects.create(
        organisation=ORG, center=center,
        camp_date=_date(payload.get('mc_date')) or _sub_date(payload),
        clients_served=1,
        hiv_tests_done=1 if _str(payload.get('mc_hiv_result')) else 0,
        sti_screenings_done=1 if _bool(payload.get('mc_screening_sti_hiv')) else 0,
        condoms_distributed=_int(payload.get('mc_condom_demo')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


# Event-kind routing for F-11/F-12. participant audience decides the model +
# the indicator (2.1 managers, 2.2 midwives, 2.5 peers / 2.3 GOB, 2.4 CBO,
# 2.6 observance). The form's gender/age counts give total_participants.
_TRAINING_KINDS = {
    'orientation_managers': ('orientation', 'HM'),
    'training_midwives':    ('training', 'MW'),
    'training_peers':       ('training', 'PE'),
}
_MEETING_KINDS = {
    'coord_gob':  'GOB',
    'coord_cbo':  'CBO',
    'observance': CoordMeeting.DAY_OBSERVANCE,
    # F-12 "Other" (Ashis review pt 6): record the event but keep it out of the
    # 2.3/2.4/2.6 indicator buckets — store as INTERNAL, not the GOB fallback.
    'other':      CoordMeeting.INTERNAL,
}


def _event_total(payload):
    explicit = _int_or_none(payload.get('ev_total'))
    if explicit:
        return explicit
    # Corrected gender buckets: Man / Woman / TG-Hijra / Others.
    keys = ['ev_man', 'ev_woman', 'ev_tg_hijra', 'ev_other']
    return sum(_int(payload.get(k)) for k in keys)


def _bnd_event(payload, lat, lng):
    """F-12 Event Report → TrainingEvent or CoordMeeting, by event kind."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    kind = _str(payload.get('ev_kind'))
    date = _date(payload.get('ev_date')) or _sub_date(payload)
    total = _event_total(payload)
    if kind in _TRAINING_KINDS:
        if _already_exists(TrainingEvent, payload):
            return HttpResponse('OK', status=200)
        etype, ptype = _TRAINING_KINDS[kind]
        TrainingEvent.objects.create(
            organisation=ORG, center=center,
            event_date=date, event_type=etype, participant_type=ptype,
            topic=_str(payload.get('ev_activity')),
            location_text=_str(payload.get('ev_place')),
            total_participants=total,
            notes=_str(payload.get('ev_ir')),
            **_base_kwargs(payload, lat, lng),
        )
        return HttpResponse('Created', status=201)
    mtype = _MEETING_KINDS.get(kind, 'GOB')
    if _already_exists(CoordMeeting, payload):
        return HttpResponse('OK', status=200)
    CoordMeeting.objects.create(
        organisation=ORG, center=center,
        meeting_date=date, meeting_type=mtype,
        location_text=_str(payload.get('ev_place')),
        participant_count=total,
        agenda=_str(payload.get('ev_objective')),
        key_decisions=_str(payload.get('ev_discussion')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _bnd_attendance(payload, lat, lng):
    """F-11 Attendance — per-participant roster. Kobo-only, NOT retained in
    SIMPLE.

    Returns 200 with no database write. The event's participant total is the
    counted source (F-12 Event Report → 2.1/2.2/2.5), so attendance rows must
    not inflate it; and the programs webhook stores no KoboSubmission, so this
    roster exists ONLY in KoboToolbox.
    TODO(audit H1): add a raw-payload retention model + migration to preserve
    the F-11 roster in SIMPLE for audit, without feeding any indicator.
    """
    return HttpResponse('OK', status=200)


def _bnd_stock(payload, lat, lng):
    """F-13 Stock Register — commodity ledger. Kobo-only, NOT retained in
    SIMPLE.

    Returns 200 with no database write. No Bandhu indicator counts stock, and
    the programs webhook stores no KoboSubmission, so this ledger exists ONLY in
    KoboToolbox.
    TODO(audit H1): add a raw-payload retention model + migration to preserve
    the F-13 ledger in SIMPLE for audit (the existing StockEntry model is a
    monthly-summary shape with a unique_together, not a drop-in fit).
    """
    return HttpResponse('OK', status=200)


def _bnd_ebillboard(payload, lat, lng):
    """F-14 e-billboard screenshot → IECMaterial(digital). Drives 4.2."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(IECMaterial, payload):
        return HttpResponse('OK', status=200)
    from partners.models import Partner
    partner = Partner.objects.filter(code='Bandhu').first()
    IECMaterial.objects.create(
        partner=partner, organisation=ORG, center=center,
        material_type=IECMaterial.DIGITAL, quantity=1,
        date_distributed=_date(payload.get('eb_date')) or _sub_date(payload),
        district=_str(payload.get('eb_location')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _bnd_centre_info(payload, lat, lng, *, name_key, addr_key, incharge_key,
                     staff_key, functional_key, equipped_key=None):
    """F-07 / F-09 — update the selected centre's roster details in place.
    These are reference/info records, not counted submissions.

    ServiceCenter has no dedicated incharge/staff/cruising-spot columns, so
    address + is_active are the only fields safely persisted here."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    changed = []
    addr = _str(payload.get(addr_key))
    if addr:
        center.address = addr; changed.append('address')
    func = payload.get(functional_key)
    if func is not None and _str(func) != '':
        center.is_active = _bool(func); changed.append('is_active')
    if changed:
        center.save(update_fields=changed + ['updated_at'] if hasattr(center, 'updated_at') else changed)
    return HttpResponse('OK', status=200)


def _bnd_kp_clinic_info(payload, lat, lng):
    """F-07 KP Clinic Information → updates the selected centre's roster."""
    return _bnd_centre_info(
        payload, lat, lng,
        name_key='kc_name', addr_key='kc_address', incharge_key='kc_incharge',
        staff_key='kc_num_staff', functional_key='kc_functional', equipped_key='kc_equipped')


def _bnd_wellness_center_info(payload, lat, lng):
    """F-09 Wellness Center Information → updates the selected centre's roster."""
    return _bnd_centre_info(
        payload, lat, lng,
        name_key='wc_name', addr_key='wc_address', incharge_key='wc_incharge',
        staff_key='wc_num_staff', functional_key='wc_functional')


def handle_bandhu_activity_ops(payload, lat, lng):
    dispatch = {
        'outreach':              _bnd_outreach,
        'mobile_camp':           _bnd_camp,
        'event_report':          _bnd_event,
        'attendance':            _bnd_attendance,
        'stock':                 _bnd_stock,
        'kp_clinic_info':        _bnd_kp_clinic_info,
        'wellness_center_info':  _bnd_wellness_center_info,
        'ebillboard':            _bnd_ebillboard,
    }
    fn = dispatch.get(_str(payload.get('record_type')))
    if not fn:
        return HttpResponse('unknown record_type', status=400)
    return fn(payload, lat, lng)


# ─── Beneficiary ID allocation ────────────────────────────────────────────────
import os as _os

_BANDHU_ML_ASSET_UID = _os.environ.get(
    'KOBO_ASSET_UID_BANDHU_ML', 'ar4muzSPxzhqd9XxVvWXjx')

# Until 2026-08-06 the 4-digit serial was typed by the peer educator and guarded
# only by a constraint against bandhu_clients.csv. That CSV is a snapshot which
# reaches a phone only when the device re-downloads the form, so two educators
# registering different people in the same sitting could not see each other's
# brand-new number and neither was blocked: 68 ids ended up shared by 165
# people. Allocation now happens HERE, in one place, so the race cannot exist.

def _next_free_serial(prefix, used):
    """Lowest unused serial for a centre, ignoring the birth years that were
    typed into the old 4-digit box (03-1980, 05-1988) — without that filter
    every new id would jump into the 1900s."""
    nums = sorted(int(c[len(prefix):]) for c in used
                  if c[len(prefix):].isdigit())
    dense = [n for n in nums if n <= max(60, len(nums) * 3)]
    n = (dense[-1] if dense else 0) + 1
    taken = set(nums)
    while n in taken:
        n += 1
    return n


def locked_name(client):
    """The stored name, re-read so a concurrent upgrade is not missed."""
    fresh = Client.objects.filter(pk=client.pk).values_list('name', flat=True).first()
    return fresh if fresh is not None else client.name


def _same_name(a, b):
    """Same woman, allowing for spacing and case only.

    Deliberately strict: anything looser would merge two different people, and
    merging is the failure this whole branch exists to prevent.
    """
    return ' '.join(str(a or '').split()).casefold() ==            ' '.join(str(b or '').split()).casefold()


def _allocate_client(dist_code, defaults, tries=40):
    """Create the Client under the next free id for this centre.

    No counter table and no explicit lock: read the current maximum, try to
    insert, and let the client_id UNIQUE constraint arbitrate when another
    worker claimed the same number in between. Retrying on IntegrityError is
    sufficient because that constraint is the only source of truth.
    """
    from django.db import IntegrityError, transaction
    prefix = '%s-' % dist_code
    for _ in range(tries):
        used = set(Client.objects.filter(
            organisation=ORG, client_id__startswith=prefix
        ).values_list('client_id', flat=True))
        candidate = '%s%04d' % (prefix, _next_free_serial(prefix, used))
        try:
            with transaction.atomic():
                return Client.objects.create(client_id=candidate, **defaults)
        except IntegrityError:
            continue
    raise RuntimeError('could not allocate a beneficiary id for %s' % prefix)


def _writeback_kobo_id(asset_uid, submission_id, client_id,
                       field_path='grp_ml/ml_id_no'):
    """Put the issued id back on the Kobo submission, in a daemon thread.

    Best effort by design: the id is authoritative in Spondon and reaches the
    field through bandhu_clients.csv either way, so a Kobo outage must never
    turn a successful registration into a 500 (a stranded submission is far
    worse than a register whose ID column fills in late).
    """
    import os
    import threading

    from django.conf import settings
    token = (getattr(settings, 'KOBO_API_TOKEN', '')
             or os.environ.get('KOBO_TOKEN', '')).strip()
    if not (token and asset_uid and submission_id):
        return

    def _run():
        try:
            import requests
            r = requests.patch(
                'https://kf.kobotoolbox.org/api/v2/assets/%s/data/bulk/' % asset_uid,
                headers={'Authorization': 'Token ' + token},
                json={'payload': {'submission_ids': [str(submission_id)],
                                  'data': {field_path: client_id}}},
                timeout=30)
            logger.info('Bandhu id write-back %s -> %s: %s',
                        submission_id, client_id, r.status_code)
        except Exception as exc:                        # noqa: BLE001
            logger.warning('Bandhu id write-back %s failed: %s', submission_id, exc)

    threading.Thread(target=_run, daemon=True, name='bandhu-id-writeback').start()


# ─── Form 0: Mother List (registration → Client, auto-approved) ────────────────

def handle_bandhu_mother_list(payload, lat, lng):
    """F-1.1 Mother List → create/update the Bandhu Client (the master list).

    Auto-approved for Bandhu (Rafi's decision, 2026-06-30): the Mother List is a
    field-managed registry that does not need manager sign-off, and the service
    forms' pulldata autofill must find the client the instant she registers.
    (PHD FSW registration, by contrast, IS manager-approved — partner-specific.)"""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    kobo_id = str(payload.get('_id', ''))
    # The re-delivery guard has to run BEFORE allocation. Kobo retries a
    # webhook that failed, and without this a retry would burn a second serial
    # on the same woman and register her twice.
    if kobo_id and Client.objects.filter(kobo_submission_id=kobo_id).exists():
        return HttpResponse('OK', status=200)
    # ml_id_no is now filled only when the worker typed an EXISTING id; a new
    # registration arrives with it blank and Spondon issues the number.
    client_id = str(payload.get('ml_id_no', '')
                    or payload.get('ml_existing_id', '')).strip().upper()
    # First registration wins — same rule as handle_phd_registration. A second
    # Mother List entry on the same ml_id_no is a DUPLICATE and must NOT
    # overwrite the existing client (that would silently replace one person's
    # record with another's). get_or_create only writes `defaults` on create.
    defaults = {
        'organisation': ORG, 'center': center,
        'name': _str(payload.get('ml_name')),
        'father_name': _str(payload.get('ml_parent_name')),
        'birth_year': _int_or_none(payload.get('ml_birth_year')),
        'target_group_code': _str(payload.get('ml_gender')),
        'current_address': _str(payload.get('ml_address')),
        'spot_name': _str(payload.get('ml_spot')),
        'education_level': _str(payload.get('ml_education')),
        'marital_status': _str(payload.get('ml_marital')),
        'children_under_18': _int_or_none(payload.get('ml_children_u18')),
        'occupation_code': _str(payload.get('ml_occupation')),
        'notes': _str(payload.get('ml_remarks')),
        'avg_clients_per_day': _int_or_none(payload.get('ml_avg_day')),
        # ml_fp_method (yn_code, skipped for never-married) → uses_fp_method.
        # Nullable: absent/empty stays None rather than defaulting to False.
        'uses_fp_method': _nullable_bool(payload, 'ml_fp_method'),
        'current_status': Client.ACTIVE,
        'approval_status': Client.APPROVED,
        'kobo_submission_id': kobo_id or None,
        'submitted_by_kobo_user': _str(payload.get('_submitted_by')),
        'latitude': lat, 'longitude': lng, 'raw_payload': payload,
    }
    if not client_id:
        # New registration: the worker typed nothing, so Spondon issues the id.
        dist = str(payload.get('centre_district_code', '')).strip()
        if not dist:
            return HttpResponse(
                'Bad Request — centre_district_code required to issue an id',
                status=400)
        client = _allocate_client(dist, defaults)
        logger.info('Bandhu Mother List issued %s to kobo=%s (%r)',
                    client.client_id, kobo_id or '-', client.name)
        _writeback_kobo_id(_BANDHU_ML_ASSET_UID, kobo_id, client.client_id)
        return HttpResponse('Created %s' % client.client_id, status=201)
    client, created = Client.objects.get_or_create(
        client_id=client_id, defaults=defaults,
    )
    if not created:
        # A Service Log referencing this id may have arrived FIRST and created
        # an auto-approved STUB (name 'Unknown'/'') with no demographics — Kobo
        # does not guarantee inter-form delivery order. The Mother List is the
        # source of truth for identity, so UPGRADE the stub in place rather than
        # dropping the demographic payload (the exporter excludes name in
        # ''/'Unknown', so without this the Service Log pulldata() keeps firing
        # "not in Mother List" forever). A real, *named* record is a genuine
        # duplicate — keep it (never clobber one person with another).
        from django.db import transaction
        with transaction.atomic():
            locked = Client.objects.select_for_update().get(pk=client.pk)
            if (locked.name or '').strip() in ('', 'Unknown'):
                for f in ('center', 'name', 'father_name', 'birth_year',
                          'target_group_code', 'current_address', 'spot_name',
                          'education_level', 'marital_status', 'children_under_18',
                          'occupation_code', 'notes', 'avg_clients_per_day',
                          'uses_fp_method', 'submitted_by_kobo_user',
                          'latitude', 'longitude', 'raw_payload'):
                    setattr(locked, f, defaults[f])
                locked.current_status = Client.ACTIVE
                locked.approval_status = Client.APPROVED
                locked.save()
                logger.info(
                    'Bandhu Mother List upgraded stub client %s (ml_id_no=%s) → %r',
                    locked.pk, client_id, locked.name)
                return HttpResponse('Stub upgraded to full registration', status=200)
        # Two different women can reach the same typed id. The duplicate check
        # in the form reads bandhu_clients.csv, which only lands on a phone when
        # the form is re-downloaded, so two peer educators registering different
        # people in one sitting never see each other's new number. That is not a
        # theory: of the 97 collisions cleaned up on 2026-08-06, 77 were made on
        # the same day as the record they clashed with and 63 involved two
        # different enumerators.
        #
        # This branch used to keep the existing record and return 200, which
        # meant the SECOND woman was never registered and nothing anywhere said
        # so. Registering her under the next free id is the only outcome that
        # loses nobody; the issued id is written back onto her Kobo submission
        # so the field can correct the paper register. Same behaviour as the
        # MPDSR action-id collision path.
        same_person = _same_name(locked_name(client), defaults['name'])
        if same_person:
            logger.warning(
                'Duplicate Bandhu Mother List ml_id_no=%s (kobo=%s) ignored — '
                'same person already registered as client %s (%r).',
                client_id, kobo_id or '-', client.pk, client.name,
            )
            return HttpResponse('Duplicate ml_id_no — existing registration kept',
                                status=200)

        dist = str(payload.get('centre_district_code', '')).strip() or client_id[:2]
        reissued = _allocate_client(dist, defaults)
        logger.warning(
            'Bandhu Mother List id collision: %s already belongs to %r; '
            'registering the incoming %r as %s instead (kobo=%s).',
            client_id, client.name, reissued.name, reissued.client_id,
            kobo_id or '-',
        )
        _writeback_kobo_id(_BANDHU_ML_ASSET_UID, kobo_id, reissued.client_id)
        return HttpResponse('Id in use — registered as %s' % reissued.client_id,
                            status=201)
    return HttpResponse('Created', status=201)
