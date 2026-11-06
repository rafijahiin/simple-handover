"""
GBV Case — Gender-Based Violence incident record.

SECURITY: Survivor name, contact, address and perpetrator name/address
are encrypted at rest using Fernet symmetric encryption (same key as
existing mpdsr encryption — FERNET_KEY env var).
Dashboard views show AGGREGATE COUNTS ONLY.
Individual records visible only to GBV Officer and Super Admin roles.
All access logged to GBVAccessLog.
"""
import logging
import uuid
from django.db import models
from django.conf import settings
from .._base_choices import ORG_CHOICES
from ._base import SubmissionBase

logger = logging.getLogger('programs')


# Key handling is delegated to fistula.encryption, which is the ONE place that
# knows about FERNET_KEY + FERNET_KEY_FALLBACKS. This module used to carry its
# own copy of the Fernet logic; during the Oct 2026 key rotation that meant GBV
# survivor/perpetrator PII (and Client PII, which imports this field) would NOT
# have decrypted with the rotation fallback key and would have silently read
# back blank. The ciphertext format is identical, so delegating is safe for
# existing rows. The EncryptedCharField class below stays defined here so the
# path recorded in existing migrations keeps resolving.
from fistula.encryption import _enc as _encrypt, _dec as _decrypt  # noqa: E402


class EncryptedCharField(models.TextField):
    """Transparent Fernet-encrypt on save, decrypt on access."""

    def from_db_value(self, value, expression, connection):
        return _decrypt(value) if value else value

    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)
        encrypted = _encrypt(value)
        setattr(model_instance, self.attname, encrypted)
        return encrypted


class GBVCase(SubmissionBase):
    SEXUAL = 'sexual'
    PHYSICAL = 'physical'
    ECONOMIC = 'economic'
    PSYCHOLOGICAL = 'psychological'

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='gbv_cases'
    )

    # Dates
    interview_date = models.DateField(db_index=True)
    incident_date = models.DateField(db_index=True)

    # Encrypted PII
    survivor_name = EncryptedCharField(blank=True)
    survivor_contact = EncryptedCharField(blank=True)
    survivor_address = EncryptedCharField(blank=True)
    perpetrator_name = EncryptedCharField(blank=True)
    perpetrator_address = EncryptedCharField(blank=True)

    # Survivor demographics (non-PII)
    survivor_age = models.PositiveSmallIntegerField(null=True, blank=True)
    survivor_gender_identity = models.CharField(max_length=50, blank=True)
    survivor_disability = models.BooleanField(default=False)

    # Violence type — top-level booleans kept for backward compatibility
    # with existing rows and existing dashboard queries (gbv_sexual /
    # gbv_physical etc.). The new sub-type fields below (audit FIX 7.3)
    # carry the granular breakdown required by the validation spec.
    gbv_sexual = models.BooleanField(default=False)
    gbv_physical = models.BooleanField(default=False)
    gbv_economic = models.BooleanField(default=False)
    gbv_psychological = models.BooleanField(default=False)

    # ─── Sexual violence sub-types (audit FIX 7.3) ─────────────────────────
    gbv_rape                   = models.BooleanField(default=False)
    gbv_sexual_harassment      = models.BooleanField(default=False)
    gbv_forced_gender_identity = models.BooleanField(default=False)
    gbv_forced_pregnancy       = models.BooleanField(default=False)
    gbv_genital_mutilation     = models.BooleanField(default=False)
    gbv_forced_sex_work        = models.BooleanField(default=False)

    # ─── Physical violence sub-types ───────────────────────────────────────
    gbv_assault            = models.BooleanField(default=False)
    gbv_beating            = models.BooleanField(default=False)
    gbv_acid_attack        = models.BooleanField(default=False)
    gbv_forced_labour      = models.BooleanField(default=False)
    gbv_domestic_violence  = models.BooleanField(default=False)
    gbv_confinement        = models.BooleanField(default=False)

    # ─── Economic violence sub-types ───────────────────────────────────────
    gbv_denied_work        = models.BooleanField(default=False)
    gbv_denied_education   = models.BooleanField(default=False)
    gbv_denied_inheritance = models.BooleanField(default=False)

    # ─── Mental / psychological violence sub-types ─────────────────────────
    gbv_verbal_abuse     = models.BooleanField(default=False)
    gbv_threats          = models.BooleanField(default=False)
    gbv_blackmail        = models.BooleanField(default=False)
    gbv_family_rejection = models.BooleanField(default=False)

    # Perpetrator info (non-PII)
    perpetrator_count        = models.PositiveSmallIntegerField(default=1)
    perpetrator_gender       = models.CharField(max_length=20, blank=True)
    perpetrator_relationship = models.CharField(max_length=100, blank=True)
    # ─── Perpetrator profile extras (audit FIX 7.3) ────────────────────────
    perpetrator_age          = models.PositiveSmallIntegerField(null=True, blank=True)
    perpetrator_occupation   = models.CharField(max_length=200, blank=True)

    # Prior reporting
    prior_reporting = models.BooleanField(default=False)
    prior_gbv_history = models.BooleanField(default=False)

    # Services needed (multi-select)
    needs_medical = models.BooleanField(default=False)
    needs_legal = models.BooleanField(default=False)
    needs_shelter = models.BooleanField(default=False)
    needs_psychosocial = models.BooleanField(default=False)

    local_action_taken = models.TextField(blank=True)
    case_officer_name = models.CharField(max_length=200, blank=True)
    supervisor_name = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-incident_date']

    def __str__(self):
        return f'GBV Case {self.incident_date} ({self.organisation})'

    @property
    def violence_types(self):
        types = []
        if self.gbv_sexual:
            types.append('Sexual')
        if self.gbv_physical:
            types.append('Physical')
        if self.gbv_economic:
            types.append('Economic')
        if self.gbv_psychological:
            types.append('Psychological')
        return types


class GBVAccessLog(models.Model):
    """Immutable audit log — every view of a GBV case detail is recorded."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(GBVCase, on_delete=models.CASCADE, related_name='access_logs')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+'
    )
    action = models.CharField(max_length=50, default='view')
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.action} on GBV case at {self.timestamp:%Y-%m-%d %H:%M}'
