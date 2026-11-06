"""
Webhook handlers for the 3 consolidated PHD XLSForms.

  phd_registration_v1      → Client
  phd_patient_services_v1  → ClinicVisit | HIVSTITestResult | Referral | (counselling raw log)
  phd_activity_ops_v1      → GroupEducationSession | TrainingEvent |
                             IECMaterial | GBVCornerRecord | StockEntry
"""
import logging

from django.http import HttpResponse
from django.utils import timezone

from .webhook import (
    _str, _bool, _int, _int_or_none, _date, _nullable_bool,
    _already_exists, _base_kwargs, _get_center, _get_or_create_client,
)
from .models import (
    Client, ClinicVisit, HIVSTITestResult, Referral,
    GroupEducationSession, TrainingEvent, IECMaterial, StockEntry,
    GBVCornerRecord, PHDCounsellingReport,
)

logger = logging.getLogger(__name__)

ORG = 'PHD'


def _client_id(payload: dict) -> str:
    """Read the unified Service Log client_id and normalise it (trim + upper).
    Falls back to the legacy per-section ID fields if the unified one is
    missing — gives one deploy of overlap during the form rollover."""
    raw = (
        payload.get('client_id')
        or payload.get('clinic_id_no')
        or payload.get('htc_client_id')
        or payload.get('ref_id_no')
        or ''
    )
    return str(raw).strip().upper()


# Material name keywords → IECMaterial.material_type
_MAT_TYPE_MAP = {
    'message board': 'message_board',
    'message_board': 'message_board',
    'signboard':     'signboard',
    'sign board':    'signboard',
    'billboard':     'billboard',
    'bill board':    'billboard',
    'poster':        'poster',
    'leaflet':       'leaflet',
    'digital':       'digital',
}


def _mat_type_from_name(name: str) -> str:
    lower = name.lower()
    for kw, mtype in _MAT_TYPE_MAP.items():
        if kw in lower:
            return mtype
    return 'other'


# ─── Form 1: FSW Registration ─────────────────────────────────────────────────

def handle_phd_registration(payload: dict, lat, lng) -> HttpResponse:
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)

    # Normalise the ID at write-time the same way the Service Log
    # normalises at lookup-time (trim + upper). Guarantees that
    # '1-0001' typed in registration matches ' 1-0001 ' typed in any
    # service form's pulldata() call.
    client_id = str(payload.get('id_no', '')).strip().upper()
    if not client_id:
        return HttpResponse('Bad Request — id_no required', status=400)

    kobo_id = str(payload.get('_id', ''))
    if kobo_id and Client.objects.filter(kobo_submission_id=kobo_id).exists():
        return HttpResponse('OK', status=200)

    # First registration wins. The ID is unique per FSW, so a second
    # registration on the same id_no is a DUPLICATE — never overwrite the
    # existing record (that would silently replace one FSW's data with
    # another's). The form's hard constraint blocks duplicates already in the
    # Master List; this backstops the case the form can't see — two workers
    # inventing the same NEW id offline on the same day (the attached CSV is a
    # snapshot). get_or_create only writes `defaults` when creating.
    defaults = {
        'organisation':        ORG,
        'center':              center,
        'name':                _str(payload.get('name')),
        'mother_name':         _str(payload.get('mother_name')),
        'birth_year':          _int_or_none(payload.get('birth_year')),
        'gender':              '02',    # all PHD registrations = Female (FSW)
        'target_group_code':   '05',    # FSW
        'current_address':     _str(payload.get('permanent_address')),
        # Socioeconomic / FSW profile — previously DROPPED (the Client columns
        # exist but the handler never read them). The form sends 1-char codes
        # for education/marital_status (build_phd_forms._form1_choices).
        'marital_status':      _str(payload.get('marital_status')),
        'education_level':     _str(payload.get('education')),
        'years_in_profession': _int_or_none(payload.get('years_in_profession')),
        'avg_clients_per_day': _int_or_none(payload.get('avg_clients_per_day')),
        'children_under_18':   _int_or_none(payload.get('children_under_18')),
        'has_nid':             _nullable_bool(payload, 'has_nid'),
        'uses_fp_method':      _nullable_bool(payload, 'uses_fp'),
        'notes':               _str(payload.get('remarks')),
        'current_status':      Client.ACTIVE,
        # Registration lands PENDING — a PHD manager approves each FSW
        # enrolment in the website queue, so the registration record itself
        # gets reviewed. Field logging is NOT blocked by this: export_phd_clients
        # now includes PENDING (not only APPROVED) clients in phd_clients.csv, so
        # the Service Log's pulldata() finds her immediately after submission —
        # before the manager acts. A REJECTED registration drops back out of the
        # CSV (she stops being loggable). See export_phd_clients.build_csv().
        'approval_status':     Client.PENDING,
        'kobo_submission_id':  kobo_id or None,
        'submitted_by_kobo_user': _str(payload.get('_submitted_by')),
        'latitude':  lat,
        'longitude': lng,
        'raw_payload': payload,
    }
    client, created = Client.objects.get_or_create(
        client_id=client_id, defaults=defaults,
    )
    if not created:
        # A Service Log referencing this id may have arrived FIRST and created
        # an auto-approved STUB (name 'Unknown'/'') with no demographics — Kobo
        # does not guarantee inter-form delivery order. Registration is the
        # source of truth for identity, so UPGRADE the stub in place rather than
        # silently dropping the demographic payload (the stub is excluded from
        # phd_clients.csv by .exclude(name=''), so without this the Service Log
        # pulldata() keeps firing "not registered" forever). A real, *named*
        # existing record is a genuine duplicate — keep it (never clobber one
        # FSW with another). Return 200 so Kobo does not retry forever.
        from django.db import transaction
        with transaction.atomic():
            locked = Client.objects.select_for_update().get(pk=client.pk)
            if (locked.name or '').strip() in ('', 'Unknown'):
                for f in ('center', 'name', 'mother_name', 'birth_year',
                          'gender', 'target_group_code', 'current_address',
                          'marital_status', 'education_level',
                          'years_in_profession', 'avg_clients_per_day',
                          'children_under_18',
                          'has_nid', 'uses_fp_method', 'notes',
                          'submitted_by_kobo_user', 'latitude', 'longitude',
                          'raw_payload'):
                    setattr(locked, f, defaults[f])
                locked.current_status = Client.ACTIVE
                # Upgrading a stub IS a real registration, so it needs the
                # manager's approval too — land it PENDING, same as a fresh
                # registration above (not APPROVED).
                locked.approval_status = Client.PENDING
                locked.save()
                logger.info(
                    'PHD registration upgraded stub client %s (id_no=%s)',
                    locked.pk, client_id)   # never log the cleartext name to stdout
                return HttpResponse('Stub upgraded to full registration', status=200)
        logger.warning(
            'Duplicate PHD registration id_no=%s (kobo=%s) ignored — '
            'existing client %s (centre %s) kept.',
            client_id, kobo_id or '-', client.pk,
            client.center.code if client.center_id else '-',
        )
        return HttpResponse('Duplicate id_no — existing registration kept', status=200)
    return HttpResponse('Created', status=201)


# ─── Form 2: Patient Services ─────────────────────────────────────────────────

def _phd_clinic(payload: dict, lat, lng) -> HttpResponse:
    """clinic section → ClinicVisit (Patient Record Register)."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(ClinicVisit, payload):
        return HttpResponse('OK', status=200)

    # Resolve or create client stub — always tag as FSW (target_group_code 05)
    client_payload = {
        'client_id':   _client_id(payload),
        'client_name': '',
        'target_group_code': '05',
    }
    client = _get_or_create_client(client_payload, center, ORG)
    # Ensure existing stubs get the FSW code stamped
    if client.target_group_code != '05':
        Client.objects.filter(pk=client.pk).update(target_group_code='05')

    ClinicVisit.objects.create(
        organisation=ORG,
        center=center,
        client=client,
        visit_date=_date(payload.get('clinic_date')) or timezone.now().date(),
        visit_type=_str(payload.get('clinic_visit_type'), ClinicVisit.NEW),
        # Screenings — from Patient Record Register columns
        hiv_screening_done=_bool(payload.get('clinic_hiv_screen')),
        sti_screening_done=_bool(payload.get('clinic_syphilis_screen')),
        hep_b_screening_done=_bool(payload.get('clinic_hepb_screen')),
        hep_c_screening_done=_bool(payload.get('clinic_hepc_screen')),
        tb_screening_done=_bool(payload.get('clinic_tb_screen')),
        gbv_screening_done=_bool(payload.get('clinic_gbv_screen')),     # new field
        mh_screening_done=_bool(payload.get('clinic_mh_screen')),       # new field
        # Diagnoses
        diag_uds=_bool(payload.get('clinic_diag_uds')),
        diag_vds=_bool(payload.get('clinic_diag_vds')),
        diag_gu=_bool(payload.get('clinic_diag_gu')),
        diag_pid=_bool(payload.get('clinic_diag_pid')),
        diag_ss=_bool(payload.get('clinic_diag_ss')),
        diag_ib=_bool(payload.get('clinic_diag_ib')),
        diag_anal_sti=_bool(payload.get('clinic_diag_anal_sti')),
        diag_gh=_bool(payload.get('clinic_diag_gh')),
        # Treatment
        treatment_provided=_str(payload.get('clinic_treatment')),
        seeking_treatment_timing=_str(payload.get('clinic_treatment_timing')),
        condom_demo_sessions=_int(payload.get('clinic_condom_demo')),
        # Follow-up
        follow_up_due_date=_date(payload.get('clinic_fu_due')),
        follow_up_done_date=_date(payload.get('clinic_fu_done')),
        adr_monitoring=_bool(payload.get('clinic_adr')),
        # Referrals — 10 columns from Patient Record Register
        referral_tb=_bool(payload.get('clinic_ref_tb')),
        referral_sti_kp=_bool(payload.get('clinic_ref_sti_confirm')),
        referral_sti_partner=_bool(payload.get('clinic_ref_sti_partner')),
        referral_fp=_bool(payload.get('clinic_ref_mch')),
        referral_gbv=_bool(payload.get('clinic_ref_gbv')),              # new field
        referral_mental_health=_bool(payload.get('clinic_ref_mhpss')),  # MHPSS
        referral_general_health=_bool(payload.get('clinic_ref_gh')),
        referral_hiv_testing=_bool(payload.get('clinic_ref_sti_nonres')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _phd_htc(payload: dict, lat, lng) -> HttpResponse:
    """htc section → HIVSTITestResult (HTC Service register)."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(HIVSTITestResult, payload):
        return HttpResponse('OK', status=200)

    client_payload = {'client_id': _client_id(payload), 'client_name': ''}
    client = _get_or_create_client(client_payload, center, ORG)
    if client.target_group_code != '05':
        Client.objects.filter(pk=client.pk).update(target_group_code='05')

    HIVSTITestResult.objects.create(
        organisation=ORG,
        center=center,
        client=client,
        testing_date=_date(payload.get('htc_date')) or timezone.now().date(),
        hiv_result=_str(payload.get('htc_final_result'), HIVSTITestResult.NOT_DONE),
        syphilis_result=HIVSTITestResult.NOT_DONE,
        hep_b_result=HIVSTITestResult.NOT_DONE,
        hep_c_result=HIVSTITestResult.NOT_DONE,
        counsellor_name=_str(payload.get('enumerator_name')),
        notes=_str(payload.get('htc_remarks')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _phd_referral(payload: dict, lat, lng) -> HttpResponse:
    """referral section → Referral (Referral Register)."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(Referral, payload):
        return HttpResponse('OK', status=200)

    client_payload = {'client_id': _client_id(payload), 'client_name': ''}
    client = _get_or_create_client(client_payload, center, ORG)

    Referral.objects.create(
        organisation=ORG,
        center=center,
        client=client,
        referral_date=_date(payload.get('ref_date')) or timezone.now().date(),
        referral_type=Referral.OTHER,
        referral_reason=_str(payload.get('ref_referred_for')),
        referred_to=_str(payload.get('ref_referred_to')),
        follow_up_date=_date(payload.get('ref_followup_date')),
        notes=_str(payload.get('ref_remarks')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _phd_counselling(payload: dict, lat, lng) -> HttpResponse:
    """counselling section → PHDCounsellingReport (monthly aggregate).

    A whole monthly counselling report was previously logged and discarded.
    Persist it as a real row. It lands PENDING and a PHD manager approves it in
    the website queue before its counts feed the dashboard — every form in the
    site is reviewed (Rafi: nothing auto-approves). Idempotent via
    kobo_submission_id."""
    if _already_exists(PHDCounsellingReport, payload):
        return HttpResponse('OK', status=200)
    center = _get_center(payload, ORG)

    PHDCounsellingReport.objects.create(
        organisation=ORG,
        approval_status=PHDCounsellingReport.PENDING,
        center=center,
        report_date=_date(payload.get('counsel_date')) or timezone.now().date(),
        prepared_by=_str(payload.get('counsel_prepared_by')),
        hiv_test_count=_int(payload.get('counsel_hiv_test')),
        sti_count=_int(payload.get('counsel_sti')),
        srhr_count=_int(payload.get('counsel_srhr')),
        gbv_count=_int(payload.get('counsel_gbv')),
        art_count=_int(payload.get('counsel_art')),
        mh_count=_int(payload.get('counsel_mh')),
        total_count=_int(payload.get('counsel_total')),
        group_mh_count=_int(payload.get('counsel_group_mh')),
        note=_str(payload.get('counsel_note')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def handle_phd_patient_services(payload: dict, lat, lng) -> HttpResponse:
    stype = _str(payload.get('service_type'))
    if stype == 'clinic':
        return _phd_clinic(payload, lat, lng)
    if stype == 'htc':
        return _phd_htc(payload, lat, lng)
    if stype == 'counselling':
        # Monthly aggregate report — persisted as PHDCounsellingReport so a
        # whole monthly counselling report is no longer silently discarded.
        return _phd_counselling(payload, lat, lng)
    if stype == 'referral':
        return _phd_referral(payload, lat, lng)
    logger.warning('phd_patient_services_v1: unknown service_type=%r', stype)
    return HttpResponse(f'Bad Request — unknown service_type: {stype}', status=400)


# ─── Form 3: Activity & Operations ────────────────────────────────────────────

def _phd_group_edu(payload: dict, lat, lng) -> HttpResponse:
    """group_edu section → GroupEducationSession (SL4 outreach/education)."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    if _already_exists(GroupEducationSession, payload):
        return HttpResponse('OK', status=200)

    audience = _str(payload.get('gedu_audience'))
    # Build topic string from whichever topics were marked yes
    topic_fields = [
        'gedu_personal_hygiene', 'gedu_unsafe_sex', 'gedu_gbv',
        'gedu_hiv_sti', 'gedu_cancer_screen', 'gedu_social_safety',
        'gedu_small_business', 'gedu_safe_sex_client',
        'gedu_hiv_sti_client', 'gedu_safe_condom_drugs',
    ]
    topics = [f.replace('gedu_', '').replace('_', ' ')
              for f in topic_fields if _bool(payload.get(f))]
    topic_str = ', '.join(topics) if topics else audience

    GroupEducationSession.objects.create(
        organisation=ORG,
        center=center,
        session_date=_date(payload.get('gedu_date')) or timezone.now().date(),
        spot_name=_str(payload.get('gedu_venue')),
        facilitator_name=_str(payload.get('enumerator_name')),
        topic=topic_str,
        participant_count=_int(payload.get('gedu_participant_count')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _phd_event(payload: dict, lat, lng) -> HttpResponse:
    """event section → TrainingEvent.
    event_subtype maps to:
      training/orientation/workshop → TrainingEvent.event_type values
      camp                          → 'camp'  (SL9 mobile health camps)
      coord_meeting                 → 'coord_meeting'  (SL14)
    """
    if _already_exists(TrainingEvent, payload):
        return HttpResponse('OK', status=200)
    center = _get_center(payload, ORG)

    subtype = _str(payload.get('event_subtype', 'training')).lower()
    # Map subtype → event_type stored in DB
    etype_map = {
        'training':    TrainingEvent.TRAINING,
        'orientation': TrainingEvent.ORIENTATION,
        'workshop':    TrainingEvent.WORKSHOP,
        'camp':        'camp',
        'coord_meeting': 'coord_meeting',
    }
    event_type = etype_map.get(subtype, TrainingEvent.TRAINING)

    # participant_type — prefer the explicit category the form now captures
    # (event_participant_type) so SL10/SL11/SL12/SL13 route correctly. Fall back
    # to the old subtype-derived default for legacy submissions that predate the
    # field (those still land as HM/MIXED, unchanged behaviour).
    ptype_form_map = {
        'hm': 'HM', 'gob': 'GOB', 'mw': 'MW', 'pe': 'PE',
        'mixed': TrainingEvent.MIXED,
    }
    ptype_form = _str(payload.get('event_participant_type', '')).lower()
    if ptype_form in ptype_form_map:
        participant_type = ptype_form_map[ptype_form]
    else:
        ptype_map = {
            'orientation': 'HM',
            'camp':        TrainingEvent.MIXED,
            'coord_meeting': TrainingEvent.MIXED,
        }
        participant_type = ptype_map.get(subtype, TrainingEvent.MIXED)

    TrainingEvent.objects.create(
        organisation=ORG,
        center=center,
        event_date=_date(payload.get('event_date')) or timezone.now().date(),
        event_type=event_type,
        participant_type=participant_type,
        topic=_str(payload.get('event_title', 'Event')),
        location_text=_str(payload.get('event_place')),
        total_participants=_int(payload.get('event_participants')),
        notes=_str(payload.get('event_notes')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _phd_material(payload: dict, lat, lng) -> HttpResponse:
    """material section → IECMaterial (Material Database → SL15)."""
    if _already_exists(IECMaterial, payload):
        return HttpResponse('OK', status=200)
    center = _get_center(payload, ORG)

    from partners.models import Partner
    partner = Partner.objects.filter(code=ORG).first()
    if not partner:
        return HttpResponse('Partner PHD not found', status=400)

    mat_name = _str(payload.get('mat_name', ''))
    mat_type = _mat_type_from_name(mat_name)

    IECMaterial.objects.create(
        partner=partner,
        center=center,
        organisation=ORG,
        material_type=mat_type,
        quantity=_int(payload.get('mat_quantity')),
        date_distributed=_date(payload.get('mat_date')) or timezone.now().date(),
        district=_str(payload.get('mat_place')),
        notes=mat_name + (' — ' + _str(payload.get('mat_notes'))
                          if payload.get('mat_notes') else ''),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _phd_gbv_corner(payload: dict, lat, lng) -> HttpResponse:
    """gbv_corner section → GBVCornerRecord (GBV Corner Establishment DB → SL16)."""
    if _already_exists(GBVCornerRecord, payload):
        return HttpResponse('OK', status=200)
    center = _get_center(payload, ORG)

    GBVCornerRecord.objects.create(
        organisation=ORG,
        center=center,
        place_of_establishment=_str(payload.get('gbv_place')),
        date_of_establishment=_date(payload.get('gbv_date')) or timezone.now().date(),
        furniture_count=_int(payload.get('gbv_furniture')),
        equipment_count=_int(payload.get('gbv_equipment')),
        fully_functional=_bool(payload.get('gbv_functional')),
        **_base_kwargs(payload, lat, lng),
    )
    return HttpResponse('Created', status=201)


def _phd_stock(payload: dict, lat, lng) -> HttpResponse:
    """stock section → StockEntry (Stock Register → SL5)."""
    center = _get_center(payload, ORG)
    if not center:
        return HttpResponse('center not found', status=400)
    item_name = _str(payload.get('stock_item'))
    if not item_name:
        return HttpResponse('Bad Request — stock_item required', status=400)
    rmonth = _date(payload.get('stock_date')) or timezone.now().date()
    rmonth = rmonth.replace(day=1)

    # Accumulate across the many per-issue submissions for the same item/month
    # instead of overwriting with the last one (idempotent via submission _id).
    from .webhook import _accumulate_stock
    _accumulate_stock(
        center=center, reporting_month=rmonth, item_name=item_name, org=ORG,
        submission_id=payload.get('_id', ''),
        batch_number=_str(payload.get('stock_batch')),
        expiry_date=_date(payload.get('stock_expiry')),
        delivery_challan_no=_str(payload.get('stock_challan')),
        opening_balance=_int(payload.get('stock_opening')),
        quantity_received=_int(payload.get('stock_received')),
        quantity_issued=_int(payload.get('stock_issued')),
        quantity_expired_lost=_int(payload.get('stock_expired_lost')),
        notes=_str(payload.get('stock_comments')),
    )
    return HttpResponse('Created', status=201)


def handle_phd_activity_ops(payload: dict, lat, lng) -> HttpResponse:
    atype = _str(payload.get('activity_type'))
    dispatch = {
        'group_edu':  _phd_group_edu,
        'event':      _phd_event,
        'material':   _phd_material,
        'gbv_corner': _phd_gbv_corner,
        'stock':      _phd_stock,
    }
    fn = dispatch.get(atype)
    if fn:
        return fn(payload, lat, lng)
    logger.warning('phd_activity_ops_v1: unknown activity_type=%r', atype)
    return HttpResponse(f'Bad Request — unknown activity_type: {atype}', status=400)


# ─── Merged Service Log handler ───────────────────────────────────────────────
# Single dispatcher for the new PHD-2 Service Log form (phd_service_log_v1).
# Reads the top-level `record_type` selector and routes to the per-section
# handler. All 9 PHD service & activity types in one place.

def handle_phd_service_log(payload: dict, lat, lng) -> HttpResponse:
    rtype = _str(payload.get('record_type'))
    dispatch = {
        # Patient-level services (Patient Record, HTC, Counselling, Referral)
        'clinic':       _phd_clinic,
        'htc':          _phd_htc,
        'referral':     _phd_referral,
        # Activity & operations (Group Ed, Event, Material, GBV corner, Stock)
        'group_edu':    _phd_group_edu,
        'event':        _phd_event,
        'material':     _phd_material,
        'gbv_corner':   _phd_gbv_corner,
        'stock':        _phd_stock,
    }
    if rtype == 'counselling':
        # Monthly aggregate report — persisted as PHDCounsellingReport
        # (was previously logged and discarded). Auto-approved (a monthly
        # summary, not a per-patient record), so it counts immediately.
        return _phd_counselling(payload, lat, lng)
    fn = dispatch.get(rtype)
    if fn:
        return fn(payload, lat, lng)
    logger.warning('phd_service_log_v1: unknown record_type=%r', rtype)
    return HttpResponse(f'Bad Request — unknown record_type: {rtype}', status=400)
