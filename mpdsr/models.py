import datetime
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ReviewStatus(models.TextChoices):
    REPORTED = 'reported', 'Reported'
    UNDER_REVIEW = 'under_review', 'Under Review'
    COMMITTEE_REVIEW = 'committee_review', 'Committee Review'
    ACTION_PLAN_DRAFTED = 'action_plan_drafted', 'Action Plan Drafted'
    CLOSED = 'closed', 'Closed'


class DeathType(models.TextChoices):
    MATERNAL = 'maternal', 'Maternal Death'
    PERINATAL = 'perinatal', 'Perinatal / Neonatal'


class PlaceOfDeath(models.TextChoices):
    FACILITY = 'facility', 'Health Facility'
    HOME = 'home', 'Home'
    IN_TRANSIT = 'in_transit', 'In Transit / On the Way'


# Maps sub-form name → human label (F1–F6 from MPDSR combined form,
# plus the review types Animesh specified in the 2026-06-02 meeting:
# Community MD Review (CDN) via verbal autopsy, Facility MD Review (FDR),
# and Social Autopsy).
# Labels follow the VERBATIM form suite live since 23 June 2026. The old map
# predated it and called f1/f2 "notifications", so every community review sat
# mislabelled in the approval queue (notifications are a separate model with
# their own slips; these are the REVIEW forms).
SUB_FORM_LABELS = {
    'f1': 'Form 01 · Community Maternal Death Review',
    'f2': 'Form 02 · Community Neonatal Death Review',
    'f3': 'F3 Community Stillbirth Review (legacy)',
    'f4': 'Form 04 · Facility Maternal Death Review',
    'f5': 'Form 05 · Facility Neonatal Death Review',
    'f6': 'F6 Facility Stillbirth Review (legacy)',
    'va_md': 'Community Verbal Autopsy (Maternal)',
    'sa_md': 'Form 06 · Social Autopsy',
}

# Sub-forms that are always perinatal/neonatal regardless of death_type field
_PERINATAL_FORMS = {'f3', 'f5', 'f6'}
# Sub-forms that are always maternal
_MATERNAL_FORMS = {'f4'}


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first(*args):
    for v in args:
        if v:
            return v
    return ''


class MPDSRCaseManager(models.Manager):
    def get_or_create_from_submission(self, submission):
        raw = submission.raw_data
        sub = (raw.get('form_type') or '').strip().lower()

        # ----- death type -----
        if sub in _PERINATAL_FORMS:
            death_type = DeathType.PERINATAL
        elif sub in _MATERNAL_FORMS:
            death_type = DeathType.MATERNAL
        else:
            # F1/F2 have an explicit death_type question
            dt_raw = (raw.get(f'{sub}_death_type') or raw.get('death_type') or '').lower()
            if dt_raw in ('stillbirth', 'neonatal', 'perinatal'):
                death_type = DeathType.PERINATAL
            else:
                death_type = DeathType.MATERNAL

        # ----- cause of death (ICD-10 select_multiple → space-separated values) -----
        cause = _first(
            raw.get('f4_probable_cause'),
            raw.get('f5_probable_cause'),
            raw.get('f6_contributing_factors'),
            raw.get('f2_cause_of_death'),
        )

        # ----- place of death -----
        place_raw = _first(
            raw.get('f1_death_place'),
            raw.get('f3_place_of_death'),
        ).lower()
        if 'home' in place_raw:
            place_of_death = PlaceOfDeath.HOME
        elif 'on_way' in place_raw or 'transit' in place_raw:
            place_of_death = PlaceOfDeath.IN_TRANSIT
        elif sub in ('f2', 'f4', 'f5', 'f6'):
            place_of_death = PlaceOfDeath.FACILITY
        elif place_raw:
            place_of_death = PlaceOfDeath.FACILITY
        else:
            place_of_death = PlaceOfDeath.FACILITY

        # ----- facility name -----
        facility_name = _first(
            raw.get('f4_facility_name'),
            raw.get('f5_facility_name'),
            raw.get('f6_facility_name'),
            raw.get('f2_facility_name'),
        )

        # ----- mother / subject age -----
        age_raw = _first(
            raw.get(f'{sub}_mother_age') if sub else None,
            raw.get('f1_mother_age'), raw.get('f2_mother_age'),
            raw.get('f3_mother_age'), raw.get('f4_mother_age'),
            raw.get('f5_mother_age'), raw.get('f6_mother_age'),
        )
        age_years = _safe_int(age_raw)

        # ----- district / upazila / union (sub-form specific) -----
        district = _first(
            raw.get(f'{sub}_district') if sub else None,
            raw.get('f1_district'), raw.get('f2_district'),
            raw.get('f3_district'), raw.get('f4_district'),
            raw.get('f5_district'), raw.get('f6_district'),
            submission.district,
        )
        upazila = _first(
            raw.get(f'{sub}_upazila') if sub else None,
            raw.get('f1_upazila'), raw.get('f3_upazila'), raw.get('f4_upazila'),
        )
        union = _first(
            raw.get(f'{sub}_union') if sub else None,
            raw.get('f1_union'), raw.get('f3_union'), raw.get('f4_union'),
        )

        # MPDSR is CIPRB-owned — default partner to CIPRB if the submission
        # didn't carry one (the webhook now sets it, this is belt-and-braces).
        partner = submission.partner or 'CIPRB'

        # submitted_at is normally a datetime; guard against a date/str.
        submitted = submission.submitted_at
        if hasattr(submitted, 'date'):
            date_of_death = submitted.date()
        else:
            date_of_death = submitted or timezone.now().date()

        # Compute logic-error flags (Animesh QA gate, deck slide 9). Advisory
        # only — flagged rows still flow through the normal review status.
        from .validators import compute_logic_flags
        logic_flags = compute_logic_flags(
            death_type=death_type,
            age_years=age_years,
            cause_of_death=cause,
            date_of_death=date_of_death,
        )

        obj, created = self.get_or_create(
            submission=submission,
            defaults={
                'partner': partner,
                'district': district,
                'region': submission.region,
                'upazila': upazila,
                'union': union,
                'latitude': submission.latitude,
                'longitude': submission.longitude,
                'date_of_death': date_of_death,
                'sub_form_type': sub,
                'death_type': death_type,
                'cause_of_death': cause,
                'place_of_death': place_of_death,
                'facility_name': facility_name,
                'age_years': age_years,
                'status': ReviewStatus.REPORTED,
                'audit_trail': [],
                'logic_flags': logic_flags,
            },
        )
        return obj, created


class MPDSRCase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_hash = models.CharField(max_length=30, unique=True, blank=True, db_index=True)

    submission = models.OneToOneField(
        'submissions.KoboSubmission',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='mpdsr_case',
    )
    partner = models.CharField(max_length=20, db_index=True)
    district = models.CharField(max_length=100, blank=True)
    upazila = models.CharField(max_length=100, blank=True)
    union = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)

    sub_form_type = models.CharField(max_length=10, blank=True, db_index=True)
    # The Social Autopsy form reviews maternal deaths, neonatal deaths AND
    # stillbirths (sa_death_type 1/2/3, verbatim from the paper tool), but
    # DeathType has only maternal and perinatal, so ingest was collapsing
    # stillbirth into perinatal and the outcome disappeared from the dashboard
    # entirely. This preserves what the reviewer actually recorded. Blank on
    # every non-Social-Autopsy row.
    sa_death_kind = models.CharField(max_length=12, blank=True, db_index=True)
    date_of_death = models.DateField()
    # Facility (Form 04) admission date — paired with date_of_death to derive
    # the admission→death interval (a care-timeliness signal). Nullable:
    # community Form 01 deaths have no facility admission.
    admission_date = models.DateField(null=True, blank=True)
    death_type = models.CharField(
        max_length=20,
        choices=DeathType.choices,
        default=DeathType.MATERNAL,
        db_index=True,
    )
    cause_of_death = models.CharField(max_length=500, blank=True)
    place_of_death = models.CharField(
        max_length=20,
        choices=PlaceOfDeath.choices,
        default=PlaceOfDeath.FACILITY,
        blank=True,
    )
    facility_name = models.CharField(max_length=200, blank=True)
    age_years = models.PositiveSmallIntegerField(null=True, blank=True)

    # ── CIPRB dashboard "major indicators" (MPDSR Form 01 community +
    #    Form 04 facility). 9 of the 11 indicators were previously lost —
    #    captured by Kobo but never persisted to a queryable column.
    #    All nullable/blank → non-destructive migration. CharFields keep
    #    the raw choice slug; histograms bucket the integers downstream.
    time_of_death = models.CharField(max_length=20, blank=True, db_index=True)         # antepartum/intrapartum/postpartum_42d/unknown
    gestational_weeks = models.PositiveSmallIntegerField(null=True, blank=True)
    anc_visits_count = models.CharField(max_length=10, blank=True)                     # none/1/2/3/4_plus/unknown
    pnc_received = models.CharField(max_length=10, blank=True)                         # yes/no/unknown (3-state — keep as char)
    mode_of_delivery = models.CharField(max_length=20, blank=True, db_index=True)      # nvd/csection/assisted_vaginal/undelivered
    delivery_outcome = models.CharField(max_length=20, blank=True)                     # livebirth/stillbirth/na
    place_of_delivery = models.CharField(max_length=20, blank=True)                    # home/gov_facility/private_facility/in_transit/na
    person_assisted_delivery = models.CharField(max_length=20, blank=True)            # doctor/nurse/midwife/tba/relatives/self/none
    time_death_after_birth_hours = models.PositiveSmallIntegerField(null=True, blank=True)

    status = models.CharField(
        max_length=30,
        choices=ReviewStatus.choices,
        default=ReviewStatus.REPORTED,
        db_index=True,
    )
    committee_date = models.DateField(null=True, blank=True)
    action_plan = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    audit_trail = models.JSONField(default=list, blank=True)

    # Logic-error flag tags raised at MPDSRCase creation by the QA validator
    # (mpdsr.validators.compute_logic_flags). Each entry is a short stable
    # string like 'AGE_LOW'. Advisory only — the manager queue renders an
    # amber badge but the approval workflow is unchanged.
    logic_flags = models.JSONField(default=list, blank=True)

    # Provenance: 'kobo' = live submission via KoboToolbox webhook.
    # 'excel_va_2026' / 'excel_va_2025' / etc. = historical baseline ingested
    # from Sayeed's verbal-autopsy Excel files. Dashboards default to combined
    # view; filterable by source for forensics.
    source = models.CharField(max_length=40, default='kobo', db_index=True)

    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='mpdsr_cases_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Manager approval (Tanjina / Setu, single-stage CIPRB). Default APPROVED
    #    so existing rows stay visible; the live webhook handler (_save_mpdsr_case)
    #    sets a NEW review submission to PENDING. NOTE: this is distinct from
    #    `status` (the committee REVIEW lifecycle) — do not conflate them.
    #    `organisation` mirrors `partner` for the shared approval queue's org
    #    filter (the queue reads obj.organisation); `center` is queue-infrastructure
    #    parity (NULL — MPDSR is district-based, has no ServiceCenter).
    APPROVAL_CHOICES = [('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')]
    approval_status = models.CharField(
        max_length=20, choices=APPROVAL_CHOICES, default='APPROVED', db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, default='')
    kobo_submission_id = models.CharField(max_length=100, blank=True, default='')
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True, default='')
    organisation = models.CharField(max_length=20, default='CIPRB', db_index=True)
    # Server-issued system reference (<FORM>-<DIST>-<NNNN>, e.g. NS1-BH-0042)
    # — allocated by programs.refs on ingestion; the hand-written paper
    # serial stays separate as the bridge to the paper register.
    system_ref = models.CharField(max_length=24, blank=True, null=True,
                                  unique=True, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')
    # Full Kobo submission, preserved verbatim. Needed for the qualitative Social
    # Autopsy (sa_md), whose meeting metadata, member counts, sex/age-detail and
    # prevention/decision structure don't all map to typed columns. Kept OUT of
    # the API by the serializer's explicit field allowlist (it can carry PII).
    raw_payload = models.JSONField(default=dict, blank=True)

    objects = MPDSRCaseManager()

    class Meta:
        ordering = ['-date_of_death', '-created_at']
        verbose_name = 'MPDSR Case'
        verbose_name_plural = 'MPDSR Cases'
        indexes = [
            models.Index(fields=['partner', 'status']),
            models.Index(fields=['death_type', 'partner']),
        ]

    # MPDSR is CIPRB-owned surveillance. The partner is normally 'CIPRB';
    # the map keeps a sensible prefix if a legacy PHD/Bandhu row ever exists.
    _PREFIX = {'PHD': 'PHD', 'Bandhu': 'BON', 'CIPRB': 'CIP'}

    def save(self, *args, **kwargs):
        if not self.case_hash:
            year = self.date_of_death.year if self.date_of_death else timezone.now().year
            prefix = self._PREFIX.get(self.partner, 'CIP')
            type_code = 'MAT' if self.death_type == DeathType.MATERNAL else 'PER'
            count = (
                MPDSRCase.objects
                .filter(partner=self.partner, date_of_death__year=year)
                .count() + 1
            )
            self.case_hash = f'MPDSR-{prefix}-{type_code}-{year}-{count:04d}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.case_hash} ({self.get_death_type_display()})'

    @property
    def sub_form_label(self) -> str:
        return SUB_FORM_LABELS.get(self.sub_form_type, self.sub_form_type.upper())

    def add_audit_entry(self, user_email: str, action: str, notes: str = '') -> None:
        entry = {
            'timestamp': timezone.now().isoformat(),
            'user': user_email,
            'action': action,
            'notes': notes,
        }
        if self.audit_trail is None:
            self.audit_trail = []
        self.audit_trail.append(entry)

    @property
    def is_overdue_committee(self) -> bool:
        if self.status == ReviewStatus.CLOSED:
            return False
        if not self.committee_date:
            return False
        return self.committee_date < datetime.date.today()


# ─── Aggregate/lookup models ingested from Sayeed's Excel files ──────────────


class MPDSRDistrictDenominator(models.Model):
    """Per-district 'Project Deaths 2026' estimate — the denominator Animesh
    needs for the reporting % rate calculation (reported / estimated).

    Source: MPDSR Report_2026.xlsx :: District Wise sheet.
    """
    district = models.CharField(max_length=100, unique=True, db_index=True)
    # Project Deaths 2026 columns (estimates / projections)
    project_deaths_md = models.FloatField(null=True, blank=True, help_text='Estimated maternal deaths 2026')
    project_deaths_nd = models.FloatField(null=True, blank=True, help_text='Estimated neonatal deaths 2026')
    project_deaths_sb = models.FloatField(null=True, blank=True, help_text='Estimated stillbirths 2026')
    source = models.CharField(max_length=40, default='excel_2026', db_index=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'MPDSR District Denominator'
        verbose_name_plural = 'MPDSR District Denominators'
        ordering = ['district']

    def __str__(self):
        return f'{self.district}: MD={self.project_deaths_md}'


class MPDSRFacilityCount(models.Model):
    """Per-facility FDN (Facility Death Notification) + FDR (Facility Death
    Review) counts. Feeds the Notification vs Review chart with real numbers
    instead of just live-Kobo submissions.

    Source: MPDSR Report_2026.xlsx :: FDN & FDR sheet.
    """
    district = models.CharField(max_length=100, db_index=True)
    facility_name = models.CharField(max_length=200, db_index=True)
    period = models.CharField(max_length=20, default='2026', db_index=True,
                              help_text='Reporting period, e.g. "2026" or "2026-Q1"')

    # CDN = Community Death Notification (per MPDSR Report 2026 columns:
    # CDN / VA / SA / FDN / FDR per death type). Animesh's spec wants
    # notifications "visibly separated by Community level and Facility level"
    # — CDN is the community level, FDN is the facility level.
    cdn_md = models.PositiveIntegerField(default=0)
    cdn_nd = models.PositiveIntegerField(default=0)
    cdn_sb = models.PositiveIntegerField(default=0)

    fdn_md = models.PositiveIntegerField(default=0)
    fdn_nd = models.PositiveIntegerField(default=0)
    fdn_sb = models.PositiveIntegerField(default=0)
    fdr_md = models.PositiveIntegerField(default=0)
    fdr_nd = models.PositiveIntegerField(default=0)
    fdr_sb = models.PositiveIntegerField(default=0)

    source = models.CharField(max_length=40, default='excel_2026', db_index=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'MPDSR Facility Count'
        verbose_name_plural = 'MPDSR Facility Counts'
        unique_together = [('district', 'facility_name', 'period')]
        ordering = ['district', 'facility_name']

    def __str__(self):
        return f'{self.district} / {self.facility_name} ({self.period})'


class MPDSRActionPlanSummary(models.Model):
    """Per-district response plan implementation tracker.

    Each row represents a planned MPDSR review/committee meeting and what
    activities were actually executed. Drives Animesh's 'MPDSR Response Plan
    Implementation Tracker' box (planned vs executed accountability).

    Source: MPDSR Action Plan_ Progress.xlsx :: per-district sheets.
    """
    REVIEW_DM = 'DM'     # District MPDSR
    REVIEW_UM = 'UM'     # Upazila MPDSR
    LEVEL_CHOICES = [(REVIEW_DM, 'District'), (REVIEW_UM, 'Upazila')]

    district = models.CharField(max_length=100, db_index=True)
    level = models.CharField(max_length=4, choices=LEVEL_CHOICES, db_index=True)
    place_of_meeting = models.CharField(max_length=200, blank=True)
    meeting_date = models.CharField(max_length=40, blank=True,
                                    help_text='Raw Excel date string — kept as text for messy formats')
    participants = models.PositiveIntegerField(null=True, blank=True)

    meetings_planned = models.PositiveIntegerField(default=0,
                                                   help_text='Number of follow-up meetings planned')
    activities_planned = models.PositiveIntegerField(default=0)
    activities_implemented = models.PositiveIntegerField(default=0)

    # Per-action detail for the full accountability matrix (Animesh's spec:
    # Date / Action / Timeline / Responsible / Indicator / Milestone /
    # Remarks / Implementation Status). List of dicts, one per action.
    # Drives the expandable matrix + deadline-based green/red colouring.
    actions = models.JSONField(default=list, blank=True)

    source = models.CharField(max_length=40, default='excel_action_plan_2026', db_index=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'MPDSR Action Plan Summary'
        verbose_name_plural = 'MPDSR Action Plan Summaries'
        ordering = ['district', 'level']

    def __str__(self):
        return f'{self.district} [{self.level}]: {self.activities_implemented}/{self.activities_planned}'

    @property
    def completion_pct(self) -> float:
        if not self.activities_planned:
            return 0.0
        return round(100.0 * self.activities_implemented / self.activities_planned, 1)


# District → Action-ID prefix. THE SINGLE SOURCE OF TRUTH for the MPDSR action
# code scheme: every code is exactly 2 letters and globally unique. The Kobo
# form (build_ciprb_forms.MPDSR_DISTRICT_CODE) derives its slug-keyed copy from
# THIS dict, so the prefix a field worker types (DH-001, RA-001) and any
# server-side allocation (next_action_id) can never diverge. These values match
# what is already stored in the live DB (Patuakhali=PA, Dhaka=DH, …); do not
# renumber them without migrating existing action_ids.
DISTRICT_ACTION_CODE = {
    'Sunamganj': 'SU', 'Sherpur': 'SH', 'Sirajganj': 'SI', 'Sylhet': 'SY',
    'Bhola': 'BH', 'Barguna': 'BG', 'Bagerhat': 'BA', 'Bandarban': 'BN',
    'Kurigram': 'KU', 'Khagrachari': 'KH', 'Gaibandha': 'GA', 'Noakhali': 'NO',
    'Patuakhali': 'PA', 'Jamalpur': 'JA', 'Habiganj': 'HA', 'Moulavibazar': 'MO',
    'Chandpur': 'CH', 'Rangpur': 'RA', 'Dhaka': 'DH',
}


class ActionSection(models.TextChoices):
    SYSTEM_STRENGTHENING = 'system_strengthening', 'MPDSR System Strengthening'
    # Display renamed per RCH review (Tanjina, 17 Aug 2026) — codes unchanged.
    COMMUNITY_VA = 'community_va', 'Common Modifiable Factor (Community)'
    FACILITY_DR = 'facility_dr', 'Common Modifiable Factor (Facility)'


class ActionStatus(models.TextChoices):
    PENDING = 'pending', 'Pending / not started'
    IN_PROGRESS = 'in_progress', 'In progress'
    IMPLEMENTED = 'implemented', 'Implemented'
    DELAYED = 'delayed', 'Delayed'
    DROPPED = 'dropped', 'Dropped'


# Marker activity for a stub row created when an `update_action` arrives for an
# action that was never registered (out-of-order delivery / stale pick). Stubs
# are parked for the real plan record to reconcile and are EXCLUDED from the
# Kobo lookup CSV, the approval queue, and dashboard rollups so they never
# masquerade as real agreed actions.
STUB_ACTIVITY_SENTINEL = '[awaiting plan record]'


class MPDSRAction(models.Model):
    """One agreed MPDSR action, tracked from plan → implementation.

    Unlike MPDSRActionPlanSummary (an Excel-sourced per-district roll-up whose
    actions live in a JSON blob), this is ONE ROW PER ACTION with a stable human
    code, `action_id` = '<district-code>-<NN>' (D-01 = Dhaka's first action). The
    code is assigned once at plan creation; later 'update' submissions reference
    it to move status / completion % forward without re-typing the action — the
    same staged auto-populate pattern the fistula register already uses.
    """
    COMPLETION_CHOICES = [(0, '0%'), (25, '25%'), (50, '50%'),
                          (75, '75%'), (100, '100%')]
    APPROVAL_CHOICES = [('PENDING', 'Pending'), ('APPROVED', 'Approved'),
                        ('REJECTED', 'Rejected')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action_id = models.CharField(max_length=12, db_index=True,
                                 help_text="'<district-code>-<NN>', e.g. D-01.")

    district = models.CharField(max_length=100, db_index=True)
    organisation = models.CharField(max_length=20, default='CIPRB', db_index=True)
    meeting_date = models.DateField(null=True, blank=True,
                                    help_text='Review meeting where the action was agreed.')

    section = models.CharField(max_length=30, choices=ActionSection.choices, db_index=True)
    sub_category = models.CharField(max_length=120, blank=True,
                                    help_text='System-Strengthening sub-category (Community Death Review, …).')

    activity = models.TextField(help_text='The action / activity to be taken.')
    responsible = models.CharField(max_length=200, blank=True)
    timeline = models.DateField(null=True, blank=True, help_text='Target date.')
    indicator = models.TextField(blank=True)
    milestone = models.TextField(blank=True)
    considerations = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=ActionStatus.choices,
                              default=ActionStatus.PENDING, db_index=True)
    completion_pct = models.PositiveSmallIntegerField(choices=COMPLETION_CHOICES, default=0)
    completion_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True, help_text='Latest progress note.')

    # Standard CIPRB approval gate + provenance (mirrors MPDSRCase). Default is
    # PENDING (fail-closed): an action must be explicitly approved by CIPRB before
    # it counts. The webhook handler sets PENDING explicitly; this default protects
    # every OTHER creation path (admin, import, migration) from silently bypassing
    # the gate (audit FIX 2026-06: was 'APPROVED', a fail-open default).
    approval_status = models.CharField(
        max_length=20, choices=APPROVAL_CHOICES, default='PENDING', db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, default='')
    kobo_submission_id = models.CharField(max_length=100, blank=True, default='')
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True, default='')
    # Typed enumerator ("YOUR NAME") — the per-creator identity for the approval
    # gate. creator_name is set ONCE at registration (immutable ownership);
    # last_edited_by_name is the latest update submitter, so the CIPRB approver
    # can see "created by X / edited by Y" and reject a non-creator's edit.
    creator_name = models.CharField(max_length=200, blank=True, default='')
    last_edited_by_name = models.CharField(max_length=200, blank=True, default='')
    source = models.CharField(max_length=40, default='kobo', db_index=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    audit_trail = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = 'MPDSR Action'
        verbose_name_plural = 'MPDSR Actions'
        ordering = ['district', 'action_id']
        unique_together = [('district', 'action_id')]
        indexes = [
            models.Index(fields=['district', 'status']),
            models.Index(fields=['section', 'status']),
            models.Index(fields=['timeline', 'status']),
        ]

    # sub_category codes -> display label. Two vocabularies share the column,
    # kept apart by `section`: the System-Strengthening sub-category (master
    # Table 1's first column) and the common modifiable factor (Table 2's first
    # column, added 2026-08). Anything not listed is a district's own 'other'
    # wording and is shown as typed.
    SUBCATEGORY_LABELS = {
        'community_death_review': 'Community Death Review',
        'facility_death_review': 'Facility Death Review',
        'assignment_causes': 'Assignment causes of deaths',
        'response_plan_dev': 'Response plan development',
        'implementation_response': 'Implementation of response',
        'monitoring_evaluation': 'Monitoring and evaluation',
        'quality_of_care': 'Lack of quality maternal and newborn care service at facilities',
        'pph_management': 'Management of Postpartum Haemorrhage (PPH)',
        'multiparity_htn_preeclampsia': 'Multiparity, prolonged labour, HTN and pre-eclampsia',
        'referral_linkages': 'Inadequate referral linkages',
        'delayed_anc': 'Delayed ANC initiation',
        'home_delivery_tba': 'Home delivery by TBA',
        'death_reporting': 'Increase proper death reporting',
    }

    @property
    def sub_category_label(self):
        """Readable first-column value, whichever master table this came from."""
        return self.SUBCATEGORY_LABELS.get(self.sub_category, self.sub_category)

    def __str__(self):
        return f'{self.action_id} — {self.activity[:50]}'

    @property
    def is_overdue(self) -> bool:
        """Past its timeline and not yet implemented/dropped."""
        if (not self.timeline or self.completion_pct >= 100
                or self.status in (ActionStatus.IMPLEMENTED, ActionStatus.DROPPED)):
            return False
        return self.timeline < timezone.now().date()

    @classmethod
    def next_action_id(cls, district: str) -> str:
        """Next '<code>-<NN>' for a district. Call inside a transaction AND a
        retry-on-IntegrityError loop (see handle_ciprb_mpdsr_action_plan):
        select_for_update() locks only rows that already exist, so two concurrent
        plans for the same (especially empty) district can still both compute the
        same number — the unique_together('district','action_id') then rejects the
        loser, whose caller retries against the now-committed sibling."""
        code = DISTRICT_ACTION_CODE.get(district)
        if code is None:
            import logging
            logging.getLogger(__name__).warning(
                'MPDSRAction.next_action_id: district %r not in DISTRICT_ACTION_CODE '
                '— using a fallback code; ids may not be globally unique', district)
            code = (district[:2] or 'XX').upper()
        rows = (cls.objects.select_for_update()
                .filter(district=district, action_id__startswith=code + '-'))
        max_n = 0
        for a in rows:
            try:
                max_n = max(max_n, int(a.action_id.rsplit('-', 1)[-1]))
            except (ValueError, IndexError):
                pass
        # 3-digit serial to match the Kobo form's regex (^<code>-[0-9]{3}$), so a
        # server-allocated id is shaped identically to a worker-typed one.
        return f'{code}-{max_n + 1:03d}'

    def add_audit_entry(self, user_email: str, action: str, notes: str = '') -> None:
        if self.audit_trail is None:
            self.audit_trail = []
        self.audit_trail.append({
            'timestamp': timezone.now().isoformat(),
            'user': user_email, 'action': action, 'notes': notes,
        })


class CIPRBReconSnapshot(models.Model):
    """The latest CIPRB Kobo-vs-app reconciliation result (mpdsr.reconcile).

    Written by `manage.py reconcile_ciprb`, read by /api/mpdsr/reconciliation/ so
    the dashboard health strip is a cheap read, not a live Kobo pull per request.
    Only the newest row matters; older rows are history.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run_at = models.DateTimeField(db_index=True)
    data = models.JSONField(default=dict)

    class Meta:
        ordering = ['-run_at']
        verbose_name = 'CIPRB reconciliation snapshot'

    def __str__(self):
        return 'recon @ %s (%s)' % (
            self.run_at.isoformat(),
            'ok' if self.data.get('all_ok') else 'DRIFT')


# ── CIPRB Phase 2 models (notification slips + Maternal Near Miss).
from .ciprb_models import (  # noqa: F401,E402
    MPDSRDeathNotification,
    MaternalNearMissCase,
)
