"""
Detect duplicate BaselineSurvey submissions.

A duplicate is defined as a survey with the same (participant_code, district, survey_type)
that already exists in the database.  The newer record is flagged as duplicate.
"""
import logging
import uuid

logger = logging.getLogger(__name__)


def flag_duplicates_for_partner(partner: str) -> int:
    """
    Scan all BaselineSurvey records for `partner` and flag any duplicates.
    Returns the number of records newly flagged.
    """
    from .models import BaselineSurvey

    # Reset existing flags so we do a clean re-scan
    BaselineSurvey.objects.filter(partner=partner).update(is_duplicate=False, duplicate_of=None)

    seen: dict[tuple, uuid.UUID] = {}
    flagged = 0

    surveys = (
        BaselineSurvey.objects
        .filter(partner=partner)
        .exclude(participant_code='')
        .order_by('survey_date', 'created_at')
    )

    for survey in surveys:
        key = (survey.participant_code, survey.district, survey.survey_type)
        if key in seen:
            survey.is_duplicate = True
            survey.duplicate_of_id = seen[key]
            survey.save(update_fields=['is_duplicate', 'duplicate_of'])
            flagged += 1
            logger.info('Flagged duplicate: %s (original: %s)', survey.id, seen[key])
        else:
            seen[key] = survey.id

    return flagged


def check_new_survey(survey) -> bool:
    """
    Check a single newly created BaselineSurvey against existing records.
    Returns True if it is a duplicate (and marks it as such in-place).
    """
    from .models import BaselineSurvey

    if not survey.participant_code:
        return False

    existing = (
        BaselineSurvey.objects
        .filter(
            participant_code=survey.participant_code,
            district=survey.district,
            survey_type=survey.survey_type,
            partner=survey.partner,
        )
        .exclude(id=survey.id)
        .order_by('survey_date', 'created_at')
        .first()
    )

    if existing:
        survey.is_duplicate = True
        survey.duplicate_of = existing
        survey.save(update_fields=['is_duplicate', 'duplicate_of'])
        return True

    return False
