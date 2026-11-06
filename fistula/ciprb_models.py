"""
CIPRBFistulaCase — the new CIPRB Fistula Question Bank model.

Separate from the existing FistulaCornerCase (which stays unchanged for
the historical KF-Fistula data). One CIPRBFistulaCase row per woman;
fields cluster by the five clinical stages so the dashboard's pipeline
can count progressions directly.

A given submission may carry only the fields for ONE stage (the form's
`stage` selector). The handler upserts on (district + case_serial +
deceased_name) and writes only the fields under that stage — so the
same case row accumulates data as it moves through Suspected →
Diagnosed → Referred → Repaired → Rehabilitated.
"""
import uuid
from django.db import models
from django.conf import settings

from .encryption import EncryptedCharField  # Fernet at rest for patient PII


# District slug → numeric code for the fistula patient-ID prefix
# (<code>-NNNN, e.g. bhola → 2-0001). Canonical home is HERE, not the
# XLSForm build command: the webhook allocates IDs from this map in
# production, where the build command cannot be imported (its module-level
# openpyxl import is a local-only build dependency — 2026-08-10 500).
# The spec names 10 base districts (codes 1-10); the remaining CIPRB
# districts get 11-19 in slug order so every option yields a deterministic
# prefix. Slug keys MUST match the form's `district` choice values
# (lower-cased, spaces→'_').
FISTULA_DISTRICT_CODE = {
    'sunamganj': 1, 'bhola': 2, 'noakhali': 3, 'gaibandha': 4,
    'kurigram': 5, 'sirajganj': 6, 'sherpur': 7, 'patuakhali': 8,
    'khagrachari': 9, 'dhaka': 10,
    'barguna': 11, 'jamalpur': 12, 'bagerhat': 13, 'habiganj': 14,
    'moulavibazar': 15, 'sylhet': 16, 'bandarban': 17, 'rangpur': 18,
    'chandpur': 19,
}


class CIPRBFistulaCase(models.Model):
    # ── Stage choices (drive the dashboard pipeline counts).
    STAGE_SUSPECTED     = 'suspected'
    STAGE_DIAGNOSED     = 'diagnosed'
    STAGE_REFERRED      = 'referred'
    STAGE_REPAIRED      = 'repaired'
    STAGE_REHABILITATED = 'rehabilitated'
    STAGE_CHOICES = [
        (STAGE_SUSPECTED,     'Suspected'),
        (STAGE_DIAGNOSED,     'Diagnosed'),
        (STAGE_REFERRED,      'Referred for Surgical Management'),
        (STAGE_REPAIRED,      'Surgically Repaired'),
        (STAGE_REHABILITATED, 'Rehabilitated & Reintegrated'),
    ]

    # ── 4 fistula types per CIPRB Question Bank (the dashboard donut).
    TYPE_OBSTETRIC  = 'obstetric'
    TYPE_IATROGENIC = 'iatrogenic'
    TYPE_CONGENITAL = 'congenital'
    TYPE_TRAUMATIC  = 'traumatic'
    TYPE_CHOICES = [
        (TYPE_OBSTETRIC,  'Obstetric'),
        (TYPE_IATROGENIC, 'Iatrogenic'),
        (TYPE_CONGENITAL, 'Congenital'),
        (TYPE_TRAUMATIC,  'Traumatic'),
    ]

    # ── Surgery outcome.
    SURG_DRY      = 'success_dry'
    SURG_NOT_DRY  = 'success_not_dry'
    SURG_FAILED   = 'failed'
    SURGERY_OUTCOME_CHOICES = [
        (SURG_DRY,     'Successfully repaired with a dry vagina'),
        (SURG_NOT_DRY, 'Successfully repaired but not dry'),
        (SURG_FAILED,  'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_serial = models.CharField(
        max_length=50, blank=True, db_index=True,
        help_text='CIPRB annual fistula serial (from the paper form).',
    )
    # ── Stable, unique patient key — the registry ID typed at the Suspected
    #    stage (<district-code>-<4-digit serial>, e.g. 1-0001, 10-0001). Every
    #    later stage references this exact ID via the form's dropdown, so the
    #    case row accumulates against one key. null=True (not '') so legacy
    #    rows without a code don't collide on the unique constraint.
    patient_code = models.CharField(
        max_length=20, blank=True, null=True, unique=True, db_index=True,
        help_text='Unique fistula patient ID: <district-code>-<4-digit serial>.',
    )

    # ── Provenance.
    submission = models.OneToOneField(
        'submissions.KoboSubmission',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='ciprb_fistula_case',
    )
    organisation = models.CharField(max_length=20, default='CIPRB',
                                    db_index=True)
    district = models.CharField(max_length=100, db_index=True)
    upazila  = models.CharField(max_length=100, blank=True)
    union    = models.CharField(max_length=100, blank=True)
    village  = models.CharField(max_length=100, blank=True)

    # ── Patient identity. Direct identifiers are Fernet-encrypted at rest
    #    (EncryptedCharField), matching GBV; demographics/occupation stay plain.
    name                = EncryptedCharField()
    age                 = models.PositiveSmallIntegerField(null=True, blank=True)
    education           = models.CharField(max_length=30, blank=True)
    husband             = EncryptedCharField(blank=True)
    husband_profession  = models.CharField(max_length=200, blank=True)
    profession_patient  = models.CharField(max_length=200, blank=True)
    current_condition   = models.CharField(max_length=200, blank=True)
    contact_number      = EncryptedCharField(blank=True)
    marital_status      = models.CharField(max_length=20, blank=True)
    age_at_marriage     = models.PositiveSmallIntegerField(null=True, blank=True)
    age_at_first_delivery = models.PositiveSmallIntegerField(null=True, blank=True)
    number_of_children  = models.PositiveSmallIntegerField(null=True, blank=True)

    # ── Obstetric history.
    delivery_complication       = models.CharField(max_length=200, blank=True)
    last_delivery_labour_duration = models.CharField(max_length=100, blank=True)
    mode_of_last_delivery       = models.CharField(max_length=30, blank=True)
    place_of_last_delivery      = models.CharField(max_length=30, blank=True)
    conducted_last_delivery     = models.CharField(max_length=30, blank=True)
    delivery_outcome            = models.CharField(max_length=20, blank=True)
    reasons_no_institutional_delivery = models.CharField(max_length=200, blank=True)
    time_duration_fistula_occurrence  = models.CharField(max_length=100, blank=True)
    duration_suffering          = models.CharField(max_length=100, blank=True)

    # ── Stage 1: Suspected.
    suspected_date     = models.DateField(null=True, blank=True)
    source_information = models.CharField(max_length=200, blank=True)
    # ── Stage 2: Diagnosed.
    diagnosed_date     = models.DateField(null=True, blank=True)
    diagnosed_place    = models.CharField(max_length=200, blank=True)
    diagnosed_by       = models.CharField(max_length=200, blank=True)
    # ── Stage 3: Referred for Surgical Management.
    refer_date          = models.DateField(null=True, blank=True)
    refer_place         = models.CharField(max_length=200, blank=True)
    referred_by_person  = models.CharField(max_length=200, blank=True)
    refer_outcome       = models.CharField(max_length=30, blank=True)
    # ── Stage 4: Surgically Repaired.
    operation_date       = models.DateField(null=True, blank=True)
    operation_place      = models.CharField(max_length=200, blank=True)
    hospital_stay_days   = models.PositiveSmallIntegerField(null=True, blank=True)
    times_of_operations  = models.PositiveSmallIntegerField(null=True, blank=True)
    fistula_type_v2      = models.CharField(
        max_length=20, choices=TYPE_CHOICES, blank=True, db_index=True,
        help_text='4-category fistula type per CIPRB Question Bank.',
    )
    iatrogenic_cause     = models.CharField(max_length=30, blank=True)
    genital_fistula_type = models.CharField(max_length=120, blank=True)
    operation_route      = models.CharField(max_length=30, blank=True)
    surgery_outcome_v2   = models.CharField(
        max_length=30, choices=SURGERY_OUTCOME_CHOICES, blank=True,
    )
    # ── Stage 5: Rehabilitated & Reintegrated.
    rehabilitation_received = models.BooleanField(null=True)
    rehabilitation_date     = models.DateField(null=True, blank=True)
    rehab_place             = models.CharField(max_length=50, blank=True)
    rehab_support_types     = models.CharField(max_length=500, blank=True)
    rehab_notes             = models.TextField(blank=True)

    # ── Current stage (latest stage the form has advanced this case to).
    current_stage = models.CharField(
        max_length=20, choices=STAGE_CHOICES, default=STAGE_SUSPECTED,
        db_index=True,
    )

    # ── Provenance / audit.
    latitude  = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    enumerator_name = models.CharField(max_length=200, blank=True)
    enumerator_mobile = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Manager approval (Tanjina / Setu, single-stage). Default APPROVED so
    #    existing/historical cases stay visible the moment the column lands; the
    #    webhook handler sets a NEW registration to PENDING. Once approved, later-
    #    stage updates keep the status (a case is not re-pended as it progresses).
    APPROVAL_CHOICES = [('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')]
    approval_status = models.CharField(
        max_length=20, choices=APPROVAL_CHOICES, default='APPROVED', db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    kobo_submission_id = models.CharField(max_length=100, blank=True, default='')
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True, default='')
    rejected_reason = models.TextField(blank=True, default='')
    # Queue-infrastructure parity only: the shared approval queue unconditionally
    # select_related's 'center'. Fistula is district-based (no ServiceCenter), so
    # this stays NULL and the queue renders '–' — but the column must EXIST or the
    # join raises FieldError and 500s the whole queue.
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'CIPRB Fistula Case'
        verbose_name_plural = 'CIPRB Fistula Cases'
        indexes = [
            models.Index(fields=['organisation', 'current_stage']),
            models.Index(fields=['district', 'current_stage']),
            models.Index(fields=['district', 'case_serial']),
        ]

    def __str__(self):
        s = self.case_serial or str(self.id)[:8]
        return f'CIPRB Fistula {s} — {self.name} ({self.current_stage})'


# The Question Bank form's `stage` selector carries one extra value that is
# NOT a clinical stage: a cost entry. It is deliberately kept out of
# CIPRBFistulaCase.STAGE_CHOICES so that recording what a woman's treatment
# cost can never advance (or appear to advance) her position in the clinical
# pipeline. The handler branches on it before the stage machinery runs.
FISTULA_COST_STAGE = 'cost'


class CIPRBFistulaCaseCost(models.Model):
    """What one fistula patient's treatment actually cost, per episode.

    A child of CIPRBFistulaCase rather than six more columns on the case row,
    because a woman can be operated more than once (the case row already
    carries `times_of_operations`). Flat columns would let the second
    operation's costs overwrite the first and silently understate the total.
    One row per (patient, point in the pathway, occurrence) keeps every
    episode and lets the dashboard report both a per-woman total and an
    average cost per repair.

    Costs attach from the REFERRAL stage onward, not only to surgery: a woman
    who was referred and travelled but was never operated (a comorbidity ruled
    out theatre) still incurred travel and investigation cost, and that money
    is spent whether or not an operation follows.
    (Dr Tanjina Pervin, RCH CIPRB, 9 September 2026.)

    There is deliberately NO "who paid" field. CIPRB pays the whole cost of a
    fistula patient's treatment and nothing is paid by the woman or her family,
    so a payer question would be a constant answer on every line and seven
    extra taps per patient. The purpose of the figures is to compare what a
    patient ACTUALLY costs against the BDT 10,000-12,000 per patient the
    project budgets. If the programme ever starts sharing cost with families,
    this is the assumption to revisit first. (Same source, same date.)

    Note on the accounting term: these figures are NOT out-of-pocket
    expenditure. Out-of-pocket means a household spending its OWN resources on
    health. Here the money is the project's throughout: a District Coordinator
    releases it to the woman and she settles the hospital bill with it, so
    although the cash passes through her hands she is disbursing project funds,
    not her own. The household's out-of-pocket expenditure is zero. These are
    the actual cost per patient, borne by the project and paid through her.
    """

    POINT_REFERRED = 'referred'
    POINT_REPAIRED = 'repaired'
    POINT_CHOICES = [
        (POINT_REFERRED, 'Referral (travel, investigation, no surgery yet)'),
        (POINT_REPAIRED, 'Surgical repair'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(
        CIPRBFistulaCase, on_delete=models.CASCADE, related_name='costs')

    cost_point = models.CharField(
        max_length=20, choices=POINT_CHOICES, default=POINT_REPAIRED,
        db_index=True,
        help_text='Which point in the pathway this money was spent at.')
    # 1st operation, 2nd operation, and so on. Tanjina: "একই আইডি ২নং ওটি" —
    # the same patient ID carries a second operation, and its own costs.
    episode_no = models.PositiveSmallIntegerField(
        default=1, help_text='Which occurrence (1st operation, 2nd operation…).')
    cost_date = models.DateField(null=True, blank=True)

    # ── The six cost heads, verbatim from the Question Bank (rows 96-102).
    #    All are NULLABLE on purpose: NULL means "not recorded", 0 means
    #    "recorded, and it genuinely cost nothing". Making them required would
    #    collapse the two and fill the data with meaningless zeroes. Whole taka
    #    only — no one itemises a fistula repair to the poisha.
    # ── What the project handed over, as distinct from what was spent.
    #    CIPRB does not pay the facility. A District Coordinator draws the money
    #    and gives it to the woman, who pays the hospital herself (at Dhaka
    #    Medical the Coordinator posted there receives it), and CIPRB transacts
    #    the total. So cash passes through hands, and the amount released and
    #    the amount actually spent are two different figures that can diverge.
    #    Recording only the spend would leave the difference invisible and
    #    nothing to reconcile CIPRB's ledger against.
    #    (Dr Tanjina Pervin, RCH CIPRB, 9 September 2026.)
    amount_disbursed = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Amount released to the patient for this episode.')
    disbursed_by = models.CharField(
        max_length=200, blank=True, default='',
        help_text='District Coordinator who handed the money over.')

    medical_cost       = models.PositiveIntegerField(null=True, blank=True)
    investigation_cost = models.PositiveIntegerField(null=True, blank=True)
    ot_cost            = models.PositiveIntegerField(null=True, blank=True)
    travel_cost        = models.PositiveIntegerField(null=True, blank=True)
    food_cost          = models.PositiveIntegerField(null=True, blank=True)
    other_cost         = models.PositiveIntegerField(null=True, blank=True)
    remarks            = models.TextField(blank=True, default='')

    # ── Provenance. Mirrors the case row so the approval queue and the audit
    #    trail can attribute a cost entry the same way they attribute a stage.
    kobo_submission_id     = models.CharField(max_length=100, blank=True, default='')
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    COST_FIELDS = ('medical_cost', 'investigation_cost', 'ot_cost',
                   'travel_cost', 'food_cost', 'other_cost')

    @property
    def total(self) -> int:
        """Sum of the recorded heads. Unrecorded heads count as nothing rather
        than breaking the sum, so a partially-filled entry still totals."""
        return sum(getattr(self, f) or 0 for f in self.COST_FIELDS)

    @property
    def balance(self):
        """Released minus spent. None when nothing was recorded as released,
        because 0 - spent would read as an overspend that never happened."""
        if self.amount_disbursed is None:
            return None
        return self.amount_disbursed - self.total

    @property
    def is_empty(self) -> bool:
        """True when no head carries a figure. Such a row is a remark only."""
        return all(getattr(self, f) is None for f in self.COST_FIELDS)

    class Meta:
        ordering = ['case', 'cost_point', 'episode_no']
        verbose_name = 'CIPRB Fistula Case Cost'
        verbose_name_plural = 'CIPRB Fistula Case Costs'
        constraints = [
            # Re-entering the same episode CORRECTS it instead of duplicating.
            # Without this a webhook redelivery, or a worker fixing a typo,
            # would double the programme's reported spend.
            models.UniqueConstraint(
                fields=['case', 'cost_point', 'episode_no'],
                name='uniq_fistula_cost_per_episode'),
        ]
        indexes = [models.Index(fields=['cost_point', 'cost_date'])]

    def __str__(self):
        return (f'{self.case.patient_code} · {self.cost_point} '
                f'#{self.episode_no} · BDT {self.total}')
