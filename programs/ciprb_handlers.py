"""
Webhook handlers for the 9 CIPRB KoboToolbox forms (Phase 2).

  ciprb_fistula_questions_v1          → fistula.CIPRBFistulaCase
  ciprb_mpdsr_community_maternal_v1   → mpdsr.MPDSRCase (sub_form_type='f1')
  ciprb_mpdsr_community_neonatal_v1   → mpdsr.MPDSRCase (sub_form_type='f2')
  ciprb_mpdsr_facility_maternal_v1    → mpdsr.MPDSRCase (sub_form_type='f4')
  ciprb_mpdsr_facility_neonatal_v1    → mpdsr.MPDSRCase (sub_form_type='f5')
  ciprb_social_autopsy_v1             → mpdsr.MPDSRCase (sub_form_type='sa_md')
  ciprb_notification_slip_01_v1       → mpdsr.MPDSRDeathNotification (slip 01)
  ciprb_notification_slip_02_v1       → mpdsr.MPDSRDeathNotification (slip 02)
  ciprb_near_miss_v1                  → mpdsr.MaternalNearMissCase

The webhook dispatcher (programs.webhook) flattens grouped Kobo keys
before calling these handlers, so all fields are at the top level.
"""
import logging
from datetime import datetime

from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import HttpResponse
from django.utils.dateparse import parse_date

from fistula.ciprb_models import (CIPRBFistulaCase, CIPRBFistulaCaseCost,
                                  FISTULA_COST_STAGE)
from mpdsr.ciprb_models import (MPDSRDeathNotification, MaternalNearMissCase,
                                SurgeryChecklist, SURGERY_PHASE_ITEMS,
                                SURGERY_NOT_DONE)
from mpdsr.models import MPDSRCase, DeathType, PlaceOfDeath, ReviewStatus

logger = logging.getLogger(__name__)

ORG = 'CIPRB'


# ─── Coercion helpers (forgiving — Kobo sends strings) ──────────────────────
def _s(v):
    if v is None: return ''
    return str(v).strip()


def _norm_id(raw):
    """Normalise a patient ID the same way the form (translate(normalize-space()))
    and the export CSV (_norm_id) do: strip + upper-case. Keeps the stored
    patient_code, the CSV key, and the form's pulldata lookups all in sync, so
    ' 1-0001 ' and '1-0001' resolve to one row."""
    return _s(raw).upper()


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _bool(v):
    if v is None: return None
    s = str(v).strip().lower()
    if s in ('1', 'yes', 'true', 'y', 't'):  return True
    if s in ('0', 'no',  'false','n', 'f'):  return False
    return None


def _mnm_flag(v):
    """WHO Maternal Near-Miss screening code → 3-state flag.

    The verbatim form codes each Section-1 criterion 0-4 (0 = not present,
    1 = present at arrival, 2 = developed within 12h, 3 = developed after 12h,
    4 = unknown / NA). For the dashboard boolean we treat 1/2/3 (the condition
    WAS present at some point) as True, 0 as False, and 4 / blank as None.
    Also accepts the legacy yes/no/unknown values from the pre-rebuild form."""
    s = _s(v).lower()
    if s in ('1', '2', '3', 'yes', 'true', 'y', 't'):  return True
    if s in ('0', 'no', 'false', 'n', 'f'):            return False
    return None


def _date(v):
    if not v: return None
    if isinstance(v, datetime): return v.date()
    try:
        return parse_date(str(v))
    except (TypeError, ValueError):
        return None


def _geo(payload):
    geo = payload.get('_geolocation') or [None, None]
    if isinstance(geo, (list, tuple)) and len(geo) >= 2:
        return geo[0], geo[1]
    return None, None


def _district(payload):
    """Canonicalise the district to proper case.

    The Kobo `district` question is a select_one whose choice *values* are
    lowercase slugs ('sunamganj', 'moulavibazar'), so a live submission would
    otherwise store 'sunamganj' while seed / Excel rows use 'Sunamganj' —
    splitting per-district groupings and showing lowercase in tables. All 18
    CIPRB districts are single words, so slug→proper is a clean title-case.
    """
    raw = _s(payload.get('district'))
    if not raw:
        return ''
    return raw.replace('_', ' ').title()


# ─── Fistula patient-ID issuance ─────────────────────────────────────────────
import os as _os

from programs.bandhu_handlers import _writeback_kobo_id

_FISTULA_ASSET_UID = _os.environ.get(
    'KOBO_ASSET_UID_FISTULA_QB', 'aH86Euq2AeJ8S9VYdry4PC')
# CIPRB 10 (MPDSR Response Plan) — target of the issued-action-id write-back.
_MPDSR_ACTION_ASSET_UID = _os.environ.get(
    'KOBO_ASSET_UID_MPDSR_ACTION', 'auFCf7bfBDtrP6xeW5F2KJ')


def _allocate_fistula_case(payload, district, name, tries=40):
    """Create the case under the next free <district-code>-NNNN patient_code.

    Same arbitration as Bandhu's _allocate_client: no counter table, no lock —
    read the used serials, try to insert, and let the patient_code UNIQUE
    constraint settle a race by retrying. Returns None for an unknown district
    slug (the form's select_one makes that near-impossible, but a hand-crafted
    payload must not 500).
    """
    from django.db import IntegrityError, transaction as _tx

    from fistula.ciprb_models import FISTULA_DISTRICT_CODE

    slug = _s(payload.get('district')).lower().replace(' ', '_')
    dist_num = FISTULA_DISTRICT_CODE.get(slug)
    if dist_num is None:
        return None
    prefix = f'{dist_num}-'

    for _ in range(tries):
        used = (CIPRBFistulaCase.objects
                .filter(patient_code__startswith=prefix)
                .values_list('patient_code', flat=True))
        nums = [int(c[len(prefix):]) for c in used
                if c[len(prefix):].isdigit()]
        candidate = f'{prefix}{(max(nums) if nums else 0) + 1:04d}'
        try:
            with _tx.atomic():
                return CIPRBFistulaCase.objects.create(
                    patient_code=candidate, organisation=ORG,
                    district=district, name=name,
                    approval_status='PENDING',
                )
        except IntegrityError:
            continue
    raise RuntimeError(f'could not allocate a fistula patient id for {prefix}')


def _save_fistula_cost(payload):
    """Record what one episode of a woman's treatment cost.

    Keyed on (case, cost_point, episode_no) so re-sending the same episode
    CORRECTS it rather than doubling the programme's reported spend — a webhook
    redelivery and a worker fixing a typo must both be safe.

    Amounts are merged, not replaced wholesale: a head left blank on a
    correcting submission keeps whatever was already recorded, matching how
    every other stage in this handler behaves. A head sent as 0 is a real
    figure and does overwrite.
    """
    code = _norm_id(payload.get('patient_code_final')
                    or payload.get('patient_code_sel'))
    if not code:
        return HttpResponse('Bad Request — patient_code required for a cost '
                            'entry', status=400)

    point = _s(payload.get('cost_point')) or CIPRBFistulaCaseCost.POINT_REPAIRED
    if point not in dict(CIPRBFistulaCaseCost.POINT_CHOICES):
        return HttpResponse(f'Bad Request — unknown cost_point {point!r}',
                            status=400)

    # Numbered for both points. "একই আইডি ২নং ওটি" is the operation case, but a
    # woman referred twice travels twice, so referrals are numbered too rather
    # than being collapsed onto one row that the second entry would overwrite.
    episode = _int(payload.get('episode_final') or payload.get('episode_no'))
    if not episode or episode < 1:
        episode = 1

    with transaction.atomic():
        case = (CIPRBFistulaCase.objects.select_for_update()
                .filter(patient_code=code).first())
        if case is None:
            # Unlike a clinical stage, a cost with no patient cannot be given a
            # stub: the money would sit against a woman who was never
            # registered and would inflate the programme total. Reject it so
            # Kobo retries and the gap is visible.
            return HttpResponse('Bad Request — no registered patient for '
                                f'{code}', status=400)

        row, _created = CIPRBFistulaCaseCost.objects.select_for_update().get_or_create(
            case=case, cost_point=point, episode_no=episode)

        for fld in CIPRBFistulaCaseCost.COST_FIELDS:
            v = _int(payload.get(fld))
            if v is not None:
                setattr(row, fld, v)

        disb = _int(payload.get('amount_disbursed'))
        if disb is not None:
            row.amount_disbursed = disb
        row.disbursed_by = _s(payload.get('disbursed_by')) or row.disbursed_by
        row.cost_date = _date(payload.get('cost_date')) or row.cost_date
        row.remarks = _s(payload.get('cost_remarks')) or row.remarks
        row.kobo_submission_id = (str(payload.get('_id', ''))
                                  or row.kobo_submission_id)
        row.submitted_by_kobo_user = (_s(payload.get('_submitted_by'))
                                      or row.submitted_by_kobo_user)
        row.save()

    return HttpResponse('OK', status=200)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║   Form 1 — CIPRB Fistula Question Bank                                  ║
# ║   The form is staged: each submission carries data for ONE stage.        ║
# ║   Identity is captured ONCE, at the Suspected stage, under a unique      ║
# ║   patient_code (<district-code>-<4 digits>). Every later stage           ║
# ║   references that exact code via the form's dropdown, so the upsert keys ║
# ║   on patient_code and merges stage-specific fields onto the one row.     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def handle_ciprb_fistula(payload, lat, lng):
    stage = _s(payload.get('stage')) or CIPRBFistulaCase.STAGE_SUSPECTED
    # A cost entry rides the same form and the same patient dropdown, but it is
    # not a step in the clinical pathway: it must never move current_stage. It
    # is handled here, before the stage machinery below can touch the case row.
    if stage == FISTULA_COST_STAGE:
        return _save_fistula_cost(payload)
    if stage not in dict(CIPRBFistulaCase.STAGE_CHOICES):
        return HttpResponse(f'Bad Request — unknown stage {stage!r}', status=400)

    # One unified ID key: later stages carry the dropdown pick; a registration
    # from the current form version arrives EMPTY (the server issues the ID
    # below). Old form versions still in the field send a typed code — honoured
    # unchanged, so the changeover needs no flag day.
    code = _norm_id(payload.get('patient_code_final')
                    or payload.get('patient_code')
                    or payload.get('patient_code_sel'))
    district = _district(payload)
    name     = _s(payload.get('name'))
    is_suspected = stage == CIPRBFistulaCase.STAGE_SUSPECTED

    if is_suspected:
        if not (name and district):
            return HttpResponse(
                'Bad Request — name and district required at the suspected '
                'stage', status=400)
        if not code:
            # Server-side ID issuance (same design as the Bandhu Mother List:
            # the client-side pulldata duplicate check only sees the CSV copy
            # cached on the device, which let 2-0028 be registered twice on
            # 2026-08-08). Guard against webhook re-delivery FIRST, so a retry
            # of the same Kobo submission reuses its case instead of burning a
            # fresh ID.
            kobo_id = str(payload.get('_id', ''))
            existing = (CIPRBFistulaCase.objects
                        .filter(kobo_submission_id=kobo_id).first()
                        if kobo_id else None)
            if existing is not None:
                code = existing.patient_code
            else:
                case = _allocate_fistula_case(payload, district, name)
                if case is None:
                    return HttpResponse(
                        'Bad Request — unknown district '
                        f'{payload.get("district")!r}', status=400)
                code = case.patient_code
                _writeback_kobo_id(
                    _FISTULA_ASSET_UID, kobo_id, code,
                    field_path='patient_code_final')
    else:
        # Later stages: identity comes from the registered row; only the code
        # (picked from the dropdown) is required.
        if not code:
            return HttpResponse('Bad Request — patient_code required', status=400)

    with transaction.atomic():
        # The patient_code is the single, unique upsert key.
        case = (CIPRBFistulaCase.objects.select_for_update()
                .filter(patient_code=code).first())
        if case is None:
            if not is_suspected:
                # A later-stage submission for an unknown ID — create a stub so
                # the data isn't lost. It carries the code + stage but no
                # identity (the registration that should have set it is missing).
                case = CIPRBFistulaCase(
                    patient_code=code, organisation=ORG,
                    district=district, name=(name or 'Unknown'),
                    approval_status='PENDING',
                )
            else:
                case = CIPRBFistulaCase(
                    patient_code=code, organisation=ORG,
                    district=district, name=name,
                    approval_status='PENDING',
                )
        # Record the Kobo submitter for the approval queue display (latest wins).
        case.submitted_by_kobo_user = _s(payload.get('_submitted_by')) or case.submitted_by_kobo_user
        case.kobo_submission_id = str(payload.get('_id', '')) or case.kobo_submission_id

        # ── Identity + obstetric history are captured ONLY at registration
        #    (the form omits these fields at later stages). Gating the writes
        #    here keeps a later-stage submission from blanking a registered
        #    woman's details even if the payload carried stray empties.
        if is_suspected:
            case.district = district or case.district
            case.name     = name or case.name
            case.case_serial = _s(payload.get('case_serial')) or case.case_serial
            case.upazila = _s(payload.get('upazila'))    or case.upazila
            case.union   = _s(payload.get('union'))      or case.union
            case.village = _s(payload.get('village'))    or case.village

            for fld in ('age', 'age_at_marriage', 'age_at_first_delivery',
                        'number_of_children'):
                v = _int(payload.get(fld))
                if v is not None: setattr(case, fld, v)

            for fld in ('education', 'husband', 'husband_profession',
                        'profession_patient', 'current_condition',
                        'contact_number', 'marital_status',
                        'delivery_complication', 'last_delivery_labour_duration',
                        'mode_of_last_delivery', 'place_of_last_delivery',
                        'conducted_last_delivery', 'delivery_outcome',
                        'reasons_no_institutional_delivery',
                        'time_duration_fistula_occurrence',
                        'duration_suffering'):
                v = _s(payload.get(fld))
                if v: setattr(case, fld, v)

        # ── Stage-specific fields.
        if stage == CIPRBFistulaCase.STAGE_SUSPECTED:
            case.suspected_date     = _date(payload.get('suspected_date')) or case.suspected_date
            case.source_information = _s(payload.get('source_information')) or case.source_information
        elif stage == CIPRBFistulaCase.STAGE_DIAGNOSED:
            case.diagnosed_date  = _date(payload.get('diagnosed_date'))  or case.diagnosed_date
            case.diagnosed_place = _s(payload.get('diagnosed_place'))    or case.diagnosed_place
            case.diagnosed_by    = _s(payload.get('diagnosed_by'))       or case.diagnosed_by
            # Anatomical type (VVF/RVF/…) is now classified at diagnosis.
            # When 'other' is chosen the worker types the specific type; keep
            # that free text so the specified problem isn't lost as a bare code.
            gft = _s(payload.get('genital_fistula_type'))
            if gft == 'other':
                gft = _s(payload.get('genital_fistula_type_other')) or gft
            case.genital_fistula_type = gft or case.genital_fistula_type
        elif stage == CIPRBFistulaCase.STAGE_REFERRED:
            case.refer_date          = _date(payload.get('refer_date')) or case.refer_date
            case.refer_place         = _s(payload.get('refer_place'))   or case.refer_place
            case.referred_by_person  = _s(payload.get('referred_by_person')) or case.referred_by_person
            case.refer_outcome       = _s(payload.get('refer_outcome')) or case.refer_outcome
        elif stage == CIPRBFistulaCase.STAGE_REPAIRED:
            case.operation_date      = _date(payload.get('operation_date')) or case.operation_date
            case.operation_place     = _s(payload.get('operation_place')) or case.operation_place
            hsd = _int(payload.get('hospital_stay_days'))
            if hsd is not None: case.hospital_stay_days = hsd
            tops = _int(payload.get('times_of_operations'))
            if tops is not None: case.times_of_operations = tops
            # genital_fistula_type moved to the Diagnosed stage; the surgery
            # stage keeps only the cause classification + operative detail.
            for fld in ('fistula_type_v2', 'iatrogenic_cause',
                        'operation_route', 'surgery_outcome_v2'):
                v = _s(payload.get(fld))
                if v: setattr(case, fld, v)
        elif stage == CIPRBFistulaCase.STAGE_REHABILITATED:
            rb = _bool(payload.get('rehabilitation_received'))
            if rb is not None: case.rehabilitation_received = rb
            case.rehabilitation_date = _date(payload.get('rehabilitation_date')) or case.rehabilitation_date
            case.rehab_place         = _s(payload.get('rehab_place'))   or case.rehab_place
            case.rehab_support_types = _s(payload.get('rehab_support_types')) or case.rehab_support_types
            case.rehab_notes         = _s(payload.get('rehab_notes'))   or case.rehab_notes

        # ── Pipeline forward-progression: never let the stage go backwards.
        stage_order = {s: i for i, (s, _) in enumerate(CIPRBFistulaCase.STAGE_CHOICES)}
        if stage_order[stage] >= stage_order[case.current_stage]:
            case.current_stage = stage

        case.enumerator_name = _s(payload.get('enumerator_name'))
        case.enumerator_mobile = _s(payload.get('enumerator_mobile'))
        case.latitude, case.longitude = lat, lng
        case.raw_payload = payload
        case.save()

    return HttpResponse('OK', status=200)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║   MPDSR Forms 1, 2, 4, 5 + Social Autopsy                               ║
# ║   All five upsert into MPDSRCase. sub_form_type distinguishes them.     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

_PLACE_MAP = {
    'home':       PlaceOfDeath.HOME,
    'facility':   PlaceOfDeath.FACILITY,
    'in_transit': PlaceOfDeath.IN_TRANSIT,
}

_REVIEW_STATUS_MAP = {
    'reviewed':    ReviewStatus.CLOSED,
    'pending':     ReviewStatus.REPORTED,
    'in_progress': ReviewStatus.UNDER_REVIEW,
}


def _mpdsr_hash(sub_form_type, district, serial):
    """Globally-unique key for a case serial.

    MPDSRCase.case_hash carries a UNIQUE constraint across the whole table, but
    `case_serial` is a per-form, per-district counter — F-01/Gaibandha and
    F-02/Sunamganj both have a case 21. The upsert looked the row up scoped to
    (partner, sub_form_type, district, case_hash) and then stored the BARE
    serial, so a serial already used by another form or district found no row
    to update, tried to INSERT, and hit the global constraint:

        IntegrityError: duplicate key value violates unique constraint
        "mpdsr_mpdsrcase_case_hash_key"  DETAIL: Key (case_hash)=(21) already exists.

    The webhook turned that into a 500, Kobo could not deliver, and the
    submission stayed in Kobo — 90 of 152 death records never reached the
    dashboard. Namespacing the stored value the way Social Autopsy already does
    ('sa:' + slip) makes the key as unique as the constraint demands, and makes
    it match the scope the lookup uses.
    """
    return f'{sub_form_type}:{district}:{serial}'[:30]


def _save_mpdsr_case(payload, lat, lng, *, sub_form_type, death_type,
                     death_field_name='cause_of_death'):
    """Common upsert for any MPDSR review form."""
    serial   = _s(payload.get('case_serial'))
    district = _district(payload)
    # Verbatim forms name the death date 'death_date' (F01/F02/F05); F04 keeps
    # 'date_of_death'. Read either so community submissions aren't rejected.
    dod = _date(payload.get('date_of_death') or payload.get('death_date'))
    if not (district and dod):
        return HttpResponse('Bad Request — district and date_of_death required',
                            status=400)

    # Consent (community maternal/neonatal + social autopsy): an explicit 'No'
    # is HONOURED — we keep only a de-identified death count (district / date /
    # cause), withholding facility, narrative and action plan. Absent or
    # 'unknown' is NOT a refusal.
    consent_refused = (_bool(payload.get('consent_given')) is False)

    # De-dup key. With a serial, match on it. Without one, fall back to the Kobo
    # submission id so a genuine RETRY updates the same row, but two DIFFERENT
    # deaths never collide. (The old fallback keyed on (date, facility_name), so
    # two home deaths on the same date in the same district — facility_name=''
    # for both — silently overwrote each other.)
    sub_id = str(payload.get('_id') or '')
    qs = MPDSRCase.objects.select_for_update().filter(
        partner=ORG, sub_form_type=sub_form_type, district=district,
    )
    if serial:
        # Match the namespaced key, and the bare serial too so rows written
        # before this fix still upsert instead of spawning a duplicate. The
        # queryset is already scoped to this partner/form/district, so the
        # legacy alternative cannot pull in another district's case.
        qs = qs.filter(Q(case_hash=_mpdsr_hash(sub_form_type, district, serial))
                       | Q(case_hash=serial))
    elif sub_id:
        qs = qs.filter(case_hash='kobo:' + sub_id)
    else:
        qs = qs.none()   # nothing to match on — never overwrite a different death

    with transaction.atomic():
        case = qs.first()
        if case is None:
            case = MPDSRCase(
                partner=ORG, sub_form_type=sub_form_type,
                district=district, date_of_death=dod,
                death_type=death_type,
                approval_status='PENDING',
            )
        case.partner = ORG
        case.organisation = ORG
        case.submitted_by_kobo_user = _s(payload.get('_submitted_by')) or case.submitted_by_kobo_user
        case.kobo_submission_id = sub_id or case.kobo_submission_id
        case.sub_form_type = sub_form_type
        case.district = district
        case.upazila = _s(payload.get('upazila'))
        case.union   = _s(payload.get('union'))
        case.date_of_death = dod
        # Facility admission date (Form 04 only) — drives the admission→death
        # interval visual. Absent on community forms → stays null.
        adm = _date(payload.get('admission_date'))
        if adm: case.admission_date = adm
        case.death_type    = death_type
        # Cause of death — keep the typed cause when 'Other' is chosen
        # (previously only the slug 'other' was stored and the free text lost).
        # Cause field name differs per verbatim form: F04 'cause_of_death',
        # F01/F02 'icd_cause', F05 'cod_cause', Social Autopsy 'cause_brief'.
        cod = (_s(payload.get(death_field_name)) or _s(payload.get('cause_of_death'))
               or _s(payload.get('icd_cause')) or _s(payload.get('cod_cause')))
        if cod == 'other' and not consent_refused:
            other_txt = (_s(payload.get('cause_of_death_other')) or _s(payload.get('cause_other'))
                         or _s(payload.get('cause_name')) or _s(payload.get('icd_disease_name')))
            if other_txt:
                cod = 'other: ' + other_txt
        case.cause_of_death = cod
        # Place field differs per verbatim form (death_place / death_place_facility
        # / place_of_death_facility); the legacy _PLACE_MAP only knew
        # home/facility/in_transit, so map by substring (facility deaths → FACILITY).
        place_raw = _s(payload.get('place_of_death') or payload.get('death_place')
                       or payload.get('death_place_facility')
                       or payload.get('place_of_death_facility')).lower()
        if 'home' in place_raw:
            case.place_of_death = PlaceOfDeath.HOME
        elif 'transit' in place_raw or 'on_way' in place_raw or 'on the way' in place_raw:
            case.place_of_death = PlaceOfDeath.IN_TRANSIT
        elif place_raw:
            case.place_of_death = PlaceOfDeath.FACILITY
        case.facility_name = '' if consent_refused else _s(payload.get('facility_name'))
        age = (_int(payload.get('deceased_age')) or _int(payload.get('mother_age'))
               or _int(payload.get('woman_age')))
        if age: case.age_years = age

        rs = _REVIEW_STATUS_MAP.get(_s(payload.get('review_status')))
        if rs: case.status = rs
        case.committee_date = _date(payload.get('review_date'))
        if consent_refused:
            case.action_plan = ''
            case.notes = ('[Consent refused — recorded as a de-identified death '
                          "count; identifying details, narrative and action plan "
                          "withheld at the family's request]")
        else:
            case.action_plan = _s(payload.get('action_plan_summary'))
            if sub_form_type == 'sa_md':
                # Social Autopsy keeps its Three-Delays narrative in
                # delay1/2/3_factors + recommendations/barrier notes (NOT the
                # three_delays/contributory_factors the generic save assumed —
                # those fields don't exist on this form, so the narrative was
                # being dropped entirely).
                parts = [_s(payload.get(k)) for k in (
                    'delay1_factors', 'delay2_factors', 'delay3_factors',
                    'community_recommendations',
                    'gender_barrier_notes', 'financial_barrier_notes')]
                case.notes = '\n'.join(p for p in parts if p)
            else:
                # Verbatim forms carry the narrative under several keys
                # (community vs facility); gather whatever is present.
                case.notes = '\n'.join(p for p in (
                    _s(payload.get('three_delays')),
                    _s(payload.get('contributory_factors')),
                    _s(payload.get('narrative_before_death')),
                    _s(payload.get('cause_opinion')),
                    _s(payload.get('death_narrative')),
                ) if p)
        if serial:
            case.case_hash = _mpdsr_hash(sub_form_type, district, serial)
        elif sub_id:
            case.case_hash = ('kobo:' + sub_id)[:30]

        # ── CIPRB dashboard "major indicators" — persist the 9 fields that
        #    were previously dropped. Only the review forms (f1/f2/f4/f5)
        #    carry them; Social Autopsy (sa_md) is a qualitative re-review of
        #    an already-counted death and emits none of these, so skip it to
        #    avoid writing empty indicator rows.
        if sub_form_type != 'sa_md':
            case.time_of_death            = _s(payload.get('time_of_death') or payload.get('death_time'))
            gw = _int(payload.get('gestational_weeks') or payload.get('gestation_week'))
            if gw is not None: case.gestational_weeks = gw
            case.anc_visits_count         = _s(payload.get('anc_visits_count') or payload.get('anc_count'))
            case.pnc_received             = _s(payload.get('pnc_received') or payload.get('pnc_count'))
            case.mode_of_delivery         = _s(payload.get('mode_of_delivery') or payload.get('delivery_mode'))
            case.delivery_outcome         = _s(payload.get('delivery_outcome'))
            case.place_of_delivery        = _s(payload.get('place_of_delivery')
                                              or payload.get('delivery_place') or payload.get('birth_place'))
            case.person_assisted_delivery = _s(payload.get('person_assisted_delivery')
                                              or payload.get('delivery_conductor'))
            tdab = _int(payload.get('time_death_after_birth_hours')
                        or payload.get('death_after_delivery_h') or payload.get('age_death_hours'))
            if tdab is not None: case.time_death_after_birth_hours = tdab

        case.latitude, case.longitude = lat, lng
        case.source = 'kobo'
        # The full Kobo answers, so the approval card can show the reviewer
        # WHAT they are approving. Without this every verbatim review rendered
        # as "no payload data" and managers were signing blind.
        case.raw_payload = payload
        case.save()

    # System ref, outside the atomic block (its IntegrityError retry would
    # poison a wrapping transaction).
    from programs.refs import MPDSR_FORM_CODE, allocate_system_ref
    allocate_system_ref(case, MPDSR_FORM_CODE.get(sub_form_type, 'MP'))
    return HttpResponse('OK', status=200)


def handle_ciprb_mpdsr_community_maternal(payload, lat, lng):
    return _save_mpdsr_case(payload, lat, lng,
                             sub_form_type='f1',
                             death_type=DeathType.MATERNAL)


def handle_ciprb_mpdsr_community_neonatal(payload, lat, lng):
    return _save_mpdsr_case(payload, lat, lng,
                             sub_form_type='f2',
                             death_type=DeathType.PERINATAL)


def handle_ciprb_mpdsr_facility_maternal(payload, lat, lng):
    return _save_mpdsr_case(payload, lat, lng,
                             sub_form_type='f4',
                             death_type=DeathType.MATERNAL)


def handle_ciprb_mpdsr_facility_neonatal(payload, lat, lng):
    return _save_mpdsr_case(payload, lat, lng,
                             sub_form_type='f5',
                             death_type=DeathType.PERINATAL)


def handle_ciprb_social_autopsy(payload, lat, lng):
    """CIPRB-6 Social Autopsy — a committee MEETING report, not a death review.

    The verbatim paper carries NO death date or structured cause/place (it is keyed
    to a death-notification slip number), so it cannot go through _save_mpdsr_case
    (which requires date_of_death). Stored as MPDSRCase sub_form_type='sa_md':
    the meeting date stands in as the required date stamp + committee_date, the
    narrative → notes, the prevention points + decisions → action_plan, and the
    full submission (name, sex, age m/d, member counts, slip no.) is preserved in
    raw_payload. Held PENDING for CIPRB approval on create.
    """
    district = _district(payload)
    meeting_date = _date(payload.get('meeting_date'))
    if not (district and meeting_date):
        return HttpResponse('Bad Request — district and meeting_date required',
                            status=400)
    sub_id = str(payload.get('_id') or '')
    slip = _s(payload.get('slip_number'))
    # 1 = maternal, 2 = neonatal, 3 = stillbirth → MATERNAL vs PERINATAL.
    # DeathType has no stillbirth member, so 2 and 3 both land on PERINATAL.
    # Keep the reviewer's actual answer in sa_death_kind, otherwise a reviewed
    # stillbirth is indistinguishable from a reviewed neonatal death and shows
    # up nowhere on the dashboard.
    _sa_kind_raw = _s(payload.get('sa_death_type'))
    sa_death_kind = {'1': 'maternal', '2': 'neonatal', '3': 'stillbirth'}.get(_sa_kind_raw, '')
    death_type = DeathType.MATERNAL if _sa_kind_raw == '1' else DeathType.PERINATAL

    def _block(prefix, n):
        out = []
        for i in range(1, n + 1):
            v = _s(payload.get('%s_%d' % (prefix, i)))
            if v:
                out.append('%d. %s' % (i, v))
        return '\n'.join(out)

    narrative = _s(payload.get('death_narrative'))
    prevention = _block('prevention', 4)
    decisions = _block('decision', 4)
    action_plan = ''
    if prevention:
        action_plan += 'Preventable factors:\n' + prevention
    if decisions:
        action_plan += ('\n\n' if action_plan else '') + 'Decisions:\n' + decisions

    # De-dup: slip number when present (one social-autopsy per notified death),
    # else the Kobo submission id so a retry updates the same row.
    qs = MPDSRCase.objects.select_for_update().filter(
        partner=ORG, sub_form_type='sa_md', district=district)
    if slip:
        qs = qs.filter(case_hash='sa:' + slip)
    elif sub_id:
        qs = qs.filter(case_hash='kobo:' + sub_id)
    else:
        qs = qs.none()

    with transaction.atomic():
        case = qs.first()
        is_new = case is None
        if is_new:
            case = MPDSRCase(partner=ORG, sub_form_type='sa_md', district=district,
                             approval_status='PENDING')
            case.case_hash = ('sa:' + slip) if slip else ('kobo:' + sub_id if sub_id else '')
        case.organisation = ORG
        case.district = district
        case.upazila = _s(payload.get('upazila'))
        case.union = _s(payload.get('union'))
        case.date_of_death = meeting_date     # no death date on the paper; meeting date is the stamp
        case.committee_date = meeting_date
        case.death_type = death_type
        case.sa_death_kind = sa_death_kind
        age = _int(payload.get('age_years'))
        if age:
            case.age_years = age
        case.notes = narrative
        case.action_plan = action_plan
        case.latitude = lat
        case.longitude = lng
        case.raw_payload = payload
        case.submitted_by_kobo_user = _s(payload.get('_submitted_by'))
        case.kobo_submission_id = sub_id or case.kobo_submission_id
        case.save()

    from programs.refs import MPDSR_FORM_CODE, allocate_system_ref
    allocate_system_ref(case, MPDSR_FORM_CODE.get(case.sub_form_type, 'SA'))
    return HttpResponse('OK', status=200)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║   Notification slips 01 + 02                                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _ns_place(payload):
    """Map the verbatim slip-01 'মৃত্যু স্থান' choice to the model's coarse
    home/facility/in_transit enum (the rich choice survives in raw_payload)."""
    raw = _s(payload.get('place_of_death')).lower()
    if raw == 'home':
        return MPDSRDeathNotification.PLACE_HOME
    if raw == 'on_the_way':
        return MPDSRDeathNotification.PLACE_TRANSIT
    if raw in ('govt_facility', 'private_ngo'):
        return MPDSRDeathNotification.PLACE_FACILITY
    return ''


def _save_notification(payload, lat, lng, slip_variant: str):
    # Verbatim slips name the death date 'death_date'; the deceased identity is
    # captured as the MOTHER (মায়ের নাম / মায়ের বয়স — the mother is the deceased
    # for a maternal death, and the recorded subject for a neonatal/stillbirth).
    district = _district(payload)
    dod = _date(payload.get('death_date') or payload.get('date_of_death'))
    name = _s(payload.get('mother_name')) or _s(payload.get('deceased_name'))
    if not (district and dod and name):
        return HttpResponse(
            'Bad Request — district, death_date, mother_name required',
            status=400)
    # The case serial is the number the programme identifies a case BY, so it
    # belongs in the identity — it used to sit in `defaults` and be overwritten.
    # Without it the key was (slip, district, date, mother's name), which merges
    # two genuinely different deaths whenever they share a mother and a date:
    #
    #   Bhola 2026-05-15 'Sadia'   serial 1 = MATERNAL death, serial 3 = STILLBIRTH
    #   Bhola 2026-06-01 'Suntana' serial 34 = STILLBIRTH,    serial 41 = NEONATAL
    #
    # A mother dying and her baby being stillborn are TWO surveillance events and
    # must both be counted. Merging them dropped one death outright and left the
    # survivor's death_kind decided by whichever slip arrived last. Two deaths
    # were missing from the notification counts because of this.
    #
    # A blank serial falls back to the Kobo submission id, so a genuine retry
    # still updates its own row while two different deaths never collide.
    serial = _s(payload.get('case_serial'))
    identity = serial or ('kobo:' + str(payload.get('_id') or ''))

    base = dict(slip_variant=slip_variant, district=district,
                date_of_death=dod, deceased_name=name)
    qs = MPDSRDeathNotification.objects.filter(**base)
    if serial:
        obj = qs.filter(case_serial=serial).first()
    else:
        # No serial on the slip. Match our own 'kobo:' key, and ALSO a legacy row
        # written before case_serial joined the identity — its serial is still ''.
        # Without that second arm a re-delivery creates a second row for the one
        # death instead of updating it.
        obj = qs.filter(Q(case_serial=identity) | Q(case_serial='')).first()

    created = obj is None
    if created:
        obj = MPDSRDeathNotification(**base)
    obj.case_serial = identity

    for _field, _value in dict(
            organisation=ORG,
            upazila=_s(payload.get('upazila')),
            union=_s(payload.get('union')),
            village=_s(payload.get('village')),
            death_kind=_s(payload.get('death_kind')) or MPDSRDeathNotification.KIND_MATERNAL,
            deceased_age=_int(payload.get('mother_age')) or _int(payload.get('deceased_age')),
            place_of_death=_ns_place(payload),
            cause_brief=_s(payload.get('cause_of_death')) or _s(payload.get('cause_brief')),
            reporter_name=_s(payload.get('collector_name')) or _s(payload.get('reporter_name')),
            reporter_mobile=_s(payload.get('collector_mobile')) or _s(payload.get('reporter_mobile')),
            notification_date=_date(payload.get('slip_date')) or dod,
            latitude=lat, longitude=lng,
            raw_payload=payload,
            submitted_by_kobo_user=_s(payload.get('_submitted_by')),
            kobo_submission_id=str(payload.get('_id') or ''),
    ).items():
        setattr(obj, _field, _value)

    # New notifications are held for CIPRB-manager approval; a re-submission
    # (update) keeps whatever status it already has — no re-pending.
    if created:
        obj.approval_status = 'PENDING'
    obj.save()

    from programs.refs import SLIP_FORM_CODE, allocate_system_ref
    allocate_system_ref(obj, SLIP_FORM_CODE.get(slip_variant, 'NS'))
    return HttpResponse('OK', status=200)


def handle_ciprb_notification_slip_01(payload, lat, lng):
    return _save_notification(payload, lat, lng, MPDSRDeathNotification.SLIP_01)


def handle_ciprb_notification_slip_02(payload, lat, lng):
    return _save_notification(payload, lat, lng, MPDSRDeathNotification.SLIP_02)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║   Maternal Near Miss audit                                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

_MNM_BOOL_FIELDS = (
    'sev_pph', 'sev_preec', 'eclampsia', 'sepsis', 'rupt_uterus', 'sev_abortion',
    'crit_blood', 'crit_radiol', 'crit_laparot', 'crit_icu',
    'life_cardio', 'life_resp', 'life_renal', 'life_coag',
    'life_hepatic', 'life_neuro', 'life_uterine',
)

# Section 3 Q15 mode-of-delivery checkboxes → the single indexed
# `mode_of_delivery` value. The Excel codes Q15 as 9 separate 0/1 items; we keep
# all 9 in raw_payload and store the first 'present' one on the model.
_MNM_MODE_FIELDS = (
    ('mode_vaginal', 'vaginal'),
    ('mode_csection', 'csection'),
    ('mode_complete_abortion', 'complete_abortion'),
    ('mode_curettage', 'curettage'),
    ('mode_medical_evacuation', 'medical_evacuation'),
    ('mode_lap_ectopic', 'lap_ectopic'),
    ('mode_lap_rupture', 'lap_rupture'),
    ('mode_discharged_pregnant', 'discharged_pregnant'),
    ('mode_unknown_other', 'unknown_other'),
)

# Section 5 underlying-cause flags → the indexed `cause_of_near_miss` bucket
# used by the dashboards. The verbatim form has no single 'primary cause'
# question, so we derive it from the WHO underlying-cause checklist (un_*),
# taking the first 'present' item in clinical-priority order. The full
# checklist stays in raw_payload.
_MNM_CAUSE_PRIORITY = (
    ('un_haemorrhage',     'haemorrhage'),
    ('un_hypertensive',    'eclampsia'),
    ('un_infection',       'sepsis'),
    ('un_abortive',        'abortion_related'),
    ('un_ectopic_molar',   'abortion_related'),
    ('un_rupture',         'other'),
    ('un_medical',         'indirect'),
    ('un_coincidental',    'indirect'),
    ('un_other_obstetric', 'other'),
    ('un_unexpected',      'other'),
    ('un_unknown',         'other'),
)

# Section 6 contributory-condition flags → labels, summarised into the existing
# free-text `contributory_conditions` field (structured cc_* live in raw_payload).
_MNM_CONTRIB_LABELS = (
    ('cc_anemia',      'Anemia'),
    ('cc_hiv',         'HIV infection'),
    ('cc_prev_cs',     'Previous cesarean section'),
    ('cc_obstructed',  'Prolonged/obstructed labor'),
    ('cc_heart',       'Heart disease'),
    ('cc_diabetes',    'Diabetes mellitus'),
    ('cc_respiratory', 'Respiratory dysfunction; Asthma, TB'),
)


def handle_ciprb_near_miss(payload, lat, lng):
    district = _district(payload)
    event_date = _date(payload.get('event_date'))
    name = _s(payload.get('woman_name'))
    if not (district and event_date and name):
        return HttpResponse(
            'Bad Request — district, event_date, woman_name required',
            status=400)

    serial = _s(payload.get('case_serial'))
    qs = MaternalNearMissCase.objects.select_for_update().filter(
        district=district, woman_name=name, event_date=event_date,
    )
    with transaction.atomic():
        case = qs.first() or MaternalNearMissCase(
            district=district, woman_name=name, event_date=event_date,
            organisation=ORG, approval_status='PENDING',
        )
        case.submitted_by_kobo_user = _s(payload.get('_submitted_by')) or case.submitted_by_kobo_user
        case.kobo_submission_id = str(payload.get('_id') or '') or case.kobo_submission_id
        case.upazila = _s(payload.get('upazila'))
        case.union   = _s(payload.get('union'))
        case.village = _s(payload.get('village'))
        case.case_serial = serial
        age = _int(payload.get('woman_age'))
        if age: case.woman_age = age
        gw = _int(payload.get('gestational_weeks'))
        if gw: case.gestational_weeks = gw
        case.facility_name = _s(payload.get('facility_name'))

        # 3-state screening flags: the verbatim form sends the WHO 0-4 code,
        # so map 1/2/3 → present (True), 0 → False, 4/blank → None. _mnm_flag
        # also accepts legacy yes/no/unknown from the pre-rebuild form.
        for fld in _MNM_BOOL_FIELDS:
            setattr(case, fld, _mnm_flag(payload.get(fld)))

        # Q15 is 9 binary checkboxes in the Excel; store the first 'present'
        # one on the model (all 9 remain in raw_payload). Legacy single-select
        # submissions fall back to the old mode_of_delivery value.
        case.mode_of_delivery = next(
            (slug for key, slug in _MNM_MODE_FIELDS
             if _s(payload.get(key)).lower() in ('1', 'yes', 'true')),
            _s(payload.get('mode_of_delivery')))
        # The verbatim form has no separate 'delivery_outcome' question; derive
        # it from the infant's vital status at birth (Q17.1).
        _ivb = _s(payload.get('infant_status_birth')).lower()
        case.delivery_outcome = ('livebirth' if _ivb == 'alive'
                                 else 'stillbirth' if _ivb == 'dead' else '')
        # Derive the indexed primary cause from the Section-5 checklist
        # (the verbatim form has no single 'primary cause' question). Falls
        # back to any legacy cause_of_near_miss value a pre-rebuild form sent.
        case.cause_of_near_miss = next(
            (bucket for key, bucket in _MNM_CAUSE_PRIORITY
             if _s(payload.get(key)).lower() in ('1', 'yes', 'true')),
            _s(payload.get('cause_of_near_miss')))
        # Summarise the Section-6 checklist into the existing free-text field.
        _cc = [lbl for key, lbl in _MNM_CONTRIB_LABELS
               if _s(payload.get(key)).lower() in ('1', 'yes', 'true')]
        _cc_other = _s(payload.get('cc_other_specify'))
        if _cc_other:
            _cc.append(_cc_other)
        case.contributory_conditions = ', '.join(_cc)
        case.audit_summary           = _s(payload.get('audit_summary'))

        case.enumerator_name   = _s(payload.get('enumerator_name'))
        case.enumerator_mobile = _s(payload.get('enumerator_mobile'))
        case.latitude, case.longitude = lat, lng
        case.raw_payload = payload
        case.save()

    from programs.refs import NEAR_MISS_FORM_CODE, allocate_system_ref
    allocate_system_ref(case, NEAR_MISS_FORM_CODE)
    return HttpResponse('OK', status=200)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║   Safe Surgery Checklist (CIPRB 11) — WHO Surgical Safety Checklist     ║
# ║   One submission = one operation. Phase completion (Sign In / Time Out  ║
# ║   / Sign Out) is scored here so the dashboard shows status at a glance.  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _parse_dt(v):
    """Parse a Kobo dateTime ('2026-10-19T14:30:00.000+06:00') → datetime, or
    None. Falls back to a date-only value promoted to midnight so an operation
    that carried only a date still sorts on the timeline."""
    if not v:
        return None
    from django.utils.dateparse import parse_datetime
    dt = parse_datetime(str(v).strip())
    if dt is not None:
        return dt
    d = _date(v)
    if d is None:
        return None
    from datetime import datetime as _dtcls, time as _time
    return _dtcls.combine(d, _time.min)


def _score_surgery_phase(payload, item_names):
    """Return (total, done) for one checklist phase.

    total = number of items in the phase (fixed by the form).
    done  = items the team addressed — answered with anything other than
            'Not done'. WHO compliance is "the check happened", not "the answer
            was yes", so 'no' / 'na' / the equipment-ready variants all count as
            done. A blank answer counts as not-done (step skipped), so a
            partially-filled phase never reads as complete."""
    total = len(item_names)
    done = 0
    for name in item_names:
        v = _s(payload.get(name)).lower()
        if v and v != SURGERY_NOT_DONE:
            done += 1
    return total, done


def handle_ciprb_safe_surgery(payload, lat, lng):
    """CIPRB-11 Safe Surgery Checklist — one operation per submission.

    Scores each of the three WHO phases on ingestion (Sign In / Time Out /
    Sign Out), stores the counts + a per-phase complete flag + overall
    compliance, and holds the record PENDING for CIPRB (Tanjina) approval.
    Idempotent on the Kobo submission id so a webhook re-delivery updates the
    same operation rather than creating a duplicate. patient_name is stored
    encrypted and never leaves the PII-gated approval drawer."""
    district = _district(payload)
    operation_name = _s(payload.get('operation_name'))
    if not operation_name:
        return HttpResponse('Bad Request — operation_name required', status=400)

    sub_id = str(payload.get('_id') or '')
    op_dt = _parse_dt(payload.get('op_datetime'))

    with transaction.atomic():
        row = (SurgeryChecklist.objects.select_for_update()
               .filter(kobo_submission_id=sub_id).first()
               if sub_id else None)
        is_new = row is None
        if is_new:
            row = SurgeryChecklist(organisation=ORG, approval_status='PENDING')

        row.organisation = ORG
        row.district = district
        row.upazila  = _s(payload.get('upazila'))
        row.union    = _s(payload.get('union'))
        row.village  = _s(payload.get('village'))
        row.facility_name  = _s(payload.get('facility_name'))
        row.ward_unit      = _s(payload.get('ward_unit'))
        row.operation_name = operation_name
        row.op_datetime    = op_dt
        row.collection_date = _date(payload.get('collection_date'))
        row.surgeon          = _s(payload.get('surgeon'))
        row.anesthesiologist = _s(payload.get('anesthesiologist'))
        row.patient_name     = _s(payload.get('patient_name'))

        # Score the three phases from the single-source item lists so the
        # handler and the dashboard aggregate can never disagree.
        st, sd = _score_surgery_phase(payload, SURGERY_PHASE_ITEMS['signin'])
        tt, td = _score_surgery_phase(payload, SURGERY_PHASE_ITEMS['timeout'])
        ot, od = _score_surgery_phase(payload, SURGERY_PHASE_ITEMS['signout'])
        row.signin_total,  row.signin_done  = st, sd
        row.timeout_total, row.timeout_done = tt, td
        row.signout_total, row.signout_done = ot, od
        row.signin_complete  = (st > 0 and sd == st)
        row.timeout_complete = (tt > 0 and td == tt)
        row.signout_complete = (ot > 0 and od == ot)
        row.fully_compliant  = (row.signin_complete and row.timeout_complete
                                and row.signout_complete)

        row.enumerator_name   = _s(payload.get('enumerator_name'))
        row.enumerator_mobile = _s(payload.get('enumerator_mobile'))
        row.submitted_by_kobo_user = (_s(payload.get('_submitted_by'))
                                      or row.submitted_by_kobo_user)
        row.kobo_submission_id = sub_id or row.kobo_submission_id
        row.latitude, row.longitude = lat, lng
        row.raw_payload = payload
        row.save()

    # System ref (the automatic operation ID) — outside the atomic block, as the
    # IntegrityError retry would poison a wrapping transaction.
    from programs.refs import SURGERY_FORM_CODE, allocate_system_ref
    allocate_system_ref(row, SURGERY_FORM_CODE)
    return HttpResponse('OK', status=200)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║   MPDSR Action Plan (CIPRB 10) — staged per-action tracker              ║
# ║   'new_plan' creates one MPDSRAction per agreed action (each gets a      ║
# ║   <district-code>-<NN> id); 'update_action' moves one forward by id.     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _flat_item(item):
    """Flatten one Kobo repeat instance to leaf field names — the dispatcher
    only flattens the TOP-level payload, not inside repeats."""
    if not isinstance(item, dict):
        return {}
    flat = dict(item)
    for k, v in item.items():
        if '/' in k:
            flat.setdefault(k.rsplit('/', 1)[-1], v)
    return flat


def _repeat(payload, *keys):
    """The list of instances for a repeat group. Kobo may serialise a repeat
    nested in groups either as a top-level slash-key (the dispatcher aliases it
    to the leaf name) OR as a nested dict — search both so the handler reads the
    actions regardless of how deep the form nests the repeat.

    Crucially, match only LIST values: Kobo can emit an empty-string scalar
    placeholder for a 0-instance repeat, and the dispatcher's first-wins leaf
    aliasing could let that scalar shadow the real array. Scanning for a
    list-valued key (exact OR by leaf) makes a scalar placeholder un-shadowing."""
    want = set(keys)
    for k, v in payload.items():
        if isinstance(v, list) and isinstance(k, str) and (k in want or k.rsplit('/', 1)[-1] in want):
            return v

    def _search(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and k.rsplit('/', 1)[-1] in want and isinstance(v, list):
                    return v
                found = _search(v)
                if found is not None:
                    return found
        elif isinstance(obj, list):
            for it in obj:
                found = _search(it)
                if found is not None:
                    return found
        return None

    return _search(payload) or []


# Enumerator contact PII that does not belong in the persisted action record /
# the approval-queue detail serializer. Stripped from raw_payload on save.
_ACTION_PII_KEYS = ('enumerator_mobile',)


def _safe_action_payload(payload):
    """raw_payload copy with enumerator contact PII removed (audit FIX 2026-06).
    The action register never needs the enumerator's mobile number, and
    raw_payload is otherwise visible to the whole CIPRB approver pool."""
    if not isinstance(payload, dict):
        return payload
    return {k: v for k, v in payload.items()
            if k.rsplit('/', 1)[-1] not in _ACTION_PII_KEYS}


def _couple_status_completion(act, completion_date):
    """Keep status and completion% coherent (audit FIX 2026-06): Implemented ⇒
    100%, and 100% ⇒ Implemented. Without this the form's two independent
    questions allow 'Implemented at 0%' or '100% but Pending' to persist."""
    from mpdsr.models import ActionStatus
    if act.status == ActionStatus.IMPLEMENTED:
        act.completion_pct = 100
        if not act.completion_date:
            act.completion_date = completion_date or act.timeline
    elif act.completion_pct == 100 and act.status not in (
            ActionStatus.IMPLEMENTED, ActionStatus.DROPPED):
        act.status = ActionStatus.IMPLEMENTED
        if not act.completion_date:
            act.completion_date = completion_date or act.timeline


def handle_ciprb_mpdsr_action_plan(payload, lat, lng):
    """CIPRB-10 MPDSR Action Plan — staged per-action tracker (fistula pattern).

    Mode 'new_plan': register ONE action whose <district-code>-<NNN> id the field
    worker TYPED; upsert on (district, action_id).
    Mode 'update_action': move an existing action (picked by id) forward —
    status / completion % / completion date / remarks.

    Hardened (audit 2026-06): idempotent on the Kobo _id (re-delivery safe);
    lookups scoped to (district, action_id) to match the uniqueness constraint;
    concurrent same-id inserts retried instead of 500-stranding; a different
    enumerator who reuses an id already owning a real action is reallocated a
    fresh id rather than silently overwriting it; unknown-id updates are ignored
    (no phantom rows); status/completion kept coherent.
    """
    from mpdsr.models import (MPDSRAction, ActionSection, ActionStatus,
                              STUB_ACTIVITY_SENTINEL)
    mode = _s(payload.get('ap_mode'))
    district = _district(payload)
    sub_id = str(payload.get('_id') or '')
    user = _s(payload.get('_submitted_by')) or 'kobo'
    enum_name = _s(payload.get('enumerator_name'))   # the typed "YOUR NAME" — creator/editor

    # ── Idempotency: Kobo re-delivers on timeout / 500-retry. If this exact
    #    submission was already applied, ack and skip — a redelivery would
    #    otherwise revert a CIPRB approval granted between deliveries and
    #    double-log the audit trail.
    if sub_id and MPDSRAction.objects.filter(kobo_submission_id=sub_id).exists():
        return HttpResponse('OK (duplicate delivery)', status=200)

    def _lookup(code):
        # Scope by (district, action_id) to match unique_together; the update
        # dropdown is district-filtered and new_plan always carries a district,
        # so id-only is a fallback for malformed payloads only.
        qs = MPDSRAction.objects.select_for_update().filter(action_id=code)
        if district:
            qs = qs.filter(district=district)
        return qs.first()

    # ── Update an existing action by id ────────────────────────────────────
    if mode == 'update_action':
        code = _norm_id(payload.get('ap_action_sel') or payload.get('ap_action_id'))
        if not code:
            return HttpResponse('Bad Request — no action selected', status=400)
        for attempt in range(3):
            try:
                with transaction.atomic():
                    act = _lookup(code)
                    if act is None:
                        # No such action. With PENDING actions now in the dropdown
                        # CSV a real action is always selectable, so an unknown id
                        # has nothing to advance — ack + log rather than fabricate
                        # a phantom '[awaiting plan record]' row.
                        logger.warning('MPDSR update_action for unknown id %r '
                                       '(district %r) — ignored', code, district)
                        return HttpResponse('OK (no such action; ignored)', status=200)
                    st = _s(payload.get('ap_new_status'))
                    if st: act.status = st
                    cp = _int(payload.get('ap_new_completion'))
                    if cp is not None: act.completion_pct = cp
                    cd = _date(payload.get('ap_completion_date'))
                    if cd: act.completion_date = cd
                    rm = _s(payload.get('ap_remarks'))
                    if rm: act.remarks = rm
                    _couple_status_completion(act, cd)
                    act.kobo_submission_id = sub_id or act.kobo_submission_id
                    # Per-creator gate: an edit drops the action back to PENDING
                    # for CIPRB re-approval; record the editor.
                    if enum_name:
                        act.last_edited_by_name = enum_name
                    act.approval_status = 'PENDING'
                    act.approved_by = None
                    act.approved_at = None
                    act.add_audit_entry(user, 'status update — pending re-approval',
                                        '%s / %s%% · edited by %s'
                                        % (act.status, act.completion_pct, enum_name or user))
                    act.save()
                return HttpResponse('OK', status=200)
            except IntegrityError:
                if attempt == 2:
                    logger.exception('MPDSR update_action conflict (acked): %s', code)
                    return HttpResponse('OK (conflict, logged)', status=200)
                continue

    # ── New plan — register ONE action, keyed on the worker-typed action_id. ──
    if not district:
        return HttpResponse('Bad Request — district required', status=400)
    # The action id may be TYPED (older form versions, and the field worker who
    # already knows the number) or left BLANK, in which case the server issues
    # the next free one for the district. Blank used to be a 400: Rina in
    # Sunamganj could only guess, typed SU-001, and the duplicate rule blocked
    # her (2026-08-20). No worker can know which serials are taken, so guessing
    # is not a workable design.
    code = _norm_id(payload.get('action_id'))
    auto_id = not code
    activity = _s(payload.get('act_activity'))
    if not activity:
        return HttpResponse('Bad Request — activity required', status=400)
    # The form carries no separate review-meeting date; the entry date is the
    # best available stamp.
    meeting_date = _date(payload.get('collection_date'))
    section = _s(payload.get('rp_section'))
    if section not in ActionSection.values:
        section = ActionSection.SYSTEM_STRENGTHENING
    for attempt in range(3):
        try:
            with transaction.atomic():
                if auto_id:
                    # Allocate inside the transaction, and re-allocate on every
                    # retry: a concurrent plan may have taken the number that
                    # this attempt computed.
                    code = MPDSRAction.next_action_id(district)
                act = _lookup(code)
                is_new = act is None
                if not is_new:
                    # The id already exists in this district. Distinguish a
                    # legitimate re-registration (same creator, or reconciling a
                    # left-over stub) from a genuine COLLISION — a DIFFERENT
                    # enumerator grabbing an id that already owns a real action.
                    # Never overwrite someone else's logged maternal-death action:
                    # reallocate the incoming submission to a fresh id (lossless).
                    is_stub = (act.activity == STUB_ACTIVITY_SENTINEL)
                    same_creator = bool(enum_name) and act.creator_name == enum_name
                    if not (is_stub or same_creator):
                        new_code = MPDSRAction.next_action_id(district)
                        logger.warning(
                            'MPDSR action id collision: %s already owns %r in %s; '
                            'reallocating incoming submission to %s', code,
                            (act.creator_name or act.submitted_by_kobo_user or '?'),
                            district, new_code)
                        code = new_code
                        act = None
                        is_new = True
                if is_new:
                    act = MPDSRAction(action_id=code, district=district,
                                      organisation=ORG, source='kobo')
                act.district = district
                act.organisation = ORG
                act.meeting_date = meeting_date
                act.section = section
                # sub_category holds the master table's FIRST column, whichever
                # table this action came from: the System-Strengthening
                # sub-category, or (new) the common modifiable factor for the two
                # factor tables. `section` disambiguates the vocabulary. 'other'
                # stores the district's own wording instead of the code.
                if section == ActionSection.SYSTEM_STRENGTHENING:
                    act.sub_category = _s(payload.get('act_subcat'))
                else:
                    factor = _s(payload.get('act_factor'))
                    if factor == 'other':
                        factor = _s(payload.get('act_factor_other'))
                    act.sub_category = factor[:120]
                act.activity = activity
                act.responsible = _s(payload.get('act_responsible'))
                act.timeline = _date(payload.get('act_timeline'))
                act.indicator = _s(payload.get('act_indicator'))
                act.milestone = _s(payload.get('act_milestone'))
                act.considerations = _s(payload.get('act_considerations'))
                # Status/creator are set only at registration — a later re-submit
                # of the same id must not reset an advanced action or its owner.
                if is_new:
                    act.status = _s(payload.get('act_status')) or ActionStatus.PENDING
                    act.creator_name = enum_name            # immutable: set ONCE
                if enum_name:
                    act.last_edited_by_name = enum_name
                _couple_status_completion(act, None)
                act.kobo_submission_id = sub_id
                act.submitted_by_kobo_user = user
                act.raw_payload = _safe_action_payload(payload)
                # Every plan submission re-enters the CIPRB approval gate.
                act.approval_status = 'PENDING'
                act.approved_by = None
                act.approved_at = None
                act.add_audit_entry(user, 'created' if is_new else 're-registered',
                                    'plan %s · by %s' % (meeting_date or '', enum_name or user))
                act.save()
            if auto_id:
                # Put the issued id on the Kobo record so the district can see
                # its own Action ID without opening the dashboard. Best effort,
                # in a daemon thread: a Kobo outage must never turn a saved
                # action into a 500 that Kobo would then retry.
                _writeback_kobo_id(_MPDSR_ACTION_ASSET_UID, sub_id, code,
                                   field_path='action_id')
            return HttpResponse('OK — 1 action (%s)' % code, status=200)
        except IntegrityError:
            if attempt == 2:
                logger.exception('MPDSR new_plan conflict (acked): %s', code)
                return HttpResponse('OK (conflict, logged)', status=200)
            continue
