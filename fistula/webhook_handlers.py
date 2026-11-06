"""
KoboToolbox webhook handlers for CIPRB Fistula forms.

Two form types:
  spondon_fistula_corner_v1     → FistulaCornerCase
  spondon_fistula_campaign_v1   → FistulaCampaignVisit

Registered in programs/webhook.py FORM_HANDLERS at import time. Same
dispatch contract: takes (payload, lat, lng), returns HttpResponse.
Same _base_kwargs convention so submitted_by FK resolution from FIX 15.7
flows through automatically.
"""
import logging

from django.http import HttpResponse
from django.utils import timezone

from .models import FistulaCornerCase, FistulaCampaignVisit, FistulaCampaign

logger = logging.getLogger(__name__)


# Local copies of programs/webhook.py value coercers — kept tiny so the
# fistula app doesn't import from programs (avoids circular import).

def _str(v, default: str = '') -> str:
    return str(v).strip() if v is not None else default


def _int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _bool_or_none(v):
    if v is None or v == '':
        return None
    s = str(v).strip().lower()
    return s in ('yes', 'true', '1', 'on', 'checked', 'হ্যাঁ')


def _date(v):
    """Best-effort date parse; handles ISO + dd-mm-yyyy / dd/mm/yyyy."""
    if not v:
        return None
    from datetime import date, datetime
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _resolve_submitter(payload):
    """Same lookup as programs/webhook.py — kept here to avoid the
    cross-app import."""
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
    qs = User.objects.filter(is_active=True)
    return (
        qs.filter(email__iexact=raw).first()
        or qs.filter(email__istartswith=f'{raw}@').first()
        or qs.filter(full_name__iexact=raw).first()
    )


def _already_exists_corner(payload) -> bool:
    return FistulaCornerCase.objects.filter(
        submission__kobo_id=str(payload.get('_id', '')),
    ).exists() if payload.get('_id') else False


def _already_exists_campaign(payload) -> bool:
    return FistulaCampaignVisit.objects.filter(
        submission__kobo_id=str(payload.get('_id', '')),
    ).exists() if payload.get('_id') else False


def _already_exists_daily_campaign(payload) -> bool:
    """Dedupe the daily CHW-activity report on its Kobo submission _id."""
    kobo_id = str(payload.get('_id', '')).strip()
    return (
        FistulaCampaign.objects.filter(kobo_submission_id=kobo_id).exists()
        if kobo_id else False
    )


# ─── Handlers ────────────────────────────────────────────────────────────────

def handle_fistula_corner(payload, lat, lng):
    """spondon_fistula_corner_v1 → FistulaCornerCase."""
    if _already_exists_corner(payload):
        return HttpResponse('OK', status=200)

    FistulaCornerCase.objects.create(
        # PII — encrypted columns accept plaintext
        patient_name=_str(payload.get('patient_name')),
        husband_name=_str(payload.get('husband_name')),
        mobile_number=_str(payload.get('mobile_number') or payload.get('mobile_no')),
        # Non-PII patient
        age_years=_int(payload.get('age_years') or payload.get('age')) or None,
        # Address
        village=_str(payload.get('village')),
        union=_str(payload.get('union')),
        upazila=_str(payload.get('upazila')),
        district=_str(payload.get('district')),
        # Dates
        suspected_date=_date(payload.get('suspected_date')),
        identification_date=_date(payload.get('identification_date')),
        diagnosis_date=_date(payload.get('diagnosis_date')) or timezone.now().date(),
        # Informant
        informant_name=_str(payload.get('informant_name')),
        informant_designation=_str(payload.get('informant_designation')),
        # Clinical
        suffering_duration=_str(payload.get('suffering_duration')),
        fistula_cause=_str(payload.get('fistula_cause')),
        fistula_type=_str(payload.get('fistula_type')).upper(),
        # Service provider
        service_provider_name=_str(payload.get('service_provider_name')),
        service_provider_designation=_str(payload.get('service_provider_designation')),
        # Referral
        referral_date=_date(payload.get('referral_date')),
        referral_place=_str(payload.get('referral_place')),
        surgery_performed=_str(payload.get('surgery_performed')).lower(),
        referral_outcome=_str(payload.get('referral_outcome')),
        remarks=_str(payload.get('remarks')),
        # Provenance
        latitude=lat,
        longitude=lng,
        submitted_by_kobo_user=_str(payload.get('_submitted_by')),
        submitted_by=_resolve_submitter(payload),
    )
    return HttpResponse('Created', status=201)


def handle_fistula_campaign_visit(payload, lat, lng):
    """spondon_fistula_campaign_v1 → FistulaCampaignVisit."""
    if _already_exists_campaign(payload):
        return HttpResponse('OK', status=200)

    FistulaCampaignVisit.objects.create(
        visit_date=_date(payload.get('visit_date') or payload.get('date'))
                    or timezone.now().date(),
        # PII
        patient_name=_str(payload.get('patient_name')),
        husband_name=_str(payload.get('husband_name')),
        contact_number=_str(payload.get('contact_number') or payload.get('mobile_number')),
        # Non-PII
        age_years=_int(payload.get('age_years') or payload.get('age')) or None,
        education=_str(payload.get('education')),
        profession=_str(payload.get('profession')),
        husband_profession=_str(payload.get('husband_profession')),
        # Address
        village=_str(payload.get('village')),
        union=_str(payload.get('union')),
        upazila=_str(payload.get('upazila')),
        district=_str(payload.get('district')),
        from_haor=_bool_or_none(payload.get('from_haor')),
        # Clinical / history
        delivery_mode=_str(payload.get('delivery_mode') or payload.get('mode_of_last_delivery')).lower(),
        delivery_outcome=_str(payload.get('delivery_outcome')).upper(),
        suffering_duration=_str(payload.get('suffering_duration') or payload.get('duration_of_suffering')),
        info_source=_str(payload.get('info_source') or payload.get('source_of_information')),
        remarks=_str(payload.get('remarks')),
        # Provenance
        latitude=lat,
        longitude=lng,
        submitted_by_kobo_user=_str(payload.get('_submitted_by')),
        submitted_by=_resolve_submitter(payload),
    )
    return HttpResponse('Created', status=201)


def handle_ciprb_fistula_campaign(payload, lat, lng):
    """ciprb_fistula_campaign_v1 → FistulaCampaign (daily CHW activity report).

    The rebuilt campaign form is a DAILY activity/reach roll-up (NOT individual
    patient registration). One submission → one FistulaCampaign row, landing
    PENDING for single-stage CIPRB approval. Deduped on the Kobo _id."""
    if _already_exists_daily_campaign(payload):
        return HttpResponse('OK', status=200)

    FistulaCampaign.objects.create(
        partner='CIPRB',
        organisation='CIPRB',
        approval_status='PENDING',
        campaign_date=_date(payload.get('collection_date')) or timezone.now().date(),
        # Location
        district=_str(payload.get('district')),
        upazila=_str(payload.get('upazila')),
        union=_str(payload.get('union')),
        # Staff head-counts
        staff_hi_ahi=_int(payload.get('staff_hi_ahi')),
        staff_ha=_int(payload.get('staff_ha')),
        staff_chcp=_int(payload.get('staff_chcp')),
        staff_fwv=_int(payload.get('staff_fwv')),
        staff_fpi=_int(payload.get('staff_fpi')),
        staff_fwa=_int(payload.get('staff_fwa')),
        staff_chw=_int(payload.get('staff_chw')),
        # Community focal points
        focal_community=_int(payload.get('focal_community')),
        focal_epi=_int(payload.get('focal_epi')),
        focal_fwc=_int(payload.get('focal_fwc')),
        focal_cc=_int(payload.get('focal_cc')),
        # Reach
        households_visited=_int(payload.get('households_visited')),
        population_covered=_int(payload.get('population_covered')),
        # Outcomes (form field → model field)
        suspected_fistula_cases=_int(payload.get('suspected_patients')),
        confirmed_fistula_cases=_int(payload.get('diagnosed_patients')),
        cases_referred=_int(payload.get('referral')),
        cases_surgery_completed=_int(payload.get('surgeries')),
        cases_social_reintegration=_int(payload.get('rehabilitation')),
        # Enumerator
        enumerator_name=_str(payload.get('enumerator_name')),
        enumerator_mobile=_str(payload.get('enumerator_mobile')),
        # Provenance
        kobo_submission_id=_str(payload.get('_id')),
        submitted_by_kobo_user=_str(payload.get('_submitted_by')),
        raw_payload=payload,
        latitude=lat,
        longitude=lng,
    )
    return HttpResponse('Created', status=201)
