"""
Server-issued system reference numbers for CIPRB surveillance records.

CIPRB asked (2026-08-11) for an automatic ID on every form. Each record gets
<FORM CODE>-<DISTRICT CODE>-<NNNN>, e.g. NS1-BH-0042 = Bhola's 42nd
Notification Slip 01. District codes reuse mpdsr.models.DISTRICT_ACTION_CODE
(the PA-001 action-ID letters) so the programme has ONE district alphabet.

Design notes:
  * The ref is allocated AFTER the record row exists, with the same
    UNIQUE-constraint arbitration as the Bandhu/fistula ID issuance: read the
    current maximum, try to save, retry on IntegrityError. No counter table.
  * The worker's hand-written paper serial stays on the record untouched —
    it is the bridge to the paper register. The system ref is the identity
    the programme quotes.
  * Best-effort write-back puts the ref on the Kobo submission (daemon
    thread; a Kobo outage never fails the ingestion).
  * MUST be called OUTSIDE the handler's select_for_update atomic block —
    an IntegrityError inside a wrapping transaction would poison it.
"""
import logging

from django.db import IntegrityError, transaction

from mpdsr.models import DISTRICT_ACTION_CODE
from programs.bandhu_handlers import _writeback_kobo_id
from programs.ciprb_replay import CIPRB_SLUG_TO_UID

logger = logging.getLogger(__name__)

# sub_form_type / slip_variant → the code the ref starts with.
MPDSR_FORM_CODE = {
    'f1': 'F1', 'f2': 'F2', 'f4': 'F4', 'f5': 'F5',
    'f3': 'F3', 'f6': 'F6',
    'sa_md': 'SA', 'sa_nd': 'SA', 'va_md': 'VA',
}
SLIP_FORM_CODE = {'01': 'NS1', '02': 'NS2'}
NEAR_MISS_FORM_CODE = 'NM'
# Safe Surgery Checklist (CIPRB-11): the automatic operation ID reads SS-DH-0007.
SURGERY_FORM_CODE = 'SS'

# form code → Kobo asset slug, for the write-back.
_FORM_CODE_TO_SLUG = {
    'F1': 'ciprb_mpdsr_community_maternal_v1',
    'F2': 'ciprb_mpdsr_community_neonatal_v1',
    'F4': 'ciprb_mpdsr_facility_maternal_v1',
    'F5': 'ciprb_mpdsr_facility_neonatal_v1',
    'SA': 'ciprb_social_autopsy_v1',
    'NS1': 'ciprb_notification_slip_01_v1',
    'NS2': 'ciprb_notification_slip_02_v1',
    'NM': 'ciprb_near_miss_v1',
    'SS': 'ciprb_safe_surgery_v1',
}


def district_letters(district: str) -> str:
    return DISTRICT_ACTION_CODE.get((district or '').strip().title(), 'XX')


def allocate_system_ref(obj, form_code: str, *, writeback: bool = True,
                        tries: int = 40) -> str | None:
    """Stamp obj.system_ref (idempotent — an already-stamped row keeps its ref).

    `obj` must already be saved (the ref lands via update_fields). Returns the
    ref, or None if allocation lost 40 straight races (logged, never raised —
    the record itself must survive even if the decoration fails).
    """
    if obj.system_ref:
        return obj.system_ref

    prefix = f'{form_code}-{district_letters(getattr(obj, "district", ""))}-'
    model = type(obj)
    for _ in range(tries):
        used = (model.objects
                .filter(system_ref__startswith=prefix)
                .values_list('system_ref', flat=True))
        nums = [int(s[len(prefix):]) for s in used
                if s[len(prefix):].isdigit()]
        obj.system_ref = f'{prefix}{(max(nums) if nums else 0) + 1:04d}'
        try:
            with transaction.atomic():
                obj.save(update_fields=['system_ref'])
            break
        except IntegrityError:
            continue
    else:
        logger.error('system_ref allocation exhausted retries for %s', prefix)
        obj.system_ref = None
        return None

    kobo_id = getattr(obj, 'kobo_submission_id', '')
    asset_uid = CIPRB_SLUG_TO_UID.get(_FORM_CODE_TO_SLUG.get(form_code, ''), '')
    if writeback and kobo_id and asset_uid:
        _writeback_kobo_id(asset_uid, kobo_id, obj.system_ref,
                           field_path='system_ref')
    return obj.system_ref
