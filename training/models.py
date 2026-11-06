import uuid

from django.conf import settings
from django.db import models


class TrainingSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    partner = models.CharField(max_length=20, db_index=True)
    district = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=100, blank=True)

    topic = models.CharField(max_length=300)
    facilitator = models.CharField(max_length=200, blank=True)
    date = models.DateField(db_index=True)
    duration_hours = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    expected_participants = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='training_sessions_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['partner', 'date']),
        ]

    def __str__(self):
        return f'{self.topic} — {self.partner} — {self.date}'

    @property
    def actual_participants(self) -> int:
        return self.attendances.filter(attended=True).count()

    @property
    def attendance_rate(self) -> float | None:
        if not self.expected_participants:
            return None
        return round(self.actual_participants / self.expected_participants * 100, 1)


class ParticipantRole(models.TextChoices):
    COMMUNITY_WORKER = 'community_worker', 'Community Worker'
    SUPERVISOR = 'supervisor', 'Supervisor'
    HEALTH_STAFF = 'health_staff', 'Health Staff'
    OTHER = 'other', 'Other'


class TrainingAttendance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        TrainingSession,
        on_delete=models.CASCADE,
        related_name='attendances',
    )
    participant_name = models.CharField(max_length=200)
    role = models.CharField(
        max_length=30,
        choices=ParticipantRole.choices,
        default=ParticipantRole.COMMUNITY_WORKER,
    )
    attended = models.BooleanField(default=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['participant_name']
        unique_together = [('session', 'participant_name')]

    def __str__(self):
        return f'{self.participant_name} @ {self.session}'
