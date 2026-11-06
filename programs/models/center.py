"""
ServiceCenter — the physical location where services are delivered.
Bandhu: 5 Drop-In Centers (DICs).
PHD: 11 brothel-based centres (placeholders pending exact names).
"""
import uuid
from django.db import models
from .._base_choices import ORG_CHOICES
from ._base import TimestampedModel


class ServiceCenter(TimestampedModel):
    DIC = 'DIC'
    BROTHEL = 'BROTHEL'
    SUB_DIC = 'SUB_DIC'
    MOBILE = 'MOBILE'
    KP_CLINIC = 'KP_CLINIC'
    CENTER_TYPE_CHOICES = [
        (DIC, 'Drop-In Center'),
        (BROTHEL, 'Brothel-Based Center'),
        (SUB_DIC, 'Sub Drop-In Center'),
        (MOBILE, 'Mobile Outreach'),
        (KP_CLINIC, 'Key Population Clinic'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    name = models.CharField(max_length=200)
    name_bangla = models.CharField(max_length=200, blank=True)
    code = models.CharField(max_length=20, unique=True)
    center_type = models.CharField(max_length=20, choices=CENTER_TYPE_CHOICES)
    district = models.CharField(max_length=100)
    upazila = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['organisation', 'name']

    def __str__(self):
        return f'{self.name} ({self.organisation})'

    # ─── Audit FIX 10.4 + 10.5 — naming convention check ───────────────────
    # PHD centers should read "[District] Brothel (PHD)".
    # Bandhu centers should read "Wellness Center [District] (Bandhu)".
    # This is a warning-only convention — existing centers are not forced
    # to rename. The property surfaces compliance status so the Admin Panel
    # and seed validation can flag drift without blocking writes.
    @property
    def naming_compliant(self) -> bool:
        name = self.name or ''
        if self.organisation == 'PHD':
            return '(PHD)' in name and 'Brothel' in name
        if self.organisation == 'Bandhu':
            return '(Bandhu)' in name and 'Wellness' in name
        # Other orgs (CIPRB, UNFPA) have no enforced convention yet.
        return True

    @property
    def naming_convention_hint(self) -> str:
        """Human-readable hint shown next to non-compliant rows in admin."""
        if self.organisation == 'PHD':
            return 'PHD convention: "[District] Brothel (PHD)"'
        if self.organisation == 'Bandhu':
            return 'Bandhu convention: "Wellness Center [District] (Bandhu)"'
        return ''
