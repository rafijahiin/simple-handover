import uuid

from django.conf import settings
from django.db import models



class MonthlyTarget(models.Model):
    """Programme target for a partner's form type in a given month."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partner = models.CharField(max_length=20, db_index=True)
    form_type = models.CharField(max_length=30, db_index=True)  # programs or legacy key
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()  # 1–12
    target = models.PositiveIntegerField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='targets_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('partner', 'form_type', 'year', 'month')]
        ordering = ['-year', '-month', 'partner']
        indexes = [
            models.Index(fields=['partner', 'year', 'month']),
        ]

    def __str__(self):
        return f'{self.partner} / {self.form_type} / {self.year}-{self.month:02d} → {self.target}'


class AlertSeverity(models.TextChoices):
    INFO = 'info', 'Info'
    WARNING = 'warning', 'Warning'
    CRITICAL = 'critical', 'Critical'


class AlertType(models.TextChoices):
    BELOW_TARGET = 'below_target', 'Below Target'
    ANOMALY = 'anomaly', 'Anomaly Detected'
    OVERDUE_CASES = 'overdue_cases', 'Overdue Cases'
    SUBMISSION_GAP = 'submission_gap', '48-Hour Submission Gap'
    DAILY_SILENCE = 'daily_silence', 'No Daily Report'
    CUSTOM = 'custom', 'Custom'


class Alert(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partner = models.CharField(max_length=20, blank=True, db_index=True)
    alert_type = models.CharField(max_length=30, choices=AlertType.choices, db_index=True)
    severity = models.CharField(
        max_length=20,
        choices=AlertSeverity.choices,
        default=AlertSeverity.WARNING,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    acknowledged = models.BooleanField(default=False, db_index=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='acknowledged_alerts',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['partner', 'acknowledged']),
            models.Index(fields=['severity', 'acknowledged']),
        ]

    def __str__(self):
        return f'[{self.severity}] {self.title}'
