import logging
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

logger = logging.getLogger('programs')


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ─── PII encryption helpers ──────────────────────────────────────────────────
# Same Fernet pattern programs.models.gbv uses — survivor name, husband name
# and mobile are encrypted at rest. FERNET_KEY env var (set in Step B Railway
# block) drives the cipher. When the key is absent the field passes through
# as plaintext so dev/test environments don't crash. Production asserts the
# key is present (spondon/settings/production.py), so the passthrough never
# stores PII in cleartext on a real deployment.

# Delegated to fistula.encryption — the single place that knows about
# FERNET_KEY + FERNET_KEY_FALLBACKS. See the note in programs/models/gbv.py:
# a local copy of this logic would not honour the rotation fallback key and
# would blank PII during a key rotation. Ciphertext format is unchanged, so
# existing rows are unaffected.
from .encryption import _enc as _encrypt, _dec as _decrypt  # noqa: E402


class EncryptedCharField(models.TextField):
    """Transparent Fernet-encrypt on save, decrypt on access."""

    def from_db_value(self, value, expression, connection):
        return _decrypt(value) if value else value

    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)
        encrypted = _encrypt(value)
        setattr(model_instance, self.attname, encrypted)
        return encrypted


class FistulaCampaignManager(models.Manager):
    def get_or_create_from_submission(self, submission):
        raw = submission.raw_data

        obj, created = self.get_or_create(
            submission=submission,
            defaults={
                'partner': submission.partner,
                'district': raw.get('district') or submission.district,
                'upazila': raw.get('upazila') or '',
                'union': raw.get('union') or '',
                'village': raw.get('village') or '',
                'facility_name': raw.get('facility_name') or '',
                'region': submission.region,
                'latitude': submission.latitude,
                'longitude': submission.longitude,
                'campaign_date': submission.submitted_at.date(),
                # Reach
                'women_screened': _safe_int(raw.get('women_screened')),
                'women_reached_awareness': _safe_int(raw.get('women_reached_awareness')),
                'men_reached_awareness': _safe_int(raw.get('men_reached_awareness')),
                'community_sessions': _safe_int(raw.get('community_sessions')),
                # Cases
                'suspected_fistula_cases': _safe_int(raw.get('suspected_fistula_cases')),
                'confirmed_fistula_cases': _safe_int(raw.get('confirmed_fistula_cases')),
                'new_cases': _safe_int(raw.get('new_cases')),
                'repeat_cases': _safe_int(raw.get('repeat_cases')),
                'fistula_type': raw.get('fistula_type') or '',
                'fistula_cause': raw.get('fistula_cause') or '',
                # Referral
                'cases_referred': _safe_int(raw.get('cases_referred')),
                'cases_accepted_referral': _safe_int(raw.get('cases_accepted_referral')),
                'cases_reached_facility': _safe_int(raw.get('cases_reached_facility')),
                # Surgery
                'cases_surgery_completed': _safe_int(raw.get('cases_surgery_completed')),
                'cases_surgery_pending': _safe_int(raw.get('cases_surgery_pending')),
                'cases_surgery_not_eligible': _safe_int(raw.get('cases_surgery_not_eligible')),
                # Follow-up
                'cases_followup_due': _safe_int(raw.get('cases_followup_due')),
                'cases_followup_completed': _safe_int(raw.get('cases_followup_completed')),
                'cases_lost_followup': _safe_int(raw.get('cases_lost_followup')),
                # Psychosocial
                'cases_counselling_provided': _safe_int(raw.get('cases_counselling_provided')),
                'cases_social_reintegration': _safe_int(raw.get('cases_social_reintegration')),
                # Barriers
                'main_barriers': raw.get('main_barriers') or '',
                'notes': raw.get('notes') or '',
            },
        )
        return obj, created


class FistulaCampaign(models.Model):
    # Approval workflow — single-stage CIPRB (Tanjina/Setu), mirroring
    # CIPRBFistulaCase. The webhook handler sets a NEW daily report to PENDING;
    # the manager finalises it in the shared /approvals queue.
    APPROVAL_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_hash = models.CharField(max_length=30, unique=True, blank=True, db_index=True)

    submission = models.OneToOneField(
        'submissions.KoboSubmission',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='fistula_campaign',
    )
    partner = models.CharField(max_length=20, db_index=True)
    organisation = models.CharField(max_length=20, default='CIPRB', db_index=True)
    district = models.CharField(max_length=100, blank=True)
    upazila = models.CharField(max_length=100, blank=True)
    union = models.CharField(max_length=100, blank=True)
    village = models.CharField(max_length=200, blank=True)
    facility_name = models.CharField(max_length=200, blank=True)
    region = models.CharField(max_length=100, blank=True)

    campaign_date = models.DateField()

    # Reach
    women_screened = models.PositiveIntegerField(default=0)
    women_reached_awareness = models.PositiveIntegerField(default=0)
    men_reached_awareness = models.PositiveIntegerField(default=0)
    community_sessions = models.PositiveSmallIntegerField(default=0)

    # Animesh's spec — campaign scale metrics (visible as top-line tiles on
    # the CIPRB dashboard). The 'Sunamganj-Daily Data Sheet' xlsx column
    # '# of Households Visited' maps to households_visited, and 'No of
    # population covered' maps to population_covered.
    households_visited = models.PositiveIntegerField(default=0)
    population_covered = models.PositiveIntegerField(default=0)

    # ── Daily CHW-activity staff head-counts (rebuilt daily campaign form).
    #    Cadre abbreviations kept as-is: HI/AHI, HA, CHCP, FWV, FPI, FWA, CHW.
    staff_hi_ahi = models.PositiveIntegerField(default=0)
    staff_ha     = models.PositiveIntegerField(default=0)
    staff_chcp   = models.PositiveIntegerField(default=0)
    staff_fwv    = models.PositiveIntegerField(default=0)
    staff_fpi    = models.PositiveIntegerField(default=0)
    staff_fwa    = models.PositiveIntegerField(default=0)
    staff_chw    = models.PositiveIntegerField(default=0)
    # Community focal points engaged that day.
    focal_community = models.PositiveIntegerField(default=0)
    focal_epi       = models.PositiveIntegerField(default=0)
    focal_fwc       = models.PositiveIntegerField(default=0)
    focal_cc        = models.PositiveIntegerField(default=0)

    # Case identification
    suspected_fistula_cases = models.PositiveSmallIntegerField(default=0)
    confirmed_fistula_cases = models.PositiveSmallIntegerField(default=0)
    new_cases = models.PositiveSmallIntegerField(default=0)
    repeat_cases = models.PositiveSmallIntegerField(default=0)
    fistula_type = models.CharField(max_length=300, blank=True)
    fistula_cause = models.CharField(max_length=300, blank=True)

    # Referral
    cases_referred = models.PositiveSmallIntegerField(default=0)
    cases_accepted_referral = models.PositiveSmallIntegerField(default=0)
    cases_reached_facility = models.PositiveSmallIntegerField(default=0)

    # Surgery
    cases_surgery_completed = models.PositiveSmallIntegerField(default=0)
    cases_surgery_pending = models.PositiveSmallIntegerField(default=0)
    cases_surgery_not_eligible = models.PositiveSmallIntegerField(default=0)

    # Follow-up
    cases_followup_due = models.PositiveSmallIntegerField(default=0)
    cases_followup_completed = models.PositiveSmallIntegerField(default=0)
    cases_lost_followup = models.PositiveSmallIntegerField(default=0)

    # Psychosocial
    cases_counselling_provided = models.PositiveSmallIntegerField(default=0)
    cases_social_reintegration = models.PositiveSmallIntegerField(default=0)

    main_barriers = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)

    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    # ── Enumerator (person filling the daily form).
    enumerator_name = models.CharField(max_length=200, blank=True)
    enumerator_mobile = models.CharField(max_length=30, blank=True)

    # ── Kobo provenance / audit.
    kobo_submission_id = models.CharField(max_length=100, blank=True, default='')
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True, default='')
    raw_payload = models.JSONField(default=dict, blank=True)

    # ── Manager approval (single-stage CIPRB — Tanjina/Setu). NEW daily reports
    #    land PENDING via the webhook handler; the shared queue approves them.
    approval_status = models.CharField(
        max_length=20, choices=APPROVAL_CHOICES, default='PENDING', db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, default='')
    # Queue-infrastructure parity only: the shared approval queue unconditionally
    # select_related's 'center'. Fistula is district-based (no ServiceCenter), so
    # this stays NULL and the queue renders '–' — but the column must EXIST or the
    # join raises FieldError and 500s the whole queue. (Same note as CIPRBFistulaCase.)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='fistula_campaigns_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FistulaCampaignManager()

    class Meta:
        ordering = ['-campaign_date', '-created_at']
        verbose_name = 'Fistula Campaign Session'
        verbose_name_plural = 'Fistula Campaign Sessions'
        indexes = [
            models.Index(fields=['partner', 'campaign_date']),
            models.Index(fields=['district', 'campaign_date']),
        ]

    def save(self, *args, **kwargs):
        if not self.case_hash:
            year = self.campaign_date.year if self.campaign_date else timezone.now().year
            prefix = 'CIP' if self.partner == 'CIPRB' else ('PHD' if self.partner == 'PHD' else 'BON')
            count = (
                FistulaCampaign.objects
                .filter(partner=self.partner, campaign_date__year=year)
                .count() + 1
            )
            self.case_hash = f'FST-{prefix}-{year}-{count:04d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.case_hash} — {self.district} ({self.campaign_date})'


# ────────────────────────────────────────────────────────────────────────────
#  FistulaCornerCase — per-patient diagnosis at District Hospital Fistula Corner
#  Source: প্রসবজনিত ফিস্টুলা রেজিস্ট্রার (Bengali register photo)
#  Activity code: F.C
# ────────────────────────────────────────────────────────────────────────────

class FistulaCornerCase(models.Model):
    """
    One row per woman diagnosed with obstetric fistula at a District Hospital
    Fistula Corner. Mirrors the paper register: patient + address + clinical
    findings + referral chain. PII (name, husband name, mobile) encrypted
    at rest via Fernet — same pattern as programs.GBVCase.
    """

    # Fistula types — V.V.F most common, also R.V.F and combined.
    VVF = 'VVF'
    RVF = 'RVF'
    BOTH = 'BOTH'
    OTHER = 'OTHER'
    FISTULA_TYPE_CHOICES = [
        (VVF,   'V.V.F (Vesico-Vaginal Fistula)'),
        (RVF,   'R.V.F (Recto-Vaginal Fistula)'),
        (BOTH,  'V.V.F + R.V.F (Combined)'),
        (OTHER, 'Other'),
    ]

    # Surgery outcome on referral.
    SURGERY_YES = 'yes'
    SURGERY_NO = 'no'
    SURGERY_PENDING = 'pending'
    SURGERY_CHOICES = [
        (SURGERY_YES,     'Yes'),
        (SURGERY_NO,      'No'),
        (SURGERY_PENDING, 'Pending'),
    ]

    # Surgical outcome category (Animesh's spec / GoB Fistula form):
    # Successful and dry / Successful and not dry / Failed.
    # Dashboard reports the two "successful" categories; Failed tracked
    # but de-emphasised per Animesh + Sayed's reporting decision.
    OUTCOME_DRY = 'success_dry'
    OUTCOME_NOT_DRY = 'success_not_dry'
    OUTCOME_FAILED = 'failed'
    OUTCOME_CHOICES = [
        (OUTCOME_DRY,     'Successfully repaired and dry'),
        (OUTCOME_NOT_DRY, 'Successfully repaired but not dry'),
        (OUTCOME_FAILED,  'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_hash = models.CharField(max_length=30, unique=True, blank=True, db_index=True)

    # Auto-ID from KF-Fistula_Staged form. One patient → one row; subsequent
    # stage submissions look up by this patient_id and UPDATE the existing
    # row instead of creating a new one. Format: DISTRICT-YYYY-<6char>.
    patient_id = models.CharField(max_length=50, blank=True, db_index=True)

    submission = models.OneToOneField(
        'submissions.KoboSubmission',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='fistula_corner_case',
    )

    # ─── Patient PII (encrypted) ─────────────────────────────────────────
    patient_name = EncryptedCharField(blank=True)
    husband_name = EncryptedCharField(blank=True)
    mobile_number = EncryptedCharField(blank=True)

    # ─── Patient non-PII ─────────────────────────────────────────────────
    age_years = models.PositiveSmallIntegerField(null=True, blank=True)

    # ─── Address ─────────────────────────────────────────────────────────
    village  = models.CharField(max_length=200, blank=True)
    union    = models.CharField(max_length=100, blank=True)
    upazila  = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True, db_index=True)

    # ─── Dates ───────────────────────────────────────────────────────────
    suspected_date     = models.DateField(null=True, blank=True)
    identification_date = models.DateField(null=True, blank=True)
    diagnosis_date     = models.DateField(null=True, blank=True, db_index=True)

    # ─── Informant ───────────────────────────────────────────────────────
    informant_name      = EncryptedCharField(blank=True)   # Fernet at rest
    informant_designation = models.CharField(max_length=200, blank=True)

    # ─── Clinical ────────────────────────────────────────────────────────
    suffering_duration = models.CharField(
        max_length=100, blank=True,
        help_text='Free-text duration — e.g. "৩ বছর", "8 মাস".',
    )
    fistula_cause = models.CharField(
        max_length=300, blank=True,
        help_text='Free-text — e.g. "দীর্ঘ সময়ের প্রসব" (prolonged labour).',
    )
    fistula_type = models.CharField(
        max_length=10, choices=FISTULA_TYPE_CHOICES, blank=True,
        help_text='V.V.F / R.V.F / Combined / Other.',
    )

    # ─── Service provider ────────────────────────────────────────────────
    service_provider_name        = models.CharField(max_length=200, blank=True)
    service_provider_designation = models.CharField(max_length=200, blank=True)

    # ─── Referral chain ──────────────────────────────────────────────────
    referral_date     = models.DateField(null=True, blank=True)
    referral_place    = models.CharField(max_length=200, blank=True)
    surgery_performed = models.CharField(
        max_length=10, choices=SURGERY_CHOICES, blank=True,
    )
    surgery_outcome = models.CharField(
        max_length=20, choices=OUTCOME_CHOICES, blank=True, db_index=True,
        help_text='Clinical outcome for repaired cases: dry / not-dry / failed.',
    )
    referral_outcome  = models.TextField(blank=True)

    # ─── Rehabilitation & Reintegration ──────────────────────────────────
    # Per Animesh in the 2026-06-01 meeting: a patient counts as
    # "Rehabilitated" if ANY of cash / livestock / training / tree plant /
    # sewing machine / VGF card / disability card / psychosocial support /
    # reintegration support is recorded. The boolean below is the umbrella
    # "did the patient receive ANY rehab support" flag; the CharField
    # captures which types as a comma-separated list (audit detail).
    received_rehab_support = models.BooleanField(default=False, db_index=True)
    rehab_support_types = models.CharField(
        max_length=300, blank=True,
        help_text='Comma-separated: Cash, Livestock, Training, Tree plant, '
                  'Sewing machine, VGF Card, Disability card, Psychosocial '
                  'support, Reintegration support',
    )
    rehab_support_date = models.DateField(null=True, blank=True)

    # ─── Remarks ─────────────────────────────────────────────────────────
    remarks = models.TextField(blank=True)

    # ─── Provenance ──────────────────────────────────────────────────────
    latitude  = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Provenance: 'kobo' (live submission) or 'excel_fistula_2026_q1' etc.
    # for records ingested from Sayeed's Excel files as historical baseline.
    source = models.CharField(max_length=40, default='kobo', db_index=True)

    class Meta:
        ordering = ['-diagnosis_date', '-created_at']
        verbose_name = 'Fistula Corner Case'
        verbose_name_plural = 'Fistula Corner Cases'
        indexes = [
            models.Index(fields=['district', '-diagnosis_date']),
            models.Index(fields=['fistula_type']),
        ]

    def save(self, *args, **kwargs):
        if not self.case_hash:
            year = (self.diagnosis_date or self.suspected_date or timezone.now().date()).year
            count = FistulaCornerCase.objects.filter(
                diagnosis_date__year=year,
            ).count() + 1
            self.case_hash = f'FC-{year}-{count:04d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.case_hash} — {self.district} ({self.fistula_type or "?"})'


# ────────────────────────────────────────────────────────────────────────────
#  FistulaCampaignVisit — per-suspected-patient house-visit screening record
#  Source: xlsx individual sheet ("Sunamganj_Individual")
#  Activity code: F.Camp
# ────────────────────────────────────────────────────────────────────────────

class FistulaCampaignVisit(models.Model):
    """
    One row per woman identified as a suspected fistula case during the
    house-to-house screening campaign. Different from the aggregate
    FistulaCampaign model (which captures daily roll-ups).

    The xlsx "Sunamganj_Individual" sheet maps directly here.
    """

    DELIVERY_LB = 'LB'   # Live Birth
    DELIVERY_SB = 'SB'   # Still Birth
    DELIVERY_UNKNOWN = 'UNK'
    DELIVERY_OUTCOME_CHOICES = [
        (DELIVERY_LB,      'Live Birth'),
        (DELIVERY_SB,      'Still Birth'),
        (DELIVERY_UNKNOWN, 'Unknown'),
    ]

    MODE_HOME = 'home'
    MODE_FACILITY = 'facility'
    MODE_OTHER = 'other'
    DELIVERY_MODE_CHOICES = [
        (MODE_HOME,     'Home'),
        (MODE_FACILITY, 'Facility'),
        (MODE_OTHER,    'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_hash = models.CharField(max_length=30, unique=True, blank=True, db_index=True)

    submission = models.OneToOneField(
        'submissions.KoboSubmission',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='fistula_campaign_visit',
    )

    visit_date = models.DateField(db_index=True)

    # ─── Patient PII (encrypted) ─────────────────────────────────────────
    patient_name  = EncryptedCharField(blank=True)
    husband_name  = EncryptedCharField(blank=True)
    contact_number = EncryptedCharField(blank=True)

    # ─── Patient non-PII ─────────────────────────────────────────────────
    age_years          = models.PositiveSmallIntegerField(null=True, blank=True)
    education          = models.CharField(max_length=100, blank=True)
    profession         = models.CharField(max_length=200, blank=True)
    husband_profession = models.CharField(max_length=200, blank=True)

    # ─── Address ─────────────────────────────────────────────────────────
    village  = models.CharField(max_length=200, blank=True)
    union    = models.CharField(max_length=100, blank=True)
    upazila  = models.CharField(max_length=100, blank=True)
    district = models.CharField(max_length=100, blank=True, db_index=True)
    from_haor = models.BooleanField(null=True, blank=True,
        help_text='Patient lives in a Haor (wetland) area.')

    # ─── Clinical / obstetric history ────────────────────────────────────
    delivery_mode    = models.CharField(max_length=20, choices=DELIVERY_MODE_CHOICES, blank=True)
    delivery_outcome = models.CharField(max_length=10, choices=DELIVERY_OUTCOME_CHOICES, blank=True)
    suffering_duration = models.CharField(
        max_length=100, blank=True,
        help_text='Free-text — e.g. "30 years", "8 years".',
    )
    info_source = models.CharField(
        max_length=100, blank=True,
        help_text='Who reported the suspected case — DRC / FWA / Midwife / Self.',
    )

    remarks = models.TextField(blank=True)

    # ─── Provenance ──────────────────────────────────────────────────────
    latitude  = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-visit_date', '-created_at']
        verbose_name = 'Fistula Campaign Visit'
        verbose_name_plural = 'Fistula Campaign Visits'
        indexes = [
            models.Index(fields=['district', '-visit_date']),
            models.Index(fields=['union', '-visit_date']),
        ]

    def save(self, *args, **kwargs):
        if not self.case_hash:
            year = (self.visit_date or timezone.now().date()).year
            count = FistulaCampaignVisit.objects.filter(visit_date__year=year).count() + 1
            self.case_hash = f'FCAMP-{year}-{count:04d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.case_hash} — {self.district} ({self.visit_date})'


# ── CIPRB Phase 2 model (Fistula Question Bank). Imported here so it
#    appears in Django's model registry alongside the legacy fistula models.
from .ciprb_models import CIPRBFistulaCase  # noqa: F401,E402
