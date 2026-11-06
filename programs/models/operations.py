"""
Programme operations models:
  - TrainingEvent       (Training / Orientation / Workshop — KF-20)
  - CoordMeeting        (Coordination Meeting — KF-19)
  - MobileHealthCamp    (PHD only — KF-18)
  - VisitorRegister     (KF-21)
"""
import uuid
from django.core.exceptions import ValidationError
from django.db import models
from .._base_choices import ORG_CHOICES
from ._base import TimestampedModel, SubmissionBase


# 2 MiB hard cap on optional photo uploads attached to meeting / training
# reports. Surfaced in the model's clean() and serializer validators so it
# is enforced regardless of code path (API, admin, future Kobo ingest).
MAX_PHOTO_BYTES = 2 * 1024 * 1024


def validate_photo_size(file_obj):
    """Reject any uploaded image larger than MAX_PHOTO_BYTES.

    File-storage backends differ in how they report size; this helper
    tolerates both `.size` and `.file.size` and a missing attribute (in
    which case nothing is enforced — the serializer also re-checks).
    An unattached FieldFile (model field with no file set yet) is also
    skipped — Django's FieldFile.size raises ValueError when no file is
    associated, which used to bubble out of clean() on partial saves."""
    # Falsy includes None, '', and unattached FieldFile (bool() returns False
    # when .name is empty).
    if not file_obj:
        return
    # Some FieldFile variants raise on .size when nothing is attached.
    try:
        size = file_obj.size
    except (ValueError, AttributeError):
        return
    if size is None:
        return
    if size > MAX_PHOTO_BYTES:
        raise ValidationError(
            f'Photo too large ({size / 1024 / 1024:.2f} MiB). '
            f'Maximum allowed is 2 MiB.',
            code='photo_too_large',
        )


class TrainingEvent(SubmissionBase):
    """
    Training / orientation / workshop event.
    total_participants feeds indicators:
      Bandhu: 2.1 (health managers), 2.2 (midwives), 2.5 (PEs)
      PHD: 2.1 (managers), 2.2 (MAs/midwives), 2.3 (PEs)
    """
    ORIENTATION = 'orientation'
    TRAINING = 'training'
    WORKSHOP = 'workshop'
    EVENT_TYPE_CHOICES = [
        (ORIENTATION, 'Orientation'),
        (TRAINING, 'Training'),
        (WORKSHOP, 'Workshop'),
    ]

    HM = 'HM'       # Health Managers
    MW = 'MW'       # Midwives / Medical Assistants
    PE = 'PE'       # Peer Educators
    CL = 'CL'       # Community Leaders
    GOB = 'GOB'     # Government Officials
    MIXED = 'MIXED'
    PARTICIPANT_TYPE_CHOICES = [
        (HM, 'Health Managers (UHC/DGHS/DGFP)'),
        (MW, 'Midwives / Medical Assistants'),
        (PE, 'Peer Educators'),
        (CL, 'Community Leaders'),
        (GOB, 'District / Upazila GOB Staff'),
        (MIXED, 'Mixed'),
    ]

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='training_events'
    )

    event_date = models.DateField(db_index=True)
    event_end_date = models.DateField(null=True, blank=True)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    participant_type = models.CharField(max_length=10, choices=PARTICIPANT_TYPE_CHOICES)
    topic = models.CharField(max_length=300)
    location_text = models.CharField(max_length=300, blank=True)
    district = models.CharField(max_length=100, blank=True)

    total_participants = models.PositiveIntegerField(default=0)
    male_participants = models.PositiveIntegerField(default=0)
    female_participants = models.PositiveIntegerField(default=0)
    tg_participants = models.PositiveIntegerField(default=0)

    # ─── Audit FIX 7.7 — Doctor/Nurse/Midwife separate counts ──────────────
    # total_participants is auto-populated from the sub-counts on save when
    # any sub-count is set, so the indicator pipeline keeps reading a single
    # number while the Kobo form can capture the breakdown.
    participants_doctors        = models.PositiveSmallIntegerField(default=0)
    participants_nurses         = models.PositiveSmallIntegerField(default=0)
    participants_midwives       = models.PositiveSmallIntegerField(default=0)
    participants_other          = models.PositiveSmallIntegerField(default=0)
    participants_other_label    = models.CharField(max_length=200, blank=True)

    facilitator = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    # ─── Mandatory upload gate (Step 5) ────────────────────────────────────
    # `report_file` MUST be present. Enforced at model level (blank=False),
    # serializer level (validate_report_file), and frontend level (submit
    # disabled until file attached). Never silently fall back to text-only.
    report_file = models.FileField(
        upload_to='training_events/reports/%Y/%m/',
        blank=False, null=False,
    )
    # Optional photo of the training. ≤ 2 MiB enforced everywhere.
    photo = models.ImageField(
        upload_to='training_events/photos/%Y/%m/',
        blank=True, null=True,
        validators=[validate_photo_size],
    )
    # Optional call-up letter / invitation.
    call_up_letter = models.FileField(
        upload_to='training_events/call_up/%Y/%m/',
        blank=True, null=True,
    )

    class Meta:
        ordering = ['-event_date']

    @property
    def auto_total_participants(self) -> int:
        """Audit FIX 7.7 — sum of category sub-counts. Returns 0 when none
        of the sub-counts are set, which leaves total_participants as the
        sole source for legacy rows."""
        return (
            (self.participants_doctors  or 0)
            + (self.participants_nurses   or 0)
            + (self.participants_midwives or 0)
            + (self.participants_other    or 0)
        )

    def clean(self):
        super().clean()
        if not self.report_file:
            raise ValidationError(
                {'report_file': 'A training report file is required.'},
                code='required',
            )
        validate_photo_size(self.photo)

        # Audit FIX 7.7 — if any sub-count is set, the total must agree.
        auto = self.auto_total_participants
        any_sub = auto > 0
        if any_sub and self.total_participants and self.total_participants != auto:
            raise ValidationError(
                {'total_participants':
                    f'total_participants ({self.total_participants}) must equal '
                    f'the sum of doctor + nurse + midwife + other counts '
                    f'({auto}). Clear the sub-counts or correct the total — '
                    f'the total is auto-calculated when sub-counts are present.'},
                code='total_participants_mismatch',
            )

    def save(self, *args, **kwargs):
        # Audit FIX 7.7 — auto-populate total when sub-counts are set.
        auto = self.auto_total_participants
        if auto > 0:
            self.total_participants = auto
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.event_type} — {self.topic[:40]} ({self.event_date})'


class CoordMeeting(SubmissionBase):
    """
    Coordination meeting report.
    feeds indicators: Bandhu 2.3 (GOB), 2.4 (CBO); PHD 2.4
    """
    GOB = 'GOB'
    CBO = 'CBO'
    INTERNAL = 'internal'
    MULTI = 'multi'
    DAY_OBSERVANCE = 'day_observance'
    MEETING_TYPE_CHOICES = [
        (GOB, 'GOB / Health Staff'),
        (CBO, 'CBO / Community Network'),
        (INTERNAL, 'Internal'),
        (MULTI, 'Multi-Stakeholder'),
        # Audit FIX 12.4 — covers Bandhu indicator 2.6 "Support day observances"
        # (e.g. World AIDS Day, Human Rights Day, Hijra Pride). Counted toward
        # the 2-event annual target.
        (DAY_OBSERVANCE, 'Day Observance / Awareness Event'),
    ]

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='coord_meetings'
    )

    meeting_date = models.DateField(db_index=True)
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPE_CHOICES, db_index=True)
    location_text = models.CharField(max_length=300, blank=True)
    district = models.CharField(max_length=100, blank=True)
    participant_count = models.PositiveIntegerField(default=0)
    agenda = models.TextField(blank=True)
    key_decisions = models.TextField(blank=True)
    prepared_by = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    # ─── Mandatory upload gate (Step 5) ────────────────────────────────────
    # `meeting_notes` (signed minutes / scanned register / typed report)
    # MUST be present. A missing file blocks submission with a clear
    # ValidationError at every layer — model.clean(), serializer.validate_
    # meeting_notes, and the frontend submit button is disabled until a
    # file is attached.
    meeting_notes = models.FileField(
        upload_to='coord_meetings/notes/%Y/%m/',
        blank=False, null=False,
    )
    # Optional photo from the meeting. ≤ 2 MiB enforced.
    photo = models.ImageField(
        upload_to='coord_meetings/photos/%Y/%m/',
        blank=True, null=True,
        validators=[validate_photo_size],
    )
    # Optional call-up letter / invitation sent before the meeting.
    call_up_letter = models.FileField(
        upload_to='coord_meetings/call_up/%Y/%m/',
        blank=True, null=True,
    )

    class Meta:
        ordering = ['-meeting_date']

    def clean(self):
        super().clean()
        if not self.meeting_notes:
            raise ValidationError(
                {'meeting_notes': 'A meeting notes file is required.'},
                code='required',
            )
        validate_photo_size(self.photo)

    def __str__(self):
        return f'{self.meeting_type} meeting — {self.meeting_date}'


class MobileHealthCamp(SubmissionBase):
    """
    PHD only — mobile health camp at brothel.
    camp count feeds indicator I_PHD_1_8 (target: 40 camps).
    """
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='mobile_health_camps'
    )

    camp_date = models.DateField(db_index=True)
    location_text = models.CharField(max_length=300, blank=True)
    brothel_name = models.CharField(max_length=200, blank=True)

    clients_served = models.PositiveIntegerField(default=0)
    hiv_tests_done = models.PositiveIntegerField(default=0)
    sti_screenings_done = models.PositiveIntegerField(default=0)
    counselling_sessions = models.PositiveIntegerField(default=0)
    referrals_made = models.PositiveIntegerField(default=0)
    condoms_distributed = models.PositiveIntegerField(default=0)

    services_description = models.TextField(blank=True)
    team_members = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-camp_date']

    def __str__(self):
        return f'Mobile Camp {self.camp_date} — {self.brothel_name or self.center}'


class VisitorRegister(TimestampedModel):
    """External visitor register (browser-based)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='visitor_entries'
    )

    visit_date = models.DateField()
    visitor_name = models.CharField(max_length=200)
    designation_and_address = models.CharField(max_length=300, blank=True)
    purpose_of_visit = models.TextField(blank=True)
    iec_bcc_distributed = models.BooleanField(default=False)
    visitor_comments = models.TextField(blank=True)
    prepared_by = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-visit_date']
