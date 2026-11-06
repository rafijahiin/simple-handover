import uuid
from django.conf import settings
from django.db import models


class FormType(models.TextChoices):
    MPDSR = 'mpdsr', 'MPDSR'
    FISTULA = 'fistula', 'Fistula Campaign'
    ACTIVITY = 'activity', 'Activity Report'
    BASELINE = 'baseline', 'Baseline/Endline Survey'
    FISTULA_STAGED = 'fistula_staged', 'Fistula Staged (Auto-ID, 5 stages)'
    MPDSR_RESPONSE_PLAN = 'mpdsr_response_plan', 'MPDSR Response Plan'


class SubmissionStatus(models.TextChoices):
    PENDING = 'pending', 'Pending Review'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


class KoboSubmission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kobo_id = models.CharField(max_length=100, unique=True)  # prevents duplicate processing
    form_type = models.CharField(max_length=20, choices=FormType.choices, db_index=True)
    partner = models.CharField(max_length=20, blank=True, db_index=True)

    # Key fields extracted for querying — full payload is in raw_data
    worker_name = models.CharField(max_length=200, blank=True)
    district = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)  # Division in Bangladesh
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    # Centre code — denormalised from raw_data at ingest time so per-centre
    # health-flag queries don't need to join through the JSON payload. Used by
    # the 74-hour Programme Health Flag system to show 'X of N centres
    # submitted today' granularity (Animesh's spec).
    centre_code = models.CharField(max_length=40, blank=True, db_index=True)

    submitted_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    raw_data = models.JSONField()

    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_submissions',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # Daily-compliance "zero report": the worker logged in and confirmed
    # there was no patient/activity today. Counts as the day's reporting
    # touch (a positive "nothing happened" signal, not a blank), but is
    # excluded from clinical/volume aggregates.
    is_zero_report = models.BooleanField(default=False, db_index=True)

    # Permanent audit trail of every review action (Animesh's "evidence of
    # you working" requirement). One entry per approve/reject, never
    # overwritten — survives re-review cycles. Each entry:
    #   {reviewer, reviewer_email, action, note, timestamp}
    review_history = models.JSONField(default=list, blank=True)

    def add_review_entry(self, *, user, action: str, note: str = ''):
        """Append an immutable review-history entry. Caller saves."""
        from django.utils import timezone as _tz
        entry = {
            'reviewer': getattr(user, 'full_name', '') or getattr(user, 'email', '') or 'Unknown',
            'reviewer_email': getattr(user, 'email', ''),
            'action': action,
            'note': (note or '').strip(),
            'timestamp': _tz.now().isoformat(),
        }
        history = list(self.review_history or [])
        history.append(entry)
        self.review_history = history
        return entry

    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['partner', 'status', '-submitted_at']),
            models.Index(fields=['form_type', 'status']),
        ]

    def __str__(self):
        return f'{self.get_form_type_display()} — {self.partner} — {self.submitted_at:%Y-%m-%d}'
