import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import FormType, KoboSubmission, SubmissionStatus

logger = logging.getLogger(__name__)


@receiver(post_save, sender=KoboSubmission)
def on_submission_status_change(sender, instance, **kwargs):
    if instance.status == SubmissionStatus.APPROVED:
        _create_mpdsr_case(instance)
        _create_fistula_campaign(instance)
        _create_baseline_survey(instance)
        _create_baseline_response(instance)
        _create_fistula_staged(instance)
        _create_mpdsr_response_plan(instance)
        _send_approval_telegram(instance)
    elif instance.status == SubmissionStatus.REJECTED:
        _send_rejection_telegram(instance)


def _create_fistula_staged(submission):
    """KF-Fistula_Staged dispatcher — stage-aware update by patient_id.

    On STAGE 1 (suspected) creates a new FistulaCornerCase row.
    On STAGES 2-5, looks up existing row by patient_id and UPDATES the
    fields relevant to that stage. Falls through to a fresh create if no
    matching patient_id is found (degraded: orphan stage update).
    """
    if submission.form_type != FormType.FISTULA_STAGED:
        return
    try:
        from fistula.models import FistulaCornerCase
        from datetime import datetime as _dt

        raw = submission.raw_data or {}
        stage = (raw.get('stage') or '').strip().lower()
        patient_id = (raw.get('patient_id') or raw.get('auto_id_seed') or '').strip()

        # Find or create row
        case = None
        if patient_id:
            case = FistulaCornerCase.objects.filter(patient_id=patient_id).first()
        if not case:
            case = FistulaCornerCase(
                patient_id=patient_id,
                case_hash=(submission.kobo_id[:30] if submission.kobo_id else ''),
                submission=submission,
                source='kobo_staged',
            )

        # Common (Stage 1) suspected-stage fields
        def _set(field, key, transform=lambda v: v):
            v = raw.get(key)
            if v not in (None, ''):
                setattr(case, field, transform(v))

        if stage == 'suspected':
            _set('patient_name', 'pt_name')
            _set('husband_name', 'husband_name')
            _set('mobile_number', 'pt_contact')
            _set('age_years', 'pt_age', int)
            _set('village', 'addr_village')
            _set('union',   'addr_union')
            _set('upazila', 'addr_upazila')
            _set('district', 'district', lambda v: v.replace('_', ' ').title())
            v = raw.get('date_suspected')
            if v:
                case.suspected_date = _safe_date(v)
        elif stage == 'diagnosed':
            v = raw.get('date_diagnosed')
            if v:
                case.diagnosis_date = _safe_date(v)
            _set('facility_name', 'place_diagnosed') if hasattr(case, 'facility_name') else None
        elif stage == 'referred':
            v = raw.get('refer_date')
            if v:
                case.referral_date = _safe_date(v)
            _set('referral_place', 'refer_place')
            _set('referral_outcome', 'refer_outcome')
        elif stage == 'repaired':
            v = raw.get('op_date')
            if v:
                # Surgery completion implies surgery_performed=yes
                case.surgery_performed = 'yes'
            _set('fistula_type', 'cause_type', lambda v: v.title())
            _set('fistula_anatomy', 'fistula_anatomy', lambda v: v.upper())
            _set('fistula_cause', 'cause_iatrogenic')
            # Surgical outcome category (dry / not-dry / failed) — the Kobo
            # op_outcome values map 1:1 to FistulaCornerCase.OUTCOME_* codes.
            _set('surgery_outcome', 'op_outcome')
        elif stage == 'rehabilitated':
            v = raw.get('rehab_received')
            if v == 'yes':
                case.received_rehab_support = True
                types = raw.get('rehab_types') or ''
                case.rehab_support_types = (
                    types.replace(' ', ',') if isinstance(types, str) else ''
                )
                d = raw.get('rehab_date')
                if d:
                    case.rehab_support_date = _safe_date(d)
            else:
                case.received_rehab_support = False

        # Latitude / longitude per submission
        if submission.latitude is not None:
            case.latitude = submission.latitude
        if submission.longitude is not None:
            case.longitude = submission.longitude

        case.save()
    except Exception as exc:
        logger.error(
            'FistulaCornerCase staged update failed for submission %s: %s',
            submission.id, exc,
        )


def _create_mpdsr_response_plan(submission):
    """KF-MPDSR_Response_Plan dispatcher — one or more MPDSRActionPlanSummary
    rows per submission. Spec from Sayed's MPDSR Response Plan_2026.docx:
    3 sections × up to 5 actions × 7 fields. We collapse each section
    into a single MPDSRActionPlanSummary row keyed by (district, level,
    meeting_date, section).
    """
    if submission.form_type != FormType.MPDSR_RESPONSE_PLAN:
        return
    try:
        from mpdsr.models import MPDSRActionPlanSummary
        raw = submission.raw_data or {}

        district = (raw.get('district') or submission.district or '').replace('_', ' ').title()
        level = (raw.get('meeting_level') or 'DM').upper()
        place = raw.get('place_of_meeting') or ''
        meeting_date = _safe_date(raw.get('meeting_date'))
        participants = raw.get('participants_count')
        try:
            participants = int(participants) if participants not in (None, '') else None
        except (TypeError, ValueError):
            participants = None

        SECTION_LABELS = {
            'sys_strengthen': 'MPDSR System Strengthening',
            'community_va': 'Community Verbal Autopsy',
            'facility_dr': 'Facility Death Review',
        }
        planned = 0
        implemented = 0
        actions = []  # full per-action matrix for the dashboard
        for sec, sec_label in SECTION_LABELS.items():
            for i in range(1, 6):
                action = raw.get(f'{sec}_a{i}_action_taken')
                if not (action and str(action).strip()):
                    continue
                status = (raw.get(f'{sec}_a{i}_status') or '').lower()
                planned += 1
                if status == 'implemented':
                    implemented += 1
                actions.append({
                    'section': sec_label,
                    'action': str(action).strip(),
                    'responsible': raw.get(f'{sec}_a{i}_responsible') or '',
                    'timeline': raw.get(f'{sec}_a{i}_timeline') or '',
                    'indicator': raw.get(f'{sec}_a{i}_indicator') or '',
                    'milestone': raw.get(f'{sec}_a{i}_milestone') or '',
                    'considerations': raw.get(f'{sec}_a{i}_considerations') or '',
                    'status': status,
                })
        if planned == 0:
            return
        md_str = meeting_date.isoformat() if meeting_date else ''
        obj, _ = MPDSRActionPlanSummary.objects.update_or_create(
            district=district,
            level=level,
            meeting_date=md_str,
            place_of_meeting=place or 'CIPRB MPDSR Meeting',
            defaults={
                'participants': participants,
                'meetings_planned': 1,
                'activities_planned': planned,
                'activities_implemented': implemented,
                'actions': actions,
                'source': 'kobo_response_plan',
            },
        )
    except Exception as exc:
        logger.error(
            'MPDSRActionPlanSummary update failed for submission %s: %s',
            submission.id, exc,
        )


def _safe_date(v):
    if not v:
        return None
    from datetime import datetime, date
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(s[:len(fmt) + 4], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _create_mpdsr_case(submission):
    if submission.form_type != FormType.MPDSR:
        return
    try:
        from mpdsr.models import MPDSRCase
        MPDSRCase.objects.get_or_create_from_submission(submission)
    except Exception as exc:
        logger.error('MPDSRCase creation failed for submission %s: %s', submission.id, exc)


def _create_fistula_campaign(submission):
    if submission.form_type != FormType.FISTULA:
        return
    try:
        from fistula.models import FistulaCampaign
        FistulaCampaign.objects.get_or_create_from_submission(submission)
    except Exception as exc:
        logger.error('FistulaCampaign creation failed for submission %s: %s', submission.id, exc)


def _is_keypop_baseline(submission):
    """True for the D5 key-population instruments (Hijra / FSW) — they
    materialise into BaselineResponse, NOT the legacy generic BaselineSurvey.

    The deployed forms set a hidden `population` calc ('hijra'/'fsw'), so a live
    submission carries it. But if that calc didn't land in raw_data (e.g. an
    Enketo preview that skips calculates), we still route correctly: ANY baseline
    form whose id is not the legacy `spondon_baseline_v1` is a key-population
    interview. Without this fallback, approval silently materialised nothing and
    the baseline tab stayed empty."""
    raw = submission.raw_data or {}
    if (raw.get('population') or '').lower() in ('hijra', 'fsw'):
        return True
    xf = (raw.get('_xform_id_string') or raw.get('_xform_id') or '').lower()
    if 'hijra' in xf or 'fsw' in xf:
        return True
    # Any BASELINE submission that is not the legacy generic survey is a
    # key-population interview → BaselineResponse.
    if xf and 'spondon_baseline' not in xf:
        return True
    return False


def _create_baseline_survey(submission):
    if submission.form_type != FormType.BASELINE:
        return
    # The new key-population instruments go to BaselineResponse instead; keep
    # the legacy generic survey only for the old spondon_baseline_v1 form.
    if _is_keypop_baseline(submission):
        return
    try:
        from baseline.models import BaselineSurvey
        BaselineSurvey.objects.get_or_create_from_submission(submission)
    except Exception as exc:
        logger.error('BaselineSurvey creation failed for submission %s: %s', submission.id, exc)


def _create_baseline_response(submission):
    if submission.form_type != FormType.BASELINE:
        return
    if not _is_keypop_baseline(submission):
        logger.warning(
            'Baseline submission %s approved but not recognised as a key-population '
            'interview (no population field / xform id) — BaselineResponse NOT created.',
            submission.id)
        return
    try:
        from baseline.models import BaselineResponse
        obj, created = BaselineResponse.objects.get_or_create_from_submission(submission)
        logger.info('BaselineResponse %s for submission %s (created=%s)',
                    obj.id, submission.id, created)
    except Exception as exc:
        logger.error('BaselineResponse creation failed for submission %s: %s', submission.id, exc)


def _send_approval_telegram(submission):
    try:
        from .notify import send_approval_confirmation
        send_approval_confirmation(submission)
    except Exception as exc:
        logger.error('Approval Telegram failed for submission %s: %s', submission.id, exc)


def _send_rejection_telegram(submission):
    try:
        from .notify import send_rejection_notification
        send_rejection_notification(submission)
    except Exception as exc:
        logger.error('Rejection Telegram failed for submission %s: %s', submission.id, exc)
