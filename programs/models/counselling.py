"""
Counselling and mental health models:
  - HTCCounselling         (HIV Testing & Counselling — KF-04)
  - IndividualCounselling  (Daily Counselling Session — KF-09)
  - MHScreening            (Depression / PTSD screening — KF-05/06)
"""
from django.core.exceptions import ValidationError
from django.db import models
from .._base_choices import ORG_CHOICES
from ._base import SubmissionBase


class HTCCounselling(SubmissionBase):
    """Audit FIX 7.1 — full HTC field set per the validation workshop spec.

    The pre-existing 15-field shape was retained and extended with the
    missing demographic, risk-history, and counsellor-checklist fields.
    All new fields default to null / False / empty so existing rows
    survive the migration unchanged. `consent` (client_consented) now
    blocks save when False — see clean()."""

    PRE = 'pre'
    POST = 'post'
    ONGOING = 'ongoing'
    SESSION_TYPE_CHOICES = [
        (PRE, 'Pre-Test'),
        (POST, 'Post-Test'),
        (ONGOING, 'Ongoing'),
    ]

    # Marital status
    UNMARRIED   = 'unmarried'
    MARRIED     = 'married'
    WIDOWED     = 'widowed'
    DIVORCED    = 'divorced'
    SEPARATED   = 'separated'
    COHABITING  = 'cohabiting'
    MARITAL_STATUS_CHOICES = [
        (UNMARRIED,  'Unmarried'),
        (MARRIED,    'Married'),
        (WIDOWED,    'Widowed'),
        (DIVORCED,   'Divorced'),
        (SEPARATED,  'Separated'),
        (COHABITING, 'Cohabiting'),
    ]

    # Last test result
    LTR_POS     = 'positive'
    LTR_NEG     = 'negative'
    LTR_UNKNOWN = 'unknown'
    LAST_TEST_RESULT_CHOICES = [
        (LTR_POS,     'Positive'),
        (LTR_NEG,     'Negative'),
        (LTR_UNKNOWN, 'Unknown'),
    ]

    # Partner type
    PT_REGULAR   = 'regular'
    PT_IRREGULAR = 'irregular'
    PARTNER_TYPE_CHOICES = [
        (PT_REGULAR,   'Regular'),
        (PT_IRREGULAR, 'Irregular'),
    ]

    # Tattoo history tri-state
    TATTOO_YES     = 'yes'
    TATTOO_NO      = 'no'
    TATTOO_UNKNOWN = 'unknown'
    TATTOO_CHOICES = [
        (TATTOO_YES,     'Yes'),
        (TATTOO_NO,      'No'),
        (TATTOO_UNKNOWN, 'Unknown'),
    ]

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='htc_sessions'
    )
    client = models.ForeignKey(
        'programs.Client', on_delete=models.PROTECT, related_name='htc_sessions'
    )

    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES)
    session_date = models.DateField(db_index=True)
    age_at_session = models.PositiveSmallIntegerField(null=True, blank=True)

    # ─── New demographic fields (audit FIX 7.1) ────────────────────────────
    visit_number = models.PositiveSmallIntegerField(default=1)
    monthly_income = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    marital_status = models.CharField(
        max_length=20, choices=MARITAL_STATUS_CHOICES, blank=True,
    )
    occupation = models.CharField(max_length=200, blank=True)

    # ─── Previous testing history ──────────────────────────────────────────
    previous_test_count = models.PositiveSmallIntegerField(default=0)
    last_test_date = models.DateField(null=True, blank=True)
    last_test_result = models.CharField(
        max_length=20, choices=LAST_TEST_RESULT_CHOICES, blank=True,
    )

    # Risk assessment (existing)
    partner_count = models.CharField(max_length=20, blank=True)
    partner_type = models.CharField(
        max_length=20, choices=PARTNER_TYPE_CHOICES, blank=True,
    )
    condom_use = models.CharField(max_length=20, blank=True)
    # Sex types — multi-select stored as JSON list of choice codes
    # (anal_insertive / anal_receptive / oral / vaginal / other …).
    # Schema kept loose so the Kobo form can extend without a migration.
    sex_types = models.JSONField(default=list, blank=True)
    needle_sharing = models.BooleanField(null=True)
    blood_transfusion = models.BooleanField(null=True)
    blood_transplant_history = models.BooleanField(default=False)
    tattoo_history = models.CharField(
        max_length=10, choices=TATTOO_CHOICES, blank=True,
    )
    sti_history_self = models.BooleanField(default=False)
    sti_history_partner = models.BooleanField(default=False)
    tb_history = models.BooleanField(default=False)
    last_risky_behaviour_date = models.DateField(null=True, blank=True)
    window_period_retest_date = models.DateField(null=True, blank=True)

    partner_hiv_positive = models.CharField(max_length=20, blank=True)
    client_pregnant = models.BooleanField(null=True)
    pregnancy_trimester = models.CharField(max_length=20, blank=True)

    # Counsellor checklist (existing 4 + spec adds 3 explicit ones)
    covered_hiv_sti_prevention = models.BooleanField(default=False)
    covered_risk_assessment = models.BooleanField(default=False)
    covered_behavior_change = models.BooleanField(default=False)
    covered_support_systems = models.BooleanField(default=False)
    checklist_confidentiality = models.BooleanField(default=False)
    checklist_condom_demo = models.BooleanField(default=False)
    # Tri-state — null = not assessed, true = at-risk, false = no risk.
    checklist_suicide_risk = models.BooleanField(null=True, blank=True)

    # Consent — blocks save when False (FIX 7.1 hard gate).
    client_consented = models.BooleanField(default=False)

    # Counseling types — multi-select (pre-test / post-test / family /
    # partner / risk-reduction / disclosure / adherence …).
    counseling_types = models.JSONField(default=list, blank=True)

    next_revisit_date = models.DateField(null=True, blank=True)

    counsellor_name = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-session_date']

    def clean(self):
        super().clean()
        # Audit FIX 7.1 — consent must be present to record the session.
        if not self.client_consented:
            raise ValidationError(
                {'client_consented':
                    'Client consent is mandatory before recording an HTC '
                    'session. Submission rejected.'},
                code='consent_required',
            )

    def __str__(self):
        return f'HTC {self.session_type} — {self.session_date}'


class IndividualCounselling(SubmissionBase):
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='counselling_sessions'
    )
    client = models.ForeignKey(
        'programs.Client', on_delete=models.PROTECT, related_name='counselling_sessions'
    )

    session_date = models.DateField(db_index=True)
    counsellor_name = models.CharField(max_length=200, blank=True)

    # Issues (multi-select mapped to booleans)
    issue_sti = models.BooleanField(default=False)
    issue_general_health = models.BooleanField(default=False)
    issue_fp = models.BooleanField(default=False)
    issue_drug_use = models.BooleanField(default=False)
    issue_psychosocial = models.BooleanField(default=False)  # counts for MHPSS indicator
    issue_gbv = models.BooleanField(default=False)
    issue_other = models.BooleanField(default=False)

    condom_distributed = models.PositiveSmallIntegerField(default=0)
    iec_materials = models.PositiveSmallIntegerField(default=0)

    # Referrals from this session
    referral_mental_health = models.BooleanField(default=False)
    referral_legal = models.BooleanField(default=False)
    referral_htc = models.BooleanField(default=False)
    referral_gbv = models.BooleanField(default=False)

    drug_habit_noted = models.BooleanField(default=False)
    drug_names = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-session_date']

    def __str__(self):
        return f'Counselling {self.session_date}'


class MHScreening(SubmissionBase):
    """Mental health screening — Zahiruddin depression scale or PTSD scale.

    Audit FIX 7.4 + 7.5: total_score is auto-calculated from item_responses
    on every save and re-validated in clean() — no manual override of the
    total is allowed. Bands and cutoffs match the validation workshop spec:

      Depression (30 items × 1-5, max 150):
        cutoff 93.5  | 30-100 Minimal · 101-114 Mild ·
                     | 115-123 Moderate · 124-150 Severe

      PTSD (auto-calc):
        cutoff 47.5  | ≤54 Mild · 55-66 Moderate ·
                     | 67-77 Severe · ≥78 Profound (Anxiety)
    """

    DEPRESSION = 'depression'
    PTSD = 'ptsd'
    SCREENING_TYPE_CHOICES = [
        (DEPRESSION, 'Depression (Zahiruddin Scale)'),
        (PTSD, 'PTSD'),
    ]

    # Severity bands — used for dashboard charts. Kept for backward
    # compatibility; the spec-mandated bands are surfaced via the
    # `depression_band` / `ptsd_band` derived properties.
    NONE = 'none'
    MINIMAL = 'minimal'
    MILD = 'mild'
    MODERATE = 'moderate'
    SEVERE = 'severe'
    EXTREME = 'extreme'
    PROFOUND = 'profound'
    SEVERITY_CHOICES = [
        (NONE,     'No / Minimal'),
        (MINIMAL,  'Minimal'),
        (MILD,     'Mild'),
        (MODERATE, 'Moderate'),
        (SEVERE,   'Severe'),
        (EXTREME,  'Extreme'),
        (PROFOUND, 'Profound'),
    ]

    # Audit FIX 7.4 + 7.5 — cutoff constants per validation spec.
    DEPRESSION_CUTOFF = 93.5
    PTSD_CUTOFF = 47.5

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='mh_screenings'
    )
    client = models.ForeignKey(
        'programs.Client', on_delete=models.PROTECT, related_name='mh_screenings'
    )

    screening_type = models.CharField(max_length=20, choices=SCREENING_TYPE_CHOICES)
    screening_date = models.DateField(db_index=True)
    psycho_number = models.CharField(max_length=50, blank=True)
    counsellor_name = models.CharField(max_length=200, blank=True)

    total_score = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    severity_category = models.CharField(
        max_length=20, choices=SEVERITY_CHOICES, blank=True
    )

    # Depression: 30 items (1-5 scale) stored as JSON for flexibility.
    # PTSD: same shape. Keys are item ids (e.g. 'q1', 'q2', ...);
    # values are integers 1-5.
    item_responses = models.JSONField(default=dict, blank=True)

    referred_for_counselling = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-screening_date']

    # ─── Audit FIX 7.4 + 7.5 — auto-scoring + bands ────────────────────────
    @staticmethod
    def _sum_responses(item_responses) -> int:
        """Defensive sum: skips non-numeric values to keep a partial response
        from crashing the save path. Returns 0 when the dict is empty."""
        total = 0
        if isinstance(item_responses, dict):
            for v in item_responses.values():
                try:
                    total += int(v)
                except (TypeError, ValueError):
                    continue
        return total

    @property
    def auto_calculated_total(self) -> int:
        """Sum of item_responses values."""
        return self._sum_responses(self.item_responses)

    @property
    def depression_band(self) -> str:
        """Spec bands for the Zahiruddin depression scale."""
        if self.screening_type != self.DEPRESSION or self.total_score is None:
            return ''
        s = float(self.total_score)
        if s <= 100:
            return 'Minimal'
        if s <= 114:
            return 'Mild'
        if s <= 123:
            return 'Moderate'
        return 'Severe'

    @property
    def depression_cutoff_exceeded(self) -> bool:
        if self.screening_type != self.DEPRESSION or self.total_score is None:
            return False
        return float(self.total_score) > self.DEPRESSION_CUTOFF

    @property
    def ptsd_band(self) -> str:
        """Spec bands for the PTSD anxiety scale."""
        if self.screening_type != self.PTSD or self.total_score is None:
            return ''
        s = float(self.total_score)
        if s <= 54:
            return 'Mild Anxiety'
        if s <= 66:
            return 'Moderate Anxiety'
        if s <= 77:
            return 'Severe Anxiety'
        return 'Profound Anxiety'

    @property
    def ptsd_cutoff_exceeded(self) -> bool:
        if self.screening_type != self.PTSD or self.total_score is None:
            return False
        return float(self.total_score) > self.PTSD_CUTOFF

    def clean(self):
        super().clean()
        # If item_responses is provided, total_score must equal the
        # computed sum — no override permitted (audit FIX 7.4 + 7.5).
        if self.item_responses:
            computed = self._sum_responses(self.item_responses)
            if self.total_score is None:
                # Auto-fill on first save.
                self.total_score = computed
            elif float(self.total_score) != float(computed):
                raise ValidationError(
                    {'total_score':
                        f'total_score is auto-calculated from item_responses '
                        f'(computed = {computed}). Manual override is not '
                        f'permitted. Either clear total_score or correct the '
                        f'item responses.'},
                    code='total_score_override_blocked',
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_screening_type_display()} screening {self.screening_date}'
