"""
CIPRB-specific MPDSR-side models that complement the existing MPDSRCase:

  - MPDSRDeathNotification    — death-notification slips 01 + 02
  - MaternalNearMissCase      — WHO MNM audit submissions

The existing MPDSRCase is reused for the 4 review forms (Form 1, 2, 4, 5)
+ Social Autopsy, distinguished by `sub_form_type`. No schema change
needed there. These two new models cover the workflows MPDSRCase doesn't.
"""
import uuid
from django.db import models
from django.conf import settings

from fistula.encryption import EncryptedCharField  # Fernet at rest for PII


# Shared note: both models below gain a single-stage CIPRB approval gate
# (Tanjina / Setu). approval_status defaults to APPROVED so existing rows stay
# visible; the webhook handlers set a NEW submission to PENDING. `center` exists
# only for shared-queue parity (the queue unconditionally select_related's it).
_APPROVAL_CHOICES = [('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')]


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║   MPDSRDeathNotification — Slip 01 and Slip 02                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class MPDSRDeathNotification(models.Model):
    """Two slips notify the same kind of event (a death) from the field,
    and trigger review committee work downstream.  They share schema."""

    KIND_MATERNAL   = 'maternal'
    KIND_NEONATAL   = 'neonatal'
    KIND_STILLBIRTH = 'stillbirth'
    KIND_CHOICES = [
        (KIND_MATERNAL,   'Maternal death'),
        (KIND_NEONATAL,   'Neonatal death'),
        (KIND_STILLBIRTH, 'Stillbirth'),
    ]

    SLIP_01 = '01'
    SLIP_02 = '02'
    SLIP_CHOICES = [(SLIP_01, 'Slip 01'), (SLIP_02, 'Slip 02')]

    PLACE_HOME       = 'home'
    PLACE_FACILITY   = 'facility'
    PLACE_TRANSIT    = 'in_transit'
    PLACE_CHOICES = [
        (PLACE_HOME,     'Home'),
        (PLACE_FACILITY, 'Health facility'),
        (PLACE_TRANSIT,  'In transit'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_serial = models.CharField(max_length=50, blank=True, db_index=True)

    submission = models.OneToOneField(
        'submissions.KoboSubmission',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='mpdsr_notification',
    )
    organisation = models.CharField(max_length=20, default='CIPRB',
                                    db_index=True)
    slip_variant = models.CharField(max_length=2, choices=SLIP_CHOICES,
                                    default=SLIP_01, db_index=True)

    # Location.
    district = models.CharField(max_length=100, db_index=True)
    upazila  = models.CharField(max_length=100, blank=True)
    union    = models.CharField(max_length=100, blank=True)
    village  = models.CharField(max_length=100, blank=True)

    # Event.
    death_kind = models.CharField(max_length=20, choices=KIND_CHOICES,
                                  db_index=True)
    # deceased_name is a dedup lookup key (update_or_create in _save_notification)
    # — Fernet ciphertext is non-deterministic, so encrypting it would defeat
    # dedup and duplicate every re-delivered notification. Kept plaintext; the
    # address (not a key) IS encrypted. A deterministic name-hash dedup key would
    # let this be encrypted too — see should-fix.
    deceased_name = models.CharField(max_length=200)
    deceased_age  = models.PositiveSmallIntegerField(null=True, blank=True)
    deceased_address = EncryptedCharField(blank=True)    # Fernet at rest
    date_of_death = models.DateField(db_index=True)
    place_of_death = models.CharField(max_length=20, choices=PLACE_CHOICES,
                                      blank=True)
    cause_brief = models.CharField(max_length=300, blank=True)

    # Reporter (often a family/community member → encrypt name + mobile).
    reporter_name   = EncryptedCharField()
    reporter_role   = models.CharField(max_length=20, blank=True)
    reporter_mobile = EncryptedCharField(blank=True)
    notification_date = models.DateField(null=True, blank=True)

    # Provenance.
    latitude  = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    # ── Manager approval (single-stage CIPRB) — see module note above.
    approval_status = models.CharField(
        max_length=20, choices=_APPROVAL_CHOICES, default='APPROVED', db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, default='')
    kobo_submission_id = models.CharField(max_length=100, blank=True, default='')
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True, default='')
    # Server-issued system reference (<FORM>-<DIST>-<NNNN>, e.g. NS1-BH-0042)
    # — allocated by programs.refs on ingestion; the hand-written paper
    # serial stays separate as the bridge to the paper register.
    system_ref = models.CharField(max_length=24, blank=True, null=True,
                                  unique=True, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-date_of_death', '-created_at']
        verbose_name = 'MPDSR Death Notification'
        verbose_name_plural = 'MPDSR Death Notifications'
        indexes = [
            models.Index(fields=['organisation', 'death_kind']),
            models.Index(fields=['district', 'date_of_death']),
        ]

    def __str__(self):
        return f'Notification {self.case_serial or str(self.id)[:8]} ({self.death_kind})'


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║   MaternalNearMissCase — WHO MNM audit                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class MaternalNearMissCase(models.Model):
    """One MNM audit per case. Three sections of binary screening
    questions (severe complications, critical interventions,
    life-threatening conditions) plus the delivery context and an audit
    summary."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_serial = models.CharField(max_length=50, blank=True, db_index=True)

    submission = models.OneToOneField(
        'submissions.KoboSubmission',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='mnm_case',
    )
    organisation = models.CharField(max_length=20, default='CIPRB',
                                    db_index=True)

    # Location + woman.
    district = models.CharField(max_length=100, db_index=True)
    upazila  = models.CharField(max_length=100, blank=True)
    union    = models.CharField(max_length=100, blank=True)
    village  = models.CharField(max_length=100, blank=True)
    # woman_name is a dedup lookup key (filter in handle_ciprb_near_miss) — same
    # constraint as deceased_name above; kept plaintext (encrypting breaks dedup).
    woman_name = models.CharField(max_length=200)
    woman_age  = models.PositiveSmallIntegerField(null=True, blank=True)
    gestational_weeks = models.PositiveSmallIntegerField(null=True, blank=True)
    facility_name = models.CharField(max_length=200, blank=True)
    event_date = models.DateField(db_index=True)

    # The 17 WHO screening flags are true 3-state: True = Yes, False = No,
    # None = Unknown. null=True (and NO default) keeps the No/Unknown
    # distinction the form captures instead of collapsing 'Unknown' into the
    # boolean default. Existing False rows are unaffected — this only widens.

    # Section 1 — severe maternal complications (6 flags).
    sev_pph       = models.BooleanField(null=True)
    sev_preec     = models.BooleanField(null=True)
    eclampsia     = models.BooleanField(null=True)
    sepsis        = models.BooleanField(null=True)
    rupt_uterus   = models.BooleanField(null=True)
    sev_abortion  = models.BooleanField(null=True)

    # Section 2 — critical interventions (4 flags).
    crit_blood    = models.BooleanField(null=True)
    crit_radiol   = models.BooleanField(null=True)
    crit_laparot  = models.BooleanField(null=True)
    crit_icu      = models.BooleanField(null=True)

    # Section 3 — life-threatening conditions (7 flags).
    life_cardio   = models.BooleanField(null=True)
    life_resp     = models.BooleanField(null=True)
    life_renal    = models.BooleanField(null=True)
    life_coag     = models.BooleanField(null=True)
    life_hepatic  = models.BooleanField(null=True)
    life_neuro    = models.BooleanField(null=True)
    life_uterine  = models.BooleanField(null=True)

    # Delivery + outcome.
    mode_of_delivery   = models.CharField(max_length=30, blank=True)
    delivery_outcome   = models.CharField(max_length=20, blank=True)
    cause_of_near_miss = models.CharField(max_length=50, blank=True,
                                          db_index=True)
    contributory_conditions = models.TextField(blank=True)
    audit_summary           = models.TextField(blank=True)

    # Provenance.
    latitude  = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    enumerator_name = EncryptedCharField(blank=True)     # Fernet at rest
    enumerator_mobile = EncryptedCharField(blank=True)   # Fernet at rest
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Manager approval (single-stage CIPRB) — see module note above.
    approval_status = models.CharField(
        max_length=20, choices=_APPROVAL_CHOICES, default='APPROVED', db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, default='')
    kobo_submission_id = models.CharField(max_length=100, blank=True, default='')
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True, default='')
    # Server-issued system reference (<FORM>-<DIST>-<NNNN>, e.g. NS1-BH-0042)
    # — allocated by programs.refs on ingestion; the hand-written paper
    # serial stays separate as the bridge to the paper register.
    system_ref = models.CharField(max_length=24, blank=True, null=True,
                                  unique=True, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-event_date', '-created_at']
        verbose_name = 'Maternal Near Miss Case'
        verbose_name_plural = 'Maternal Near Miss Cases'
        indexes = [
            models.Index(fields=['organisation', 'event_date']),
            models.Index(fields=['district', 'event_date']),
        ]

    def __str__(self):
        return f'MNM {self.case_serial or str(self.id)[:8]} ({self.district})'

    @property
    def severe_complication_count(self) -> int:
        # Count only Yes (True); None (Unknown) and False (No) do not count.
        return sum(1 for v in (self.sev_pph, self.sev_preec, self.eclampsia,
                               self.sepsis, self.rupt_uterus, self.sev_abortion)
                   if v is True)

    @property
    def critical_intervention_count(self) -> int:
        return sum(1 for v in (self.crit_blood, self.crit_radiol,
                               self.crit_laparot, self.crit_icu)
                   if v is True)

    @property
    def life_threat_count(self) -> int:
        return sum(1 for v in (self.life_cardio, self.life_resp, self.life_renal,
                               self.life_coag, self.life_hepatic, self.life_neuro,
                               self.life_uterine)
                   if v is True)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║   SurgeryChecklist — WHO Surgical Safety Checklist (CIPRB-11)            ║
# ║                                                                          ║
# ║   Not a death-surveillance form: this is a clinical-quality checklist    ║
# ║   (Bangladesh QIS Annex-13) the OT team fills per operation. It lives    ║
# ║   here beside the other CIPRB standalone case models to reuse the same   ║
# ║   single-stage approval gate + system-ref machinery, rather than open a  ║
# ║   new app for one model. Tanjina (CIPRB RCH) asked for the three phases  ║
# ║   — Sign In / Time Out / Sign Out — with per-phase completion trackable  ║
# ║   at a glance, plus an automatic operation ID (the system_ref).          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# The checklist items that make up each phase, in form order. Single source of
# truth for both the webhook handler (which scores a submission) and the
# dashboard aggregate (which reports compliance), so the two can never drift.
# These are the checklist item names in build_ciprb_forms._safe_surgery_survey
# (mostly `acknowledge` tick boxes, plus a few select_one); a blank/unticked
# answer counts as not done.
SURGERY_PHASE_ITEMS = {
    'signin': [
        'si_team_mobilized', 'si_urgency', 'si_identity', 'si_sterility',
        'si_anesthesia_check', 'si_pulse_oximeter', 'si_allergy',
        'si_antibiotic', 'si_antacid', 'si_airway', 'si_asa', 'si_pph',
        'si_iv_access', 'si_blood_available', 'si_haemoglobin', 'si_platelet',
        'si_other_labs', 'si_blood_group', 'si_newborn_resus',
    ],
    'timeout': [
        'to_team_intro', 'to_patient_confirm', 'to_nursing_equipment',
        'to_skin_prep', 'to_vaginal_prep', 'to_surgeon_steps',
        'to_surgeon_difficulty', 'to_surgeon_blood', 'to_surgeon_concerns',
        'to_anesth_concerns', 'to_newborn_concerns',
    ],
    'signout': [
        'so_surgery_performed', 'so_counts', 'so_blood_loss', 'so_specimen',
        'so_equipment', 'so_recovery', 'so_ward',
    ],
}
# The one answer value that means the checklist step was NOT carried out. Every
# other value (yes / no / na / done / the equipment-ready variants) means the
# team addressed the item — WHO compliance is "the check happened", not "the
# answer was yes". A blank answer is also treated as not-done (step skipped).
SURGERY_NOT_DONE = 'not_done'


class SurgeryChecklist(models.Model):
    """One WHO Surgical Safety Checklist per operation (CIPRB-11).

    Phase completion is computed on ingestion and stored as counts + a boolean
    per phase so the dashboard can show Sign In / Time Out / Sign Out status at
    a glance without re-reading raw_payload. `fully_compliant` is true only when
    all three phases are complete. patient_name is encrypted at rest and is kept
    OUT of the at-a-glance dashboard list (it surfaces only in the PII-gated
    approval drawer)."""

    PHASES = ('signin', 'timeout', 'signout')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.CharField(max_length=20, default='CIPRB', db_index=True)

    # Location (the shared _meta community block the form carries).
    district = models.CharField(max_length=100, db_index=True)
    upazila  = models.CharField(max_length=100, blank=True)
    union    = models.CharField(max_length=100, blank=True)
    village  = models.CharField(max_length=100, blank=True)

    # Operation identity.
    facility_name  = models.CharField(max_length=200, blank=True)
    ward_unit      = models.CharField(max_length=120, blank=True)
    operation_name = models.CharField(max_length=300)
    op_datetime    = models.DateTimeField(null=True, blank=True, db_index=True)
    collection_date = models.DateField(null=True, blank=True)
    surgeon         = models.CharField(max_length=200, blank=True)
    anesthesiologist = models.CharField(max_length=200, blank=True)
    # Patient name is PII — encrypted at rest, never returned by the at-a-glance
    # dashboard list (only the PII-gated approval drawer / register shows it).
    patient_name = EncryptedCharField(blank=True)

    # Per-phase completion, computed on ingestion from SURGERY_PHASE_ITEMS.
    signin_total   = models.PositiveSmallIntegerField(default=0)
    signin_done    = models.PositiveSmallIntegerField(default=0)
    signin_complete = models.BooleanField(default=False, db_index=True)
    timeout_total  = models.PositiveSmallIntegerField(default=0)
    timeout_done   = models.PositiveSmallIntegerField(default=0)
    timeout_complete = models.BooleanField(default=False, db_index=True)
    signout_total  = models.PositiveSmallIntegerField(default=0)
    signout_done   = models.PositiveSmallIntegerField(default=0)
    signout_complete = models.BooleanField(default=False, db_index=True)
    fully_compliant = models.BooleanField(default=False, db_index=True)

    # Provenance.
    latitude  = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    enumerator_name = EncryptedCharField(blank=True)     # Fernet at rest
    enumerator_mobile = EncryptedCharField(blank=True)   # Fernet at rest
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Manager approval (single-stage CIPRB) — see module note above.
    approval_status = models.CharField(
        max_length=20, choices=_APPROVAL_CHOICES, default='APPROVED', db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, default='')
    kobo_submission_id = models.CharField(max_length=100, blank=True, default='',
                                          db_index=True)
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True, default='')
    # Server-issued operation ID (<SS>-<DIST>-<NNNN>, e.g. SS-DH-0007) — the
    # "automated unique ID" Tanjina asked for. Allocated by programs.refs on
    # ingestion; distinct from any paper serial.
    system_ref = models.CharField(max_length=24, blank=True, null=True,
                                  unique=True, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-op_datetime', '-created_at']
        verbose_name = 'Safe Surgery Checklist'
        verbose_name_plural = 'Safe Surgery Checklists'
        indexes = [
            models.Index(fields=['organisation', 'op_datetime']),
            models.Index(fields=['district', 'fully_compliant']),
        ]

    def __str__(self):
        return f'Surgery {self.system_ref or str(self.id)[:8]} ({self.operation_name})'

    @property
    def phases_complete_count(self) -> int:
        return sum(1 for v in (self.signin_complete, self.timeout_complete,
                               self.signout_complete) if v)
