import logging
import uuid

from django.db import models

from submissions.flatten import flatten_group_keys

from .derive import derive_fields
from .populations import resolve_population

logger = logging.getLogger(__name__)


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class SurveyType(models.TextChoices):
    BASELINE = 'baseline', 'Baseline'
    ENDLINE = 'endline', 'Endline'


class BaselineSurveyManager(models.Manager):
    def get_or_create_from_submission(self, submission):
        raw = submission.raw_data
        survey_type_raw = (raw.get('survey_type') or '').lower()
        survey_type = SurveyType.ENDLINE if 'endline' in survey_type_raw else SurveyType.BASELINE

        # Animesh's spec — duplication warning on baseline submissions.
        # Flag a survey as duplicate when the same (district, upazila,
        # device/kobo_user, day) already has a survey on file. The manager
        # sees a yellow card on the approval queue and decides whether to
        # accept or reject.
        from datetime import timedelta
        submitted_day = submission.submitted_at.date()
        device_marker = (
            raw.get('deviceid') or raw.get('device_id')
            or submission.kobo_id.split(':')[0] if submission.kobo_id else ''
        )
        district_key = (raw.get('district') or submission.district or '').strip()
        upazila_key = (raw.get('upazila') or '').strip()
        dup_candidate = None
        if district_key and upazila_key:
            dup_candidate = self.filter(
                district__iexact=district_key,
                upazila__iexact=upazila_key,
                survey_date__range=(submitted_day - timedelta(days=1),
                                    submitted_day + timedelta(days=1)),
            ).exclude(submission=submission).order_by('-created_at').first()

        obj, created = self.get_or_create(
            submission=submission,
            defaults={
                'is_duplicate': bool(dup_candidate),
                'duplicate_of': dup_candidate,
                'partner': submission.partner,
                'district': raw.get('district') or submission.district,
                'upazila': raw.get('upazila') or '',
                'union': raw.get('union') or '',
                'facility_name': raw.get('facility_name') or '',
                'region': submission.region,
                'survey_type': survey_type,
                'survey_date': submission.submitted_at.date(),
                'participant_code': raw.get('respondent_id') or '',
                # Respondent profile
                'respondent_age': _safe_int(raw.get('age')),
                'sex': raw.get('sex') or '',
                'education': raw.get('education') or '',
                'ses': raw.get('ses') or '',
                # Family planning
                'fp_use': raw.get('fp_use') or '',
                'fp_method': raw.get('fp_method') or '',
                # Maternal health
                'currently_pregnant': raw.get('currently_pregnant') or '',
                'anc_4visits': raw.get('anc_4visits') or '',
                'skilled_birth_attendant': raw.get('skilled_birth_attendant') or '',
                'danger_signs_knowledge': raw.get('danger_signs_knowledge') or '',
                # Awareness
                'fistula_awareness': raw.get('fistula_awareness') or '',
                'mpdsr_awareness': raw.get('mpdsr_awareness') or '',
                'gbv_awareness': raw.get('gbv_awareness') or '',
                'child_marriage_knowledge': raw.get('child_marriage_knowledge') or '',
                # Access
                'health_facility_distance': raw.get('health_facility_distance') or '',
                'srh_service_satisfaction': raw.get('srh_service_satisfaction') or '',
                'raw_data': raw,
            },
        )
        return obj, created


class BaselineSurvey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.OneToOneField(
        'submissions.KoboSubmission',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='baseline_survey',
    )
    partner = models.CharField(max_length=20, db_index=True)
    district = models.CharField(max_length=100, blank=True)
    upazila = models.CharField(max_length=100, blank=True)
    union = models.CharField(max_length=100, blank=True)
    facility_name = models.CharField(max_length=200, blank=True)
    region = models.CharField(max_length=100, blank=True)

    survey_type = models.CharField(
        max_length=20,
        choices=SurveyType.choices,
        default=SurveyType.BASELINE,
        db_index=True,
    )
    survey_date = models.DateField(null=True, blank=True)
    participant_code = models.CharField(max_length=100, blank=True, db_index=True)

    # Respondent profile
    respondent_age = models.PositiveSmallIntegerField(null=True, blank=True)
    sex = models.CharField(max_length=20, blank=True)
    education = models.CharField(max_length=50, blank=True)
    ses = models.CharField(max_length=50, blank=True)

    # Family planning
    fp_use = models.CharField(max_length=20, blank=True)
    fp_method = models.CharField(max_length=50, blank=True)

    # Maternal health
    currently_pregnant = models.CharField(max_length=20, blank=True)
    anc_4visits = models.CharField(max_length=20, blank=True)
    skilled_birth_attendant = models.CharField(max_length=20, blank=True)
    danger_signs_knowledge = models.CharField(max_length=20, blank=True)

    # Awareness
    fistula_awareness = models.CharField(max_length=20, blank=True)
    mpdsr_awareness = models.CharField(max_length=20, blank=True)
    gbv_awareness = models.CharField(max_length=20, blank=True)
    child_marriage_knowledge = models.CharField(max_length=20, blank=True)

    # Health access
    health_facility_distance = models.CharField(max_length=50, blank=True)
    srh_service_satisfaction = models.CharField(max_length=50, blank=True)

    raw_data = models.JSONField(default=dict)
    is_duplicate = models.BooleanField(default=False, db_index=True)
    duplicate_of = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='duplicates',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BaselineSurveyManager()

    class Meta:
        ordering = ['-survey_date', '-created_at']
        indexes = [
            models.Index(fields=['partner', 'survey_type']),
            models.Index(fields=['participant_code', 'district', 'survey_type']),
        ]

    def __str__(self):
        return f'{self.survey_type} / {self.partner} / {self.district} / {self.survey_date}'


# ─── D5 key-population baseline (Hijra / FSW) — CIPRB-conducted ───────────────
# The generic BaselineSurvey above was built for an assumed maternal-health
# survey and does NOT fit the two validated key-population instruments. These
# land in BaselineResponse: a THIN monitoring projection (the full 184/194-
# question answer set stays whole in raw_data; analysis reads raw_data at report
# time). Distinguished only by `population` (hijra/fsw); partner is always CIPRB.

class BaselineResponseManager(models.Manager):
    def get_or_create_from_submission(self, submission):
        # Flatten Kobo's 'group/field' keys so derived fields resolve, and store the
        # flattened copy so downstream readers see flat names.
        raw = flatten_group_keys(submission.raw_data or {})
        # One derivation, shared with the CSV export (baseline/derive.py) so the
        # export can never disagree with what was stored.
        d = derive_fields(raw, fallback_district=submission.district)
        population = d['population']
        if population is None:
            logger.error('BaselineResponse: population unresolved for submission %s '
                         '(kobo_id=%s) — defaulting to hijra; CHECK THIS RECORD.',
                         submission.id, submission.kobo_id)
            population = 'hijra'
        survey_round = SurveyType.ENDLINE if d['survey_round'] == 'endline' else SurveyType.BASELINE
        serial = d['serial']
        district = d['district']
        site_code = d['site_code']
        age = d['age']
        outcome = d['interview_outcome']

        # Duplicate flag — the serial is the unique key (kept PLAINTEXT; Fernet
        # would break the match). Flag if the same serial is already on file for
        # this population + round.
        dup = None
        if serial:
            dup = (self.filter(population=population, survey_round=survey_round,
                               serial__iexact=serial)
                   .exclude(submission=submission)
                   .order_by('created_at').first())

        obj, created = self.get_or_create(
            submission=submission,
            defaults={
                'population': population,
                'survey_round': survey_round,
                'partner': submission.partner or 'CIPRB',
                'district': district,
                'site_code': site_code,
                'serial': serial,
                'age': age,
                'interview_outcome': outcome,
                'latitude': submission.latitude,
                'longitude': submission.longitude,
                'is_duplicate': bool(dup),
                'duplicate_of': dup,
                'raw_data': raw,
            },
        )
        return obj, created


class BaselineResponse(models.Model):
    """One VERIFIED D5 baseline/endline interview (Hijra or FSW), CIPRB-owned.
    Materialised only when a CIPRB supervisor approves the submission."""
    POPULATION_CHOICES = [
        ('hijra', 'Hijra / Gender-diverse'),
        ('fsw', 'Female Sex Worker'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.OneToOneField(
        'submissions.KoboSubmission',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='baseline_response',
    )
    population = models.CharField(max_length=10, choices=POPULATION_CHOICES, db_index=True)
    survey_round = models.CharField(
        max_length=20, choices=SurveyType.choices,
        default=SurveyType.BASELINE, db_index=True,
    )
    partner = models.CharField(max_length=20, default='CIPRB', db_index=True)
    district = models.CharField(max_length=100, blank=True, db_index=True)
    site_code = models.CharField(max_length=80, blank=True)
    # serial = questionnaire serial; the dedup key. PLAINTEXT, never encrypted.
    serial = models.CharField(max_length=100, blank=True, db_index=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    interview_outcome = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    is_duplicate = models.BooleanField(default=False, db_index=True)
    duplicate_of = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='duplicates',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BaselineResponseManager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['population', 'survey_round']),
            models.Index(fields=['population', 'district']),
            models.Index(fields=['serial', 'population', 'survey_round']),
        ]

    def __str__(self):
        return f'{self.population} / {self.survey_round} / {self.district} / {self.serial}'


# ─── Anomaly review decisions ────────────────────────────────────────────────
# The FSW anomaly engine (baseline/anomaly.py + fsw_rules.py) is deterministic
# and read-only: it NEVER edits raw Kobo data. Human review decisions live here,
# in a SEPARATE audit table keyed on (record_id, rule_id) — one decision per
# flagged anomaly. Correcting the underlying data is done in KoboToolbox; this
# table only records the reviewer's verdict and note.

class AnomalyReview(models.Model):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('confirmed', 'Confirmed'),
        ('corrected', 'Corrected'),
        ('false_positive', 'False positive'),
        ('needs_verification', 'Needs field verification'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The engine's record_id (Kobo _uuid / submission id). Plaintext, immutable.
    submission_id = models.CharField(max_length=200, db_index=True)
    rule_id = models.CharField(max_length=100, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        'accounts.User', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['submission_id', 'rule_id'], name='uniq_anomaly_review'),
        ]
        indexes = [models.Index(fields=['status'])]
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.submission_id} / {self.rule_id} / {self.status}'
