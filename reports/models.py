import uuid

from django.conf import settings
from django.db import models



class ReportFormat(models.TextChoices):
    PDF = 'pdf', 'PDF'
    DOCX = 'docx', 'Word Document'
    PPTX = 'pptx', 'PowerPoint'
    PNG = 'png', 'Image (PNG)'
    HTML = 'html', 'Web Page'


class ReportType(models.TextChoices):
    MONTHLY_SUMMARY = 'monthly_summary', 'Monthly Summary'
    ONE_PAGER = 'one_pager', 'Infographic'
    NEWSLETTER = 'newsletter', 'Newsletter'
    WEB_REPORT = 'web_report', 'Web Report'


class PeriodType(models.TextChoices):
    BIWEEKLY  = 'biweekly',  'Bi-Weekly'
    MONTHLY   = 'monthly',   'Monthly'
    QUARTERLY = 'quarterly', 'Quarterly'


class NarrativeSource(models.TextChoices):
    """How was the narrative text in this report produced?"""
    AI                    = 'ai',                    'AI (validated)'
    AI_VALIDATION_FAILED  = 'ai_validation_failed',  'AI (validation failed → fallback)'
    AI_DISABLED           = 'ai_disabled',           'AI disabled by user'
    INSUFFICIENT_DATA     = 'insufficient_data',     'Insufficient data — template used'
    AI_API_ERROR          = 'ai_api_error',          'AI API error → fallback'
    TEMPLATE              = 'template',              'Template only'
    HAND_WRITTEN_DEMO     = 'hand_written_demo',     'Hand-written demo content'


class Report(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_type = models.CharField(max_length=30, choices=ReportType.choices, db_index=True)
    format = models.CharField(max_length=10, choices=ReportFormat.choices)
    partner = models.CharField(max_length=20, blank=True, db_index=True)

    # Legacy period fields (kept for backward compat)
    year = models.PositiveSmallIntegerField(default=2026)
    month = models.PositiveSmallIntegerField(default=1)

    # New period fields
    period_type  = models.CharField(
        max_length=10, choices=PeriodType.choices,
        default=PeriodType.MONTHLY, db_index=True,
    )
    period_start = models.DateField(null=True, blank=True)
    period_end   = models.DateField(null=True, blank=True)

    title = models.CharField(max_length=300)
    narrative = models.TextField(blank=True)
    file = models.FileField(upload_to='reports/%Y/%m/', null=True, blank=True)
    # Durable copy of the report bytes in Postgres. Railway's container
    # filesystem is EPHEMERAL (wiped on every redeploy/restart), so the bytes
    # behind `file` do not survive — these do. `download` serves from here.
    file_bytes = models.BinaryField(null=True, blank=True, editable=False)
    original_filename = models.CharField(max_length=200, blank=True)
    # Unguessable token for the shareable web-report link (/r/<token>/). Only
    # set on WEB_REPORT rows; emailed to UNFPA, opens without login.
    share_token = models.CharField(max_length=48, blank=True, db_index=True)

    # Provenance — see NarrativeSource for values
    narrative_source = models.CharField(
        max_length=30, choices=NarrativeSource.choices,
        default=NarrativeSource.TEMPLATE,
        db_index=True,
    )
    model_used = models.CharField(max_length=80, blank=True)

    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reports_generated',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['partner', 'year', 'month']),
        ]

    def __str__(self):
        return f'{self.title} ({self.format})'
