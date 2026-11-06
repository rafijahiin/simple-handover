"""
KoboToolbox webhook handler for all programs form types.

POST /webhook/programs/
Single endpoint; dispatch is keyed on `_xform_id_string` from KoboToolbox.

Form id_string → model mapping (id_string is set in the XLS form settings
sheet and MUST match exactly what KoboToolbox sends):

  spondon_client_reg_v1      → Client (registration — both orgs)
  spondon_clinic_visit_v1    → ClinicVisit
  spondon_hiv_sti_test_v1    → HIVSTITestResult
  spondon_adr_record_v1      → ADRRecord
  spondon_autoclave_log_v1   → AutoclaveLog
  spondon_antenatal_card_v1  → AntenatalCard (PHD only)
  spondon_htc_counsel_v1     → HTCCounselling
  spondon_counselling_v1     → IndividualCounselling
  spondon_mh_screening_v1    → MHScreening
  spondon_gbv_case_v1        → GBVCase
  spondon_outreach_v1        → OutreachSession
  spondon_group_edu_v1       → GroupEducationSession
  spondon_referral_v1        → Referral
  spondon_hygiene_kit_v1     → SafetyHygieneKit (Bandhu only)
  spondon_training_event_v1  → TrainingEvent
  spondon_coord_meeting_v1   → CoordMeeting
  spondon_mobile_camp_v1     → MobileHealthCamp (PHD only)

Design notes:
- All handlers are idempotent via kobo_submission_id unique constraint.
- Center lookup: uses `center_code` field; falls back to org's first active
  centre (with a warning log) to avoid discarding field data.
- Client lookup: uses `client_id` field; creates a minimal stub on first
  encounter so FK constraints are satisfied and the record is preserved.
- GBV: EncryptedCharField encrypts PII transparently on save — plain text
  values are passed from the payload.
- Nullable booleans (temp_121_achieved, etc.): absent key → None, present → bool.
"""
import json
import logging
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from submissions.validators import validate_kobo_signature
from .models import (
    ServiceCenter, Client,
    ClinicVisit, HIVSTITestResult, ADRRecord, AutoclaveLog, AntenatalCard,
    HTCCounselling, IndividualCounselling, MHScreening,
    GBVCase,
    OutreachSession, GroupEducationSession,
    Referral,
    SafetyHygieneKit,
    TrainingEvent, CoordMeeting, MobileHealthCamp,
    StockEntry, IECMaterial,
)

logger = logging.getLogger(__name__)


# ─── Value coercion helpers ────────────────────────────────────────────────────

def _str(v, default: str = '') -> str:
    return str(v).strip() if v is not None else default


def _bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ('yes', 'true', '1', 'on', 'checked', 'oui')


def _nullable_bool(payload: dict, key: str):
    """Return bool if key present and non-empty, else None."""
    v = payload.get(key)
    if v is None or v == '':
        return None
    return _bool(v)


def _int(v, default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _int_or_none(v):
    """Return int or None (for optional IntegerFields)."""
    if v is None or v == '':
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _decimal(v):
    """Return Decimal or None."""
    if v is None or v == '':
        return None
    try:
        return Decimal(str(v).strip())
    except Exception:
        return None


def _date(v):
    """Parse YYYY-MM-DD → date or None."""
    if not v:
        return None
    try:
        from datetime import date
        return date.fromisoformat(str(v).strip()[:10])
    except (ValueError, TypeError):
        return None


def _geolocation(payload: dict) -> tuple:
    geo = payload.get('_geolocation')
    if not isinstance(geo, (list, tuple)) or len(geo) < 2:
        # An object/null _geolocation (geo[0] on a dict → KeyError, uncaught)
        # would 500 and strand the submission; coerce to no-location instead.
        return None, None
    try:
        return float(geo[0]), float(geo[1])
    except (TypeError, ValueError):
        return None, None


def _org(payload: dict) -> str:
    raw = (
        payload.get('organisation') or
        payload.get('partner_org') or
        payload.get('partner') or ''
    ).strip().upper()
    if 'PHD' in raw:
        return 'PHD'
    if 'BANDHU' in raw or 'BONDHU' in raw or 'BONDU' in raw or 'BND' in raw:
        return 'Bandhu'
    return ''


# ─── FK resolution helpers ─────────────────────────────────────────────────────

def _get_center(payload: dict, org: str):
    """
    Resolve ServiceCenter. Matches, in order:
      1. center_code (exact ServiceCenter.code, e.g. 'R001')
      2. centre_id / center_name as typed in the form — either the
         Wellness Centre ID ('R001') or its name ('Daulatdia Wellness
         Center'), case-insensitive, scoped to the org.
      3. the org's first active centre (fallback, warns)
    Returns None only if there are zero active centres (setup issue).

    PHD field workers type the wellness-centre NAME (or its ID) in the
    'centre_id' field — there is no center_code on the wire — so the
    name/ID match in step 2 is what actually assigns the right centre.
    """
    code = _str(payload.get('center_code'))
    if code:
        center = ServiceCenter.objects.filter(code=code, is_active=True).first()
        if center:
            return center
        logger.warning('Programs webhook: center_code %r not found; trying fallback', code)

    # Step 2 — match the free-text centre the worker typed (ID or name).
    typed = _str(payload.get('centre_id')) or _str(payload.get('center_name'))
    if typed:
        qs = ServiceCenter.objects.filter(organisation=org, is_active=True)
        center = (
            qs.filter(code__iexact=typed).first()
            or qs.filter(name__iexact=typed).first()
            or qs.filter(name__icontains=typed).first()
        )
        if center:
            return center
        logger.warning('Programs webhook: centre %r not matched for org %r; trying fallback', typed, org)

    # Never drop a submission just because the centre can't be matched — fall
    # back to the org's first active centre, then to an org-scoped auto-created
    # placeholder. (Workshop fix: forms whose centre list doesn't match seeded
    # centres were 400'ing with "center not found".)
    #
    # M1: every fallback is scoped to the submission's OWN org. A cross-org
    # fallback (ANY active centre) previously let a Bandhu submission bind to a
    # PHD centre, and the auto-create defaulted to org='PHD'. Both are now
    # org-bound so a Bandhu submission can never land on/create a PHD centre.
    center = ServiceCenter.objects.filter(organisation=org, is_active=True).first()
    if center:
        logger.warning('Programs webhook: no matched centre for org %r; using org fallback %r', org, center.code)
        return center
    center = ServiceCenter.objects.create(
        code=f'AUTO-{(org or "NA")[:8].upper()}',
        organisation=org or 'PHD',
        name=f'{org or "Unassigned"} (auto-created)',
        center_type='sda',
        district='',
        is_active=True,
    )
    logger.warning('Programs webhook: auto-created placeholder centre %r for org %r', center.code, org or 'PHD')
    return center


def _get_or_create_client(payload: dict, center, org: str):
    """
    Resolve Client by client_id.  Creates a minimal stub when not found so
    FK constraints are satisfied and the submission is not lost.
    """
    client_id = _str(payload.get('client_id'))
    if not client_id:
        import uuid as _uuid
        client_id = f'STUB_{_uuid.uuid4().hex[:8].upper()}'

    client, created = Client.objects.get_or_create(
        client_id=client_id,
        defaults={
            'organisation': org,
            'center': center,
            'name': _str(payload.get('client_name', 'Unknown')),
            'current_status': Client.ACTIVE,
            'approval_status': Client.APPROVED,   # stubs are auto-approved
        },
    )
    if created:
        logger.info('Programs webhook: created stub client %s', client_id)
    return client


def _resolve_submitter(payload: dict):
    """Resolve the Kobo collector username to a local User row, or None.

    Order of attempts:
      1. payload['_submitted_by'] matched against User.email
      2. same value matched against full_name (case-insensitive)
      3. payload['enumerator_email'] (if a form passes it explicitly)

    Returning None means the record will land with submitted_by=NULL —
    which is fine for org-level visibility but means field staff won't
    see it through the FIX 15.7 own-entries filter until the user is
    eventually matched in a later run. Lookup is best-effort and never
    blocks ingestion."""
    try:
        from accounts.models import User
    except Exception:
        return None
    raw = (
        payload.get('_submitted_by')
        or payload.get('enumerator_email')
        or payload.get('collector_email')
        or ''
    )
    raw = str(raw).strip()
    if not raw:
        return None
    # Case-insensitive email match first — Kobo usernames are commonly
    # email-shaped or coincide with the local-part of email.
    qs = User.objects.filter(is_active=True)
    user = qs.filter(email__iexact=raw).first()
    if user:
        return user
    user = qs.filter(email__istartswith=f'{raw}@').first()
    if user:
        return user
    user = qs.filter(full_name__iexact=raw).first()
    return user


def _base_kwargs(payload: dict, lat, lng) -> dict:
    """Fields common to every SubmissionBase create() call."""
    return {
        'kobo_submission_id': str(payload.get('_id', '')),
        'submitted_by_kobo_user': _str(payload.get('_submitted_by')),
        # Audit FIX 15.7 — populate the FK so field staff can see their own
        # entries through the OrgFilterMixin per-user filter. None when the
        # collector_name can't be resolved to a User; the org filter still
        # applies as a safety net.
        'submitted_by': _resolve_submitter(payload),
        'latitude': lat,
        'longitude': lng,
        'raw_payload': payload,
    }


def _already_exists(model, payload: dict) -> bool:
    return model.objects.filter(
        kobo_submission_id=str(payload.get('_id', ''))
    ).exists()


# ─── Form handlers ─────────────────────────────────────────────────────────────

def _handle_clinic_visit(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(ClinicVisit, payload):
        return HttpResponse('OK', status=200)
    client = _get_or_create_client(payload, center, org)

    ClinicVisit.objects.create(
        organisation=org, center=center, client=client,
        visit_date=_date(payload.get('visit_date')) or timezone.now().date(),
        visit_type=_str(payload.get('visit_type'), ClinicVisit.NEW),
        monthly_serial=_str(payload.get('monthly_serial')),
        # Screenings
        sti_screening_done=_bool(payload.get('sti_screening_done')),
        hiv_screening_done=_bool(payload.get('hiv_screening_done')),
        tb_screening_done=_bool(payload.get('tb_screening_done')),
        diabetic_screening_done=_bool(payload.get('diabetic_screening_done')),
        hep_b_screening_done=_bool(payload.get('hep_b_screening_done')),
        hep_c_screening_done=_bool(payload.get('hep_c_screening_done')),
        # STI diagnoses
        diag_uds=_bool(payload.get('diag_uds')),
        diag_vds=_bool(payload.get('diag_vds')),
        diag_gu=_bool(payload.get('diag_gu')),
        diag_pid=_bool(payload.get('diag_pid')),
        diag_ss=_bool(payload.get('diag_ss')),
        diag_ib=_bool(payload.get('diag_ib')),
        diag_anal_sti=_bool(payload.get('diag_anal_sti')),
        diag_other=_bool(payload.get('diag_other')),
        diag_other_specify=_str(payload.get('diag_other_specify')),
        diag_gh=_bool(payload.get('diag_gh')),
        diag_psd=_bool(payload.get('diag_psd')),
        diag_mental_health=_bool(payload.get('diag_mental_health')),
        treatment_provided=_str(payload.get('treatment_provided')),
        seeking_treatment_timing=_str(payload.get('seeking_treatment_timing')),
        condom_demo_sessions=_int(payload.get('condom_demo_sessions')),
        condoms_distributed=_int(payload.get('condoms_distributed')),
        sti_counselling_provided=_bool(payload.get('sti_counselling_provided')),
        partner_management=_str(payload.get('partner_management')),
        # Referrals
        referral_tb=_bool(payload.get('referral_tb')),
        referral_sti_kp=_bool(payload.get('referral_sti_kp')),
        referral_sti_partner=_bool(payload.get('referral_sti_partner')),
        referral_general_health=_bool(payload.get('referral_general_health')),
        referral_hiv_testing=_bool(payload.get('referral_hiv_testing')),
        referral_mental_health=_bool(payload.get('referral_mental_health')),
        referral_diabetic=_bool(payload.get('referral_diabetic')),
        referral_fp=_bool(payload.get('referral_fp')),
        follow_up_due_date=_date(payload.get('follow_up_due_date')),
        follow_up_done_date=_date(payload.get('follow_up_done_date')),
        adr_monitoring=_bool(payload.get('adr_monitoring')),
        prepared_by=_str(payload.get('prepared_by')),
        pregnancy_status=_str(payload.get('pregnancy_status')),
        anc_status=_str(payload.get('anc_status')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_hiv_sti_test(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(HIVSTITestResult, payload):
        return HttpResponse('OK', status=200)
    client = _get_or_create_client(payload, center, org)

    # Optional link to prior clinic visit from this session
    clinic_visit = None
    cv_id = _str(payload.get('clinic_visit_kobo_id'))
    if cv_id:
        clinic_visit = ClinicVisit.objects.filter(kobo_submission_id=cv_id).first()

    HIVSTITestResult.objects.create(
        organisation=org, center=center, client=client,
        clinic_visit=clinic_visit,
        testing_date=_date(payload.get('testing_date')) or timezone.now().date(),
        lab_id=_str(payload.get('lab_id')),
        hiv_result=_str(payload.get('hiv_result'), HIVSTITestResult.NOT_DONE),
        syphilis_result=_str(payload.get('syphilis_result'), HIVSTITestResult.NOT_DONE),
        hep_b_result=_str(payload.get('hep_b_result'), HIVSTITestResult.NOT_DONE),
        hep_c_result=_str(payload.get('hep_c_result'), HIVSTITestResult.NOT_DONE),
        in_window_period=_bool(payload.get('in_window_period')),
        retest_date=_date(payload.get('retest_date')),
        art_linkage_status=_str(payload.get('art_linkage_status')),
        counsellor_name=_str(payload.get('counsellor_name')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_adr_record(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(ADRRecord, payload):
        return HttpResponse('OK', status=200)
    client = _get_or_create_client(payload, center, org)

    ADRRecord.objects.create(
        organisation=org, center=center, client=client,
        report_date=_date(payload.get('report_date')) or timezone.now().date(),
        drugs_given=_str(payload.get('drugs_given')),
        followup_date=_date(payload.get('followup_date')),
        adverse_effect_present=_bool(payload.get('adverse_effect_present')),
        adverse_effect_description=_str(payload.get('adverse_effect_description')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_autoclave_log(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(AutoclaveLog, payload):
        return HttpResponse('OK', status=200)

    AutoclaveLog.objects.create(
        organisation=org, center=center,
        log_date=_date(payload.get('log_date')) or timezone.now().date(),
        log_type=_str(payload.get('log_type'), AutoclaveLog.AUTOCLAVE),
        items_autoclaved=_str(payload.get('items_autoclaved')),
        temp_121_achieved=_nullable_bool(payload, 'temp_121_achieved'),
        tape_test_passed=_nullable_bool(payload, 'tape_test_passed'),
        done_by=_str(payload.get('done_by')),
        material_type=_str(payload.get('material_type')),
        quantity=_str(payload.get('quantity')),
        supervised_by=_str(payload.get('supervised_by')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_antenatal_card(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(AntenatalCard, payload):
        return HttpResponse('OK', status=200)
    client = _get_or_create_client(payload, center, org)

    AntenatalCard.objects.create(
        organisation=org, center=center, client=client,
        visit_date=_date(payload.get('visit_date')) or timezone.now().date(),
        anc_visit_number=_int(payload.get('anc_visit_number'), 1),
        trimester=_str(payload.get('trimester')),
        lmp_date=_date(payload.get('lmp_date')),
        edd=_date(payload.get('edd')),
        blood_pressure=_str(payload.get('blood_pressure')),
        weight_kg=_decimal(payload.get('weight_kg')),
        referred=_bool(payload.get('referred')),
        referred_to=_str(payload.get('referred_to')),
        prepared_by=_str(payload.get('prepared_by')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_htc_counselling(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(HTCCounselling, payload):
        return HttpResponse('OK', status=200)
    client = _get_or_create_client(payload, center, org)

    HTCCounselling.objects.create(
        organisation=org, center=center, client=client,
        session_type=_str(payload.get('session_type'), HTCCounselling.PRE),
        session_date=_date(payload.get('session_date')) or timezone.now().date(),
        age_at_session=_int_or_none(payload.get('age_at_session')),
        partner_count=_str(payload.get('partner_count')),
        condom_use=_str(payload.get('condom_use')),
        needle_sharing=_nullable_bool(payload, 'needle_sharing'),
        blood_transfusion=_nullable_bool(payload, 'blood_transfusion'),
        partner_hiv_positive=_str(payload.get('partner_hiv_positive')),
        client_pregnant=_nullable_bool(payload, 'client_pregnant'),
        pregnancy_trimester=_str(payload.get('pregnancy_trimester')),
        covered_hiv_sti_prevention=_bool(payload.get('covered_hiv_sti_prevention')),
        covered_risk_assessment=_bool(payload.get('covered_risk_assessment')),
        covered_behavior_change=_bool(payload.get('covered_behavior_change')),
        covered_support_systems=_bool(payload.get('covered_support_systems')),
        client_consented=_bool(payload.get('client_consented')),
        counsellor_name=_str(payload.get('counsellor_name')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_individual_counselling(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(IndividualCounselling, payload):
        return HttpResponse('OK', status=200)
    client = _get_or_create_client(payload, center, org)

    IndividualCounselling.objects.create(
        organisation=org, center=center, client=client,
        session_date=_date(payload.get('session_date')) or timezone.now().date(),
        counsellor_name=_str(payload.get('counsellor_name')),
        issue_sti=_bool(payload.get('issue_sti')),
        issue_general_health=_bool(payload.get('issue_general_health')),
        issue_fp=_bool(payload.get('issue_fp')),
        issue_drug_use=_bool(payload.get('issue_drug_use')),
        issue_psychosocial=_bool(payload.get('issue_psychosocial')),
        issue_gbv=_bool(payload.get('issue_gbv')),
        issue_other=_bool(payload.get('issue_other')),
        condom_distributed=_int(payload.get('condom_distributed')),
        iec_materials=_int(payload.get('iec_materials')),
        referral_mental_health=_bool(payload.get('referral_mental_health')),
        referral_legal=_bool(payload.get('referral_legal')),
        referral_htc=_bool(payload.get('referral_htc')),
        referral_gbv=_bool(payload.get('referral_gbv')),
        drug_habit_noted=_bool(payload.get('drug_habit_noted')),
        drug_names=_str(payload.get('drug_names')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_mh_screening(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(MHScreening, payload):
        return HttpResponse('OK', status=200)
    client = _get_or_create_client(payload, center, org)

    # Item responses: KoboToolbox form names items mh_q1 … mh_q30
    item_responses = {
        f'q{i}': _int(payload[f'mh_q{i}'])
        for i in range(1, 31)
        if payload.get(f'mh_q{i}') is not None
    }

    MHScreening.objects.create(
        organisation=org, center=center, client=client,
        screening_type=_str(payload.get('screening_type'), MHScreening.DEPRESSION),
        screening_date=_date(payload.get('screening_date')) or timezone.now().date(),
        psycho_number=_str(payload.get('psycho_number')),
        counsellor_name=_str(payload.get('counsellor_name')),
        total_score=_decimal(payload.get('total_score')),
        severity_category=_str(payload.get('severity_category')),
        item_responses=item_responses,
        referred_for_counselling=_bool(payload.get('referred_for_counselling')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_gbv_case(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(GBVCase, payload):
        return HttpResponse('OK', status=200)

    GBVCase.objects.create(
        organisation=org, center=center,
        interview_date=_date(payload.get('interview_date')) or timezone.now().date(),
        incident_date=_date(payload.get('incident_date')) or timezone.now().date(),
        # Encrypted PII — EncryptedCharField handles encryption on save
        survivor_name=_str(payload.get('survivor_name')),
        survivor_contact=_str(payload.get('survivor_contact')),
        survivor_address=_str(payload.get('survivor_address')),
        perpetrator_name=_str(payload.get('perpetrator_name')),
        perpetrator_address=_str(payload.get('perpetrator_address')),
        # Non-PII demographics
        survivor_age=_int_or_none(payload.get('survivor_age')),
        survivor_gender_identity=_str(payload.get('survivor_gender_identity')),
        survivor_disability=_bool(payload.get('survivor_disability')),
        # Violence types (multi-select)
        gbv_sexual=_bool(payload.get('gbv_sexual')),
        gbv_physical=_bool(payload.get('gbv_physical')),
        gbv_economic=_bool(payload.get('gbv_economic')),
        gbv_psychological=_bool(payload.get('gbv_psychological')),
        # Perpetrator
        perpetrator_count=_int(payload.get('perpetrator_count'), 1),
        perpetrator_gender=_str(payload.get('perpetrator_gender')),
        perpetrator_relationship=_str(payload.get('perpetrator_relationship')),
        prior_reporting=_bool(payload.get('prior_reporting')),
        prior_gbv_history=_bool(payload.get('prior_gbv_history')),
        # Services needed
        needs_medical=_bool(payload.get('needs_medical')),
        needs_legal=_bool(payload.get('needs_legal')),
        needs_shelter=_bool(payload.get('needs_shelter')),
        needs_psychosocial=_bool(payload.get('needs_psychosocial')),
        local_action_taken=_str(payload.get('local_action_taken')),
        case_officer_name=_str(payload.get('case_officer_name')),
        supervisor_name=_str(payload.get('supervisor_name')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_outreach_session(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(OutreachSession, payload):
        return HttpResponse('OK', status=200)

    OutreachSession.objects.create(
        organisation=org, center=center,
        session_date=_date(payload.get('session_date')) or timezone.now().date(),
        peer_educator_name=_str(payload.get('peer_educator_name', 'Unknown')),
        spot_name=_str(payload.get('spot_name')),
        individual_contacts=_int(payload.get('individual_contacts')),
        individual_health_edu_count=_int(payload.get('individual_health_edu_count')),
        group_health_edu_count=_int(payload.get('group_health_edu_count')),
        condoms_distributed_free=_int(payload.get('condoms_distributed_free')),
        lubricants_distributed_free=_int(payload.get('lubricants_distributed_free')),
        iec_bcc_materials_distributed=_int(payload.get('iec_bcc_materials_distributed')),
        hiv_aids_sti_knowledge_sessions=_int(payload.get('hiv_aids_sti_knowledge_sessions')),
        gbv_sessions=_int(payload.get('gbv_sessions')),
        referral_mental_health=_int(payload.get('referral_mental_health')),
        referral_legal_services=_int(payload.get('referral_legal_services')),
        referral_htc_hts=_int(payload.get('referral_htc_hts')),
        referral_gbv=_int(payload.get('referral_gbv')),
        referral_other=_int(payload.get('referral_other')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_group_education(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(GroupEducationSession, payload):
        return HttpResponse('OK', status=200)

    GroupEducationSession.objects.create(
        organisation=org, center=center,
        session_date=_date(payload.get('session_date')) or timezone.now().date(),
        spot_name=_str(payload.get('spot_name')),
        facilitator_name=_str(payload.get('facilitator_name')),
        topic=_str(payload.get('topic', 'Health Education')),
        participant_count=_int(payload.get('participant_count')),
        male_count=_int(payload.get('male_count')),
        female_count=_int(payload.get('female_count')),
        tg_count=_int(payload.get('tg_count')),
        duration_minutes=_int_or_none(payload.get('duration_minutes')),
        materials_distributed=_int(payload.get('materials_distributed')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_referral(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(Referral, payload):
        return HttpResponse('OK', status=200)
    client = _get_or_create_client(payload, center, org)

    Referral.objects.create(
        organisation=org, center=center, client=client,
        referral_date=_date(payload.get('referral_date')) or timezone.now().date(),
        referral_type=_str(payload.get('referral_type'), Referral.OTHER),
        referral_reason=_str(payload.get('referral_reason')),
        referred_to=_str(payload.get('referred_to')),
        referred_by_name=_str(payload.get('referred_by_name')),
        referred_by_designation=_str(payload.get('referred_by_designation')),
        follow_up_date=_date(payload.get('follow_up_date')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_hygiene_kit(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(SafetyHygieneKit, payload):
        return HttpResponse('OK', status=200)

    # Client is optional for kit distribution
    client = None
    client_id = _str(payload.get('client_id'))
    if client_id:
        client = Client.objects.filter(client_id=client_id).first()

    SafetyHygieneKit.objects.create(
        organisation=org, center=center, client=client,
        distribution_date=_date(payload.get('distribution_date')) or timezone.now().date(),
        condom_count=_int(payload.get('condom_count')),
        condom_demo=_bool(payload.get('condom_demo')),
        awareness_session=_bool(payload.get('awareness_session')),
        iec_distributed=_int(payload.get('iec_distributed')),
        clinical_service_provided=_bool(payload.get('clinical_service_provided')),
        counselling_provided=_bool(payload.get('counselling_provided')),
        referral_done=_bool(payload.get('referral_done')),
        group_session=_bool(payload.get('group_session')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_training_event(payload, lat, lng):
    org = _org(payload)
    if _already_exists(TrainingEvent, payload):
        return HttpResponse('OK', status=200)
    # Center is optional for training events (may be at an external venue)
    center = _get_center(payload, org)

    TrainingEvent.objects.create(
        organisation=org, center=center,
        event_date=_date(payload.get('event_date')) or timezone.now().date(),
        event_end_date=_date(payload.get('event_end_date')),
        event_type=_str(payload.get('event_type'), TrainingEvent.TRAINING),
        participant_type=_str(payload.get('participant_type'), TrainingEvent.MIXED),
        topic=_str(payload.get('topic', 'Training')),
        location_text=_str(payload.get('location_text')),
        district=_str(payload.get('district')),
        total_participants=_int(payload.get('total_participants')),
        male_participants=_int(payload.get('male_participants')),
        female_participants=_int(payload.get('female_participants')),
        tg_participants=_int(payload.get('tg_participants')),
        facilitator=_str(payload.get('facilitator')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_coord_meeting(payload, lat, lng):
    org = _org(payload)
    if _already_exists(CoordMeeting, payload):
        return HttpResponse('OK', status=200)
    # Center is optional
    center = _get_center(payload, org)

    CoordMeeting.objects.create(
        organisation=org, center=center,
        meeting_date=_date(payload.get('meeting_date')) or timezone.now().date(),
        meeting_type=_str(payload.get('meeting_type'), CoordMeeting.INTERNAL),
        location_text=_str(payload.get('location_text')),
        district=_str(payload.get('district')),
        participant_count=_int(payload.get('participant_count')),
        agenda=_str(payload.get('agenda')),
        key_decisions=_str(payload.get('key_decisions')),
        prepared_by=_str(payload.get('prepared_by')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _handle_mobile_camp(payload, lat, lng):
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(MobileHealthCamp, payload):
        return HttpResponse('OK', status=200)

    MobileHealthCamp.objects.create(
        organisation=org, center=center,
        camp_date=_date(payload.get('camp_date')) or timezone.now().date(),
        location_text=_str(payload.get('location_text')),
        brothel_name=_str(payload.get('brothel_name')),
        clients_served=_int(payload.get('clients_served')),
        hiv_tests_done=_int(payload.get('hiv_tests_done')),
        sti_screenings_done=_int(payload.get('sti_screenings_done')),
        counselling_sessions=_int(payload.get('counselling_sessions')),
        referrals_made=_int(payload.get('referrals_made')),
        condoms_distributed=_int(payload.get('condoms_distributed')),
        services_description=_str(payload.get('services_description')),
        team_members=_str(payload.get('team_members')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


# ─── KF-01 Client Registration ────────────────────────────────────────────────

def _handle_client_reg(payload: dict, lat: float | None, lng: float | None) -> HttpResponse:
    """
    KF-01 Client Registration — creates or updates the full Client record.

    Unlike service delivery forms, client registration does NOT go through the
    approval workflow (no approval_status field on Client).  The record is
    written directly.  If a stub Client already exists (created by a prior
    service delivery submission with the same client_id), it is updated with
    the full demographic data.
    """
    org = _org(payload)
    if not org:
        return HttpResponse('Bad Request — organisation could not be resolved', status=400)

    center = _get_center(payload, org)
    if not center:
        return HttpResponse('Bad Request — no active ServiceCenter for this organisation', status=400)

    client_id = _str(payload.get('client_id'))
    if not client_id:
        return HttpResponse('Bad Request — client_id required', status=400)

    # Check idempotency by kobo_submission_id
    kobo_id = str(payload.get('_id', ''))
    if kobo_id and Client.objects.filter(kobo_submission_id=kobo_id).exists():
        return HttpResponse('OK', status=200)

    full_data: dict = {
        'organisation': org,
        'center': center,
        'name': _str(payload.get('client_name')),
        'mother_name': _str(payload.get('mother_name')),
        'father_name': _str(payload.get('father_name')),
        'birth_year': _int_or_none(payload.get('birth_year')),
        'gender': _str(payload.get('gender')),
        'target_group_code': _str(payload.get('target_group_code')),
        'current_address': _str(payload.get('current_address')),
        'spot_name': _str(payload.get('spot_name')),
        'uses_fp_method': _nullable_bool(payload, 'uses_fp_method'),
        'has_nid': _nullable_bool(payload, 'has_nid'),
        'enrolled_date': _date(payload.get('enrolled_date')),
        'notes': _str(payload.get('notes')),
        'current_status': Client.ACTIVE,
        # Approval workflow — KF-01 requires manager approval
        'approval_status': Client.PENDING,
        'kobo_submission_id': kobo_id or None,
        'submitted_by_kobo_user': _str(payload.get('_submitted_by')),
        'latitude': lat,
        'longitude': lng,
        'raw_payload': payload,
    }

    client, created = Client.objects.update_or_create(
        client_id=client_id,
        defaults=full_data,
    )
    action = 'registered' if created else 'updated'
    logger.info('Client %s: %s [%s] → PENDING approval', action, client_id, org)
    return HttpResponse('Created' if created else 'OK', status=201 if created else 200)


# ─── Stock & IEC handlers (models existed; handlers added for the combined
#     Activity & Operations form) ──────────────────────────────────────────────

def _handle_stock_entry(payload, lat, lng):
    """Monthly stock summary. StockEntry is a plain TimestampedModel (no GPS /
    SubmissionBase audit columns), so idempotency is on the natural key
    (center, reporting_month, item_name) via update_or_create — not on
    kobo_submission_id."""
    org = _org(payload)
    center = _get_center(payload, org)
    if not center:
        return HttpResponse('center not found', status=400)
    item_name = _str(payload.get('item_name'))
    if not item_name:
        return HttpResponse('Bad Request — item_name required', status=400)
    rmonth = _date(payload.get('reporting_month')) or timezone.now().date()
    rmonth = rmonth.replace(day=1)  # normalise to first of month

    StockEntry.objects.update_or_create(
        center=center, reporting_month=rmonth, item_name=item_name,
        defaults={
            'organisation': org,
            'item_category': _str(payload.get('item_category'), StockEntry.OTHER),
            'batch_number': _str(payload.get('batch_number')),
            'expiry_date': _date(payload.get('expiry_date')),
            'delivery_challan_no': _str(payload.get('delivery_challan_no')),
            'opening_balance': _int(payload.get('opening_balance')),
            'quantity_received': _int(payload.get('quantity_received')),
            'quantity_issued': _int(payload.get('quantity_issued')),
            'quantity_expired_lost': _int(payload.get('quantity_expired_lost')),
            'notes': _str(payload.get('notes')),
            'approval_status': StockEntry.PENDING,
        },
    )
    return HttpResponse('Created', status=201)


def _handle_iec_material(payload, lat, lng):
    """IEC / SBCC material installation (message boards, signboards, billboards,
    posters …). Feeds PHD indicators 3.1a–d. IECMaterial is SubmissionBase, so
    it uses the standard audit kwargs + the approval queue."""
    org = _org(payload)
    if not org:
        return HttpResponse('Bad Request — organisation could not be resolved', status=400)
    center = _get_center(payload, org)  # nullable FK; fallback is fine
    if _already_exists(IECMaterial, payload):
        return HttpResponse('OK', status=200)

    from partners.models import Partner
    partner = Partner.objects.filter(code=org).first()
    if partner is None:
        return HttpResponse('Bad Request — partner not found for IEC material', status=400)

    IECMaterial.objects.create(
        partner=partner, center=center, organisation=org,
        material_type=_str(payload.get('material_type'), IECMaterial.OTHER),
        quantity=_int(payload.get('quantity')),
        date_distributed=_date(payload.get('date_distributed')) or timezone.now().date(),
        district=_str(payload.get('district')),
        notes=_str(payload.get('notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


# ─── Combined-form dispatchers ─────────────────────────────────────────────────
#
# Per the 3-form consolidation (registration + patient-service + activity-ops),
# the two combined forms each carry an in-form selector and prefix every section
# field with "<section>__". The dispatcher reads the selector, un-prefixes the
# active section back to the flat field names the proven single-form handlers
# expect, and delegates. NO change to the existing handlers.
#
# route value → (field_prefix, handler, primary_name_field)
#   primary_name_field receives the shared enumerator_name when the section's own
#   identity field is blank, so "who filled it" is always captured even with
#   anonymous (login-less) submission.

_PATIENT_SERVICE_ROUTES = {
    'clinic':      ('clinic',      _handle_clinic_visit,           'prepared_by'),
    'htc':         ('htc',         _handle_hiv_sti_test,           'counsellor_name'),
    'counselling': ('counselling', _handle_individual_counselling, 'counsellor_name'),
    'mh':          ('mh',          _handle_mh_screening,           'counsellor_name'),
    'gbv':         ('gbv',         _handle_gbv_case,               'case_officer_name'),
    'referral':    ('referral',    _handle_referral,               'referred_by_name'),
}

_ACTIVITY_ROUTES = {
    'outreach':  ('outreach',  _handle_outreach_session, 'peer_educator_name'),
    'group_edu': ('group_edu', _handle_group_education,  'facilitator_name'),
    'training':  ('training',  _handle_training_event,   'facilitator'),
    'meeting':   ('meeting',   _handle_coord_meeting,    'prepared_by'),
    'camp':      ('camp',      _handle_mobile_camp,      'team_members'),
    'stock':     ('stock',     _handle_stock_entry,      None),
    'iec':       ('iec',       _handle_iec_material,     None),
}


def _unprefix(payload: dict, prefix: str) -> dict:
    """Flatten a combined-form payload to one section. Keeps shared/system keys
    (those without a "__" separator, e.g. client_id, center_code, _id,
    _geolocation, _submitted_by) and strips "<prefix>__" off this section's
    fields. Other sections' prefixed fields are dropped."""
    p = prefix + '__'
    sub: dict = {}
    for k, v in payload.items():
        if k.startswith(p):
            sub[k[len(p):]] = v
        elif '__' not in k:
            sub[k] = v
    return sub


def _dispatch_combined(payload, lat, lng, selector_key: str, routes: dict):
    selection = _str(payload.get(selector_key))
    route = routes.get(selection)
    if not route:
        logger.warning('Combined webhook: unknown %s=%r', selector_key, selection)
        return HttpResponse(f'Bad Request — unknown {selector_key}: {selection!r}', status=400)
    prefix, handler, name_field = route
    sub = _unprefix(payload, prefix)
    # "Who populated it" — stamp the shared enumerator name into the section's
    # natural identity field when the field worker left it blank.
    enumerator = _str(payload.get('enumerator_name'))
    if name_field and enumerator and not _str(sub.get(name_field)):
        sub[name_field] = enumerator
    return handler(sub, lat, lng)


def _handle_patient_service(payload, lat, lng):
    """Form 2 — routes on service_type to the patient-level handlers."""
    return _dispatch_combined(payload, lat, lng, 'service_type', _PATIENT_SERVICE_ROUTES)


def _handle_activity_ops(payload, lat, lng):
    """Form 3 — routes on activity_type to the operational handlers."""
    return _dispatch_combined(payload, lat, lng, 'activity_type', _ACTIVITY_ROUTES)


# ─── Dispatch table ────────────────────────────────────────────────────────────

# Keys are the XLS form id_string values (set in KoboToolbox form settings).
# Phase 5 XLS forms MUST use these exact id_strings for routing to work.

def _lazy_phd(name):
    """Lazy import to avoid circular dependency (phd_handlers imports from webhook)."""
    def wrapper(payload, lat, lng):
        from . import phd_handlers
        return getattr(phd_handlers, name)(payload, lat, lng)
    return wrapper


def _lazy_ciprb(name):
    """Lazy import — keeps webhook.py import-cycle-free."""
    def wrapper(payload, lat, lng):
        from . import ciprb_handlers
        return getattr(ciprb_handlers, name)(payload, lat, lng)
    return wrapper


def _lazy_bandhu(name):
    """Lazy import — bandhu_handlers imports from webhook."""
    def wrapper(payload, lat, lng):
        from . import bandhu_handlers
        return getattr(bandhu_handlers, name)(payload, lat, lng)
    return wrapper


def _lazy_nil(name):
    """Lazy import — nil_handlers imports from webhook."""
    def wrapper(payload, lat, lng):
        from . import nil_handlers
        return getattr(nil_handlers, name)(payload, lat, lng)
    return wrapper


def _lazy_fistula(name):
    """Lazy import — fistula.webhook_handlers imports from programs.models."""
    def wrapper(payload, lat, lng):
        from fistula import webhook_handlers
        return getattr(webhook_handlers, name)(payload, lat, lng)
    return wrapper


FORM_HANDLERS: dict = {
    # ── CIPRB Phase 2 — 9 new forms (Fistula QB, MPDSR 1/2/4/5, Social
    #    Autopsy, 2 notification slips, Maternal Near Miss). ──
    'ciprb_fistula_questions_v1':
        _lazy_ciprb('handle_ciprb_fistula'),
    # Daily CHW-activity campaign form — the rebuilt form is a DAILY
    # activity/reach report (households visited, population covered, staff/focal
    # head-counts, suspected/diagnosed/referral/surgery/rehab counts), NOT
    # individual patient registration. Each submission → one FistulaCampaign row
    # (PENDING for single-stage CIPRB approval).
    'ciprb_fistula_campaign_v1':
        _lazy_fistula('handle_ciprb_fistula_campaign'),
    'ciprb_mpdsr_community_maternal_v1':
        _lazy_ciprb('handle_ciprb_mpdsr_community_maternal'),
    'ciprb_mpdsr_community_neonatal_v1':
        _lazy_ciprb('handle_ciprb_mpdsr_community_neonatal'),
    'ciprb_mpdsr_facility_maternal_v1':
        _lazy_ciprb('handle_ciprb_mpdsr_facility_maternal'),
    'ciprb_mpdsr_facility_neonatal_v1':
        _lazy_ciprb('handle_ciprb_mpdsr_facility_neonatal'),
    'ciprb_social_autopsy_v1':
        _lazy_ciprb('handle_ciprb_social_autopsy'),
    'ciprb_notification_slip_01_v1':
        _lazy_ciprb('handle_ciprb_notification_slip_01'),
    'ciprb_notification_slip_02_v1':
        _lazy_ciprb('handle_ciprb_notification_slip_02'),
    'ciprb_near_miss_v1':
        _lazy_ciprb('handle_ciprb_near_miss'),
    # Safe Surgery Checklist (CIPRB 11) — one WHO Surgical Safety Checklist per
    # operation; phase completion scored on ingestion (→ SurgeryChecklist).
    'ciprb_safe_surgery_v1':
        _lazy_ciprb('handle_ciprb_safe_surgery'),
    # MPDSR Action Plan (CIPRB 10) — staged per-action tracker (new_plan / update).
    'ciprb_mpdsr_response_plan_v1':
        _lazy_ciprb('handle_ciprb_mpdsr_action_plan'),
    # ── PHD consolidated forms (new, from final source files) ──────────────────
    # ── Bandhu consolidated forms (faithful from UNFPA Tools.xlsx) ─────────────
    'bandhu_mother_list_v1':    _lazy_bandhu('handle_bandhu_mother_list'),
    'bandhu_service_log_v1':    _lazy_bandhu('handle_bandhu_service_log'),
    'bandhu_activity_ops_v1':   _lazy_bandhu('handle_bandhu_activity_ops'),

    # ── Shared "No Reporting Today" form (any centre, any partner). ──
    'no_report_v1':             _lazy_nil('handle_no_report'),
    # ── PHD consolidated forms (new, from final source files) ─────────────────
    'phd_registration_v1':      _lazy_phd('handle_phd_registration'),
    'phd_service_log_v1':       _lazy_phd('handle_phd_service_log'),
    # Legacy 3-form variants — kept registered so any in-flight submissions
    # from the old Forms 2 & 3 still route correctly during transition.
    'phd_patient_services_v1':  _lazy_phd('handle_phd_patient_services'),
    'phd_activity_ops_v1':      _lazy_phd('handle_phd_activity_ops'),
    # ── PHD 3-form consolidation (registration + 2 combined forms) ──
    'spondon_client_reg_v1':       _handle_client_reg,
    'spondon_patient_service_v1':  _handle_patient_service,
    'spondon_activity_ops_v1':     _handle_activity_ops,
    # ── Legacy single-purpose forms (still routable) ──
    'spondon_clinic_visit_v1':   _handle_clinic_visit,
    'spondon_hiv_sti_test_v1':   _handle_hiv_sti_test,
    'spondon_adr_record_v1':     _handle_adr_record,
    'spondon_autoclave_log_v1':  _handle_autoclave_log,
    'spondon_antenatal_card_v1': _handle_antenatal_card,
    'spondon_htc_counsel_v1':    _handle_htc_counselling,
    'spondon_counselling_v1':    _handle_individual_counselling,
    'spondon_mh_screening_v1':   _handle_mh_screening,
    'spondon_gbv_case_v1':       _handle_gbv_case,
    'spondon_outreach_v1':       _handle_outreach_session,
    'spondon_group_edu_v1':      _handle_group_education,
    'spondon_referral_v1':       _handle_referral,
    'spondon_hygiene_kit_v1':    _handle_hygiene_kit,
    'spondon_training_event_v1': _handle_training_event,
    'spondon_coord_meeting_v1':  _handle_coord_meeting,
    'spondon_mobile_camp_v1':    _handle_mobile_camp,
    # Legacy spondon_fistula_corner_v1 / spondon_fistula_campaign_v1 routes
    # REMOVED 2026-06-20 — CIPRB fistula now lives entirely in CIPRBFistulaCase
    # (Question Bank ciprb_fistula_questions_v1 + Campaign ciprb_fistula_campaign_v1,
    # registered above). No legacy fistula forms.
}

# Fallback: map KoboToolbox asset UIDs → form slugs.
# Some KoboToolbox deployments send the asset UID as _xform_id_string
# instead of the XLS settings id_string.  This table lets the webhook
# resolve the handler even when the slug-based URL isn't used.
_ASSET_UID_TO_SLUG: dict[str, str] = {}

def _build_uid_map() -> None:
    """Populate from Django settings at first request (lazy)."""
    from django.conf import settings as _s
    uid_pairs = [
        ('KOBO_ASSET_UID_CLIENT_REG',   'spondon_client_reg_v1'),
        ('KOBO_ASSET_UID_CLINIC_VISIT', 'spondon_clinic_visit_v1'),
        ('KOBO_ASSET_UID_HIV_STI',      'spondon_hiv_sti_test_v1'),
        ('KOBO_ASSET_UID_ADR',          'spondon_adr_record_v1'),
        ('KOBO_ASSET_UID_AUTOCLAVE',    'spondon_autoclave_log_v1'),
        ('KOBO_ASSET_UID_ANC',          'spondon_antenatal_card_v1'),
        ('KOBO_ASSET_UID_HTC',          'spondon_htc_counsel_v1'),
        ('KOBO_ASSET_UID_COUNSELLING',  'spondon_counselling_v1'),
        ('KOBO_ASSET_UID_MH_SCREEN',    'spondon_mh_screening_v1'),
        ('KOBO_ASSET_UID_GBV',          'spondon_gbv_case_v1'),
        ('KOBO_ASSET_UID_OUTREACH',     'spondon_outreach_v1'),
        ('KOBO_ASSET_UID_GROUP_EDU',    'spondon_group_edu_v1'),
        ('KOBO_ASSET_UID_REFERRAL',     'spondon_referral_v1'),
        ('KOBO_ASSET_UID_HYGIENE',      'spondon_hygiene_kit_v1'),
        ('KOBO_ASSET_UID_TRAINING',     'spondon_training_event_v1'),
        ('KOBO_ASSET_UID_COORD_MTG',    'spondon_coord_meeting_v1'),
        ('KOBO_ASSET_UID_MOBILE_CAMP',  'spondon_mobile_camp_v1'),
        # Legacy submission-app UIDs
        ('KOBO_ASSET_UID_MPDSR',        'spondon_mpdsr_combined_v1'),
        ('KOBO_ASSET_UID_FISTULA',      'spondon_fistula_v1'),
        ('KOBO_ASSET_UID_BASELINE',     'spondon_baseline_v1'),
        ('KOBO_ASSET_UID_ACTIVITY',     'spondon_client_reg_v1'),
    ]
    for attr, slug in uid_pairs:
        uid = getattr(_s, attr, '') or ''
        if uid:
            _ASSET_UID_TO_SLUG[uid] = slug


# ─── Telegram notification ─────────────────────────────────────────────────────

def _notify(org: str, form_label: str, kobo_id: str) -> None:
    """
    Send a lightweight new-submission alert to the org's Telegram chat.
    Mirrors the pattern in submissions/telegram.py.
    """
    import json as _json
    import requests as _requests
    from django.conf import settings as _settings

    # Email the partner's managers/focal that a new submission is awaiting
    # review (operational forms now alert just like the KoboSubmission path).
    try:
        from submissions.email_notify import _recipients_for, _send
        recipients = _recipients_for(org)
        if recipients:
            _send(
                f'[SIMPLE] New {form_label} submission — {org}',
                f'A new {form_label} submission from {org} is awaiting review.\n\n'
                f'Open SIMPLE to review and approve:\n'
                f'{getattr(_settings, "SIMPLE_PUBLIC_URL", "")}/approvals',
                recipients,
            )
    except Exception as exc:
        logger.error('Programs webhook email error: %s', exc)

    token = getattr(_settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token:
        return
    try:
        chat_ids = _json.loads(getattr(_settings, 'TELEGRAM_CHAT_IDS', '{}'))
    except Exception:
        return

    chat_id = chat_ids.get(org)
    if not chat_id:
        return

    text = (
        f'<b>New Submission — {form_label}</b>\n\n'
        f'Organisation: {org}\n'
        f'KoboToolbox ID: {kobo_id}\n\n'
        f'<i>Open SIMPLE to review and approve.</i>'
    )
    try:
        _requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            timeout=5,
        ).raise_for_status()
    except Exception as exc:
        logger.error('Programs webhook Telegram error: %s', exc)


# ─── Webhook view ──────────────────────────────────────────────────────────────

_FORM_LABELS = {
    'phd_registration_v1':      'PHD — FSW Registration',
    'phd_service_log_v1':       'PHD — Service Log',
    'phd_patient_services_v1':  'PHD — Patient Services',
    'phd_activity_ops_v1':      'PHD — Activity & Operations',
    'spondon_client_reg_v1':       'FSW Registration',
    'spondon_patient_service_v1':  'Patient Service',
    'spondon_activity_ops_v1':     'Activity & Operations',
    'spondon_clinic_visit_v1':   'Clinic Visit (KF-02)',
    'spondon_hiv_sti_test_v1':   'HIV/STI Test Result (KF-03)',
    'spondon_adr_record_v1':     'ADR Record (KF-13)',
    'spondon_autoclave_log_v1':  'Autoclave Log (KF-16)',
    'spondon_antenatal_card_v1': 'Antenatal Card (ANC)',
    'spondon_htc_counsel_v1':    'HTC Counselling (KF-04)',
    'spondon_counselling_v1':    'Individual Counselling (KF-09)',
    'spondon_mh_screening_v1':   'MH Screening (KF-05/06)',
    'spondon_gbv_case_v1':       'GBV Case',
    'spondon_outreach_v1':       'Outreach Session (KF-08)',
    'spondon_group_edu_v1':      'Group Education (KF-10)',
    'spondon_referral_v1':       'Referral',
    'spondon_hygiene_kit_v1':    'Safety & Hygiene Kit (KF-12)',
    'spondon_training_event_v1': 'Training Event (KF-20)',
    'spondon_coord_meeting_v1':  'Coordination Meeting (KF-19)',
    'spondon_mobile_camp_v1':    'Mobile Health Camp (KF-18)',
}


def _flatten_group_keys(payload: dict) -> dict:
    """Expose a group-stripped alias for every nested KoboToolbox field.

    Kobo serialises grouped questions as 'group/field' (and nested groups
    as 'a/b/field'). Every PHD/Bandhu handler reads flat leaf names like
    'id_no' or 'clinic_date', so without this they never match and the
    handler 400s ('id_no required'). We keep the original keys intact and
    add a leaf alias for each grouped key. On a leaf collision across
    groups the first occurrence wins (PHD forms use unique leaf names, so
    collisions are not expected) and we log it.

    Meta keys (_id, _xform_id_string, _geolocation, _submitted_by, …)
    contain no '/', so they pass through untouched.
    """
    if not isinstance(payload, dict):
        return payload
    flat = dict(payload)
    for key, val in payload.items():
        if '/' not in key:
            continue
        leaf = key.rsplit('/', 1)[-1]
        if not leaf:
            continue
        if leaf in flat:
            # Don't clobber a real flat key or an earlier group's leaf — BUT a
            # repeat LIST must never be shadowed by a scalar (Kobo can emit an
            # empty-string placeholder for a 0-instance repeat); prefer the list.
            if isinstance(val, list) and not isinstance(flat[leaf], list):
                flat[leaf] = val
            elif flat[leaf] != val:
                logger.debug('flatten: leaf %r collision (%r kept)', leaf, leaf)
            continue
        flat[leaf] = val
    return flat


@csrf_exempt
@require_POST
def programs_webhook(request, org_override: str = '', form_slug: str = ''):
    """
    POST /webhook/programs/                              — id_string from payload
    POST /webhook/programs/PHD/                          — force org=PHD
    POST /webhook/programs/Bandhu/                       — force org=Bandhu
    POST /webhook/programs/form/<form_slug>/             — form type from URL (recommended)

    The /form/<form_slug>/ variant is the most reliable: it bypasses
    _xform_id_string entirely, so it works even when KoboToolbox auto-generates
    its own id_string on upload.

    KoboToolbox REST Service setup (per form):
      URL:    https://<domain>/webhook/programs/form/spondon_client_reg_v1/
      Method: POST
      Header: Authorization: Token REDACTED
    """
    if not validate_kobo_signature(request):
        logger.warning(
            'Programs webhook rejected — bad signature from %s',
            request.META.get('REMOTE_ADDR'),
        )
        return HttpResponse('Forbidden', status=403)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse('Bad Request — expected JSON body', status=400)
    if not isinstance(payload, dict):
        # A non-object body (array/string/number) survives _flatten_group_keys
        # unchanged and then AttributeErrors on payload.get(...) → 500 → Kobo
        # retries forever and strands the submission. Reject cleanly.
        return HttpResponse('Bad Request — expected a JSON object', status=400)

    # KoboToolbox nests every field under its XLSForm group, e.g.
    # 'grp_fsw/id_no' rather than 'id_no'. Every handler reads flat leaf
    # names, so expose a stripped alias for each grouped key here, once,
    # centrally — this is the difference between a registration creating a
    # Client and silently 400-ing with 'id_no required'.
    payload = _flatten_group_keys(payload)

    kobo_id = str(payload.get('_id', '')).strip()
    if not kobo_id:
        return HttpResponse('Bad Request — missing _id', status=400)

    if org_override:
        payload['organisation'] = org_override
        logger.debug('Programs webhook: org forced to %r via URL', org_override)

    # form_slug in URL takes priority over _xform_id_string in payload —
    # this is the reliable path when KoboToolbox auto-generates its own id_string.
    if form_slug:
        xform_id = form_slug
        logger.debug('Programs webhook: form type %r resolved from URL slug', xform_id)
    else:
        xform_id = payload.get('_xform_id_string', '')

    handler = FORM_HANDLERS.get(xform_id)

    # Fallback: resolve KoboToolbox asset UID → form slug
    if not handler and xform_id:
        if not _ASSET_UID_TO_SLUG:
            _build_uid_map()
        resolved_slug = _ASSET_UID_TO_SLUG.get(xform_id)
        if resolved_slug:
            logger.info('Programs webhook: resolved asset UID %r → slug %r', xform_id, resolved_slug)
            xform_id = resolved_slug
            handler = FORM_HANDLERS.get(xform_id)

    if not handler:
        logger.warning('Programs webhook: unknown form id_string %r', xform_id)
        return HttpResponse(f'Bad Request — unknown form: {xform_id}', status=400)

    lat, lng = _geolocation(payload)

    try:
        response = handler(payload, lat, lng)
    except Exception as exc:
        logger.exception('Programs webhook error processing %s [%s]: %s', xform_id, kobo_id, exc)
        return HttpResponse('Internal Server Error', status=500)

    if response.status_code == 201:
        logger.info('Programs submission created: %s [%s] org=%s', kobo_id, xform_id,
                    org_override or _org(payload) or '?')
        try:
            org = org_override or _org(payload)
            # Fire the email/Telegram alert off the request thread. SMTP or
            # Telegram can be slow or unreachable from the host (observed:
            # email_notify blocking ~2 min on "Network is unreachable"), which
            # would otherwise stall the webhook response long after the row is
            # already saved — making Kobo time out and retry. The submission is
            # persisted before this point, so notification is pure side-effect.
            import threading as _threading
            _threading.Thread(
                target=_notify,
                args=(org, _FORM_LABELS.get(xform_id, xform_id), kobo_id),
                daemon=True, name='programs-notify',
            ).start()
        except Exception as exc:
            logger.error('Programs webhook notify dispatch error: %s', exc)

    return response


@csrf_exempt
@require_POST
def programs_webhook_phd(request):
    """POST /webhook/programs/PHD/ — all submissions tagged organisation='PHD'."""
    return programs_webhook(request, org_override='PHD')


@csrf_exempt
@require_POST
def programs_webhook_bondhu(request):
    """POST /webhook/programs/Bandhu/ — all submissions tagged organisation='Bandhu'."""
    return programs_webhook(request, org_override='Bandhu')


@csrf_exempt
@require_POST
def programs_webhook_by_form(request, form_slug: str):
    """
    POST /webhook/programs/form/<form_slug>/

    Identifies the form type from the URL slug rather than _xform_id_string.
    This is the recommended endpoint when KoboToolbox has auto-generated its
    own id_string and doesn't match the XLS settings sheet value.

    KoboToolbox REST Service URL per form:
      https://<domain>/webhook/programs/form/spondon_client_reg_v1/
      https://<domain>/webhook/programs/form/spondon_clinic_visit_v1/
      ... etc.
    """
    return programs_webhook(request, form_slug=form_slug)
