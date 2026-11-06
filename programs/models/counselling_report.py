"""
PHD Counselling Report (monthly aggregate per counsellor).
Source: Counselling Report.docx → phd_service_log_v1 `sec_counsel` section.

This is a MONTHLY SUMMARY, not per-patient records. The form sends integer
counts per counselling category (counsel_* fields). Previously the webhook
handler logged and discarded these — this model persists them so a whole
monthly report is no longer silently lost.

Field mapping (form field → model field):
  counsel_prepared_by → prepared_by
  counsel_date        → report_date
  counsel_hiv_test    → hiv_test_count
  counsel_sti         → sti_count
  counsel_srhr        → srhr_count
  counsel_gbv         → gbv_count
  counsel_art         → art_count
  counsel_mh          → mh_count
  counsel_total       → total_count        (form auto-calculates)
  counsel_group_mh    → group_mh_count
  counsel_note        → note
"""
from django.db import models
from .._base_choices import ORG_CHOICES
from ._base import SubmissionBase


class PHDCounsellingReport(SubmissionBase):
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='counselling_reports',
    )

    report_date = models.DateField(db_index=True)
    prepared_by = models.CharField(max_length=200, blank=True)

    # Individual counselling counts per category
    hiv_test_count = models.PositiveIntegerField(default=0)
    sti_count = models.PositiveIntegerField(default=0)
    srhr_count = models.PositiveIntegerField(default=0)
    gbv_count = models.PositiveIntegerField(default=0)
    art_count = models.PositiveIntegerField(default=0)
    mh_count = models.PositiveIntegerField(default=0)
    total_count = models.PositiveIntegerField(default=0)
    # Group mental-health counselling count
    group_mh_count = models.PositiveIntegerField(default=0)

    note = models.TextField(blank=True)

    class Meta:
        ordering = ['-report_date']

    def __str__(self):
        return f'Counselling report {self.report_date} ({self.organisation})'
