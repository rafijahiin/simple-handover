"""
NilReport — a "No reporting today" record.

When a Wellness Centre has no field upload for a day, a zero-day return is
filed (centre + date + reason) so missing days are explained rather than
silently blank. Two routes create one:

  - the field "No Reporting Today" Kobo form → webhook (programs.nil_handlers),
    which records it at PENDING (so kobo_submission_id is set), then
  - a manager logs it in-system via the API.

Either way it follows its org's normal approval (PHD single-stage; Bandhu
two-stage: manager then UNFPA) before it counts in the reporting / compliance
view, and it counts toward the centre's daily reporting the moment it lands.
"""
from django.db import models
from django.db.models import Q

from ._base import SubmissionBase
from .._base_choices import ORG_CHOICES


class NilReport(SubmissionBase):
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='nil_reports',
    )
    report_date = models.DateField(db_index=True)
    reason = models.TextField()

    class Meta:
        ordering = ['-report_date', '-created_at']
        indexes = [
            models.Index(fields=['organisation', '-report_date']),
        ]
        # One nil-report per centre per day (a centre either reported or it
        # didn't). Null centre allowed for org-wide nil days.
        constraints = [
            models.UniqueConstraint(
                fields=['organisation', 'center', 'report_date'],
                name='uniq_nil_report_per_centre_day',
            ),
            # Postgres treats NULLs as distinct, so the constraint above does
            # NOT cover org-wide (null-centre) nil days — add a partial one.
            models.UniqueConstraint(
                fields=['organisation', 'report_date'],
                condition=Q(center__isnull=True),
                name='uniq_nil_report_org_day_no_centre',
            ),
        ]

    def __str__(self):
        return f'No report — {self.organisation} / {self.center or "all"} ({self.report_date})'
