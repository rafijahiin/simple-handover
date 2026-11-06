"""
Pharmacy module — PrescriptionRecord.

Step 6 spec: every prescription captured at PHD or Bandhu service centres
goes through this model. Quantities are hard-capped by drug and (where
relevant) by the underlying condition the prescription treats:

    metronidazole   STI=14,  GENERAL=10  tablets
    doxycycline     STI=20,  GENERAL=10  capsules
    b_complex       10                   tablets
    ibuprofen       10                   tablets
    paracetamol     10                   tablets
    ranitidine      10                   tablets
    antacid         10                   tablets
    ors             STANDARD=3, SEVERE=5 sachets   (condition_type=GENERAL
                                                    means STANDARD here)

Limits are enforced at three layers:
  - PrescriptionRecord.clean()    — model-level, raises ValidationError
  - PrescriptionRecordSerializer.validate() — API layer, returns 400
  - frontend field max attribute — disables submit on overflow

There is no silent capping. A quantity exceeding the cap always errors
with a user-facing message identifying the cap.
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Drug(models.TextChoices):
    METRONIDAZOLE = 'metronidazole', 'Metronidazole'
    DOXYCYCLINE   = 'doxycycline',   'Doxycycline'
    B_COMPLEX     = 'b_complex',     'B-Complex'
    IBUPROFEN     = 'ibuprofen',     'Ibuprofen'
    PARACETAMOL   = 'paracetamol',   'Paracetamol'
    RANITIDINE    = 'ranitidine',    'Ranitidine'
    ANTACID       = 'antacid',       'Antacid'
    ORS           = 'ors',           'ORS (Oral Rehydration Salts)'


class ConditionType(models.TextChoices):
    """Why the drug was prescribed. Drives the max-quantity cap for
    metronidazole / doxycycline / ORS. Drugs without a condition-specific
    cap accept either value and apply the same single limit."""
    STI     = 'STI',     'STI'
    GENERAL = 'GENERAL', 'General'
    # ORS-specific: "STANDARD" is treated equivalent to GENERAL; SEVERE
    # is the higher-allowance sachet count for severe dehydration.
    SEVERE  = 'SEVERE',  'Severe (ORS only)'


class ApprovalStatus(models.TextChoices):
    PENDING  = 'PENDING',  'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'


# ─── Hard-coded max-dispense limits ──────────────────────────────────────────
#
# Drugs without per-condition variation map to {None: limit}. Drugs with
# per-condition caps map to {ConditionType.X: limit, ...}.
# UNIT is purely informational — surfaced in the ValidationError message.

DRUG_LIMITS: dict[str, dict] = {
    Drug.METRONIDAZOLE: {
        ConditionType.STI:     14,
        ConditionType.GENERAL: 10,
        '_unit': 'tablets',
    },
    Drug.DOXYCYCLINE: {
        ConditionType.STI:     20,
        ConditionType.GENERAL: 10,
        '_unit': 'capsules',
    },
    Drug.B_COMPLEX: {None: 10, '_unit': 'tablets'},
    Drug.IBUPROFEN: {None: 10, '_unit': 'tablets'},
    Drug.PARACETAMOL: {None: 10, '_unit': 'tablets'},
    Drug.RANITIDINE: {None: 10, '_unit': 'tablets'},
    Drug.ANTACID:    {None: 10, '_unit': 'tablets'},
    Drug.ORS: {
        # GENERAL doubles as the STANDARD dehydration band.
        ConditionType.GENERAL: 3,
        ConditionType.SEVERE:  5,
        '_unit': 'sachets',
    },
}


def max_quantity_for(drug: str, condition_type: str | None) -> tuple[int, str]:
    """Return (max_quantity, unit) for this (drug, condition) pair.

    Raises ValidationError for an unknown drug. Drugs without per-
    condition variation ignore the condition_type and use their single
    limit. Drugs with per-condition variation require a matching key
    (ORS defaults missing/STI to STANDARD/GENERAL).
    """
    table = DRUG_LIMITS.get(drug)
    if table is None:
        raise ValidationError(
            {'drug': f'Unknown drug code "{drug}".'},
            code='unknown_drug',
        )
    unit = table['_unit']

    # Single-limit drugs: condition_type is ignored.
    if None in table:
        return table[None], unit

    # Per-condition drugs: must match. Treat ORS STANDARD as GENERAL.
    key = condition_type
    if drug == Drug.ORS and key not in (ConditionType.GENERAL, ConditionType.SEVERE):
        key = ConditionType.GENERAL
    if key not in table:
        raise ValidationError(
            {'condition_type':
                f'{drug} requires condition_type one of '
                f'{[k for k in table if k != "_unit"]}; got {condition_type!r}.'},
            code='condition_required',
        )
    return table[key], unit


# ─── PrescriptionRecord ──────────────────────────────────────────────────────

class PrescriptionRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Client linkage. Stored as a string to keep Pharmacy loosely coupled
    # from programs.Client — the client model may be revised at workshop.
    client_id = models.CharField(max_length=64, db_index=True)

    partner = models.ForeignKey(
        'partners.Partner',
        on_delete=models.PROTECT,
        related_name='prescriptions',
    )
    center = models.ForeignKey(
        'programs.ServiceCenter',
        on_delete=models.PROTECT,
        related_name='prescriptions',
    )
    prescribed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='prescriptions',
    )
    date = models.DateField(db_index=True)
    drug = models.CharField(max_length=20, choices=Drug.choices)
    quantity = models.PositiveSmallIntegerField()
    condition_type = models.CharField(
        max_length=10, choices=ConditionType.choices,
        default=ConditionType.GENERAL,
    )
    approval_status = models.CharField(
        max_length=10, choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['drug', 'date']),
            models.Index(fields=['partner', 'date']),
        ]

    def clean(self):
        super().clean()
        if self.quantity is None or self.quantity <= 0:
            raise ValidationError(
                {'quantity': 'Quantity must be a positive integer.'},
                code='quantity_invalid',
            )
        max_qty, unit = max_quantity_for(self.drug, self.condition_type)
        if self.quantity > max_qty:
            raise ValidationError(
                {'quantity':
                    f'{self.get_drug_display()} '
                    f'({self.get_condition_type_display()}) capped at '
                    f'{max_qty} {unit}. Requested {self.quantity} {unit} — '
                    f'submission rejected.'},
                code='quantity_exceeds_cap',
            )

    def save(self, *args, **kwargs):
        # Run model-level validation on every save so the cap holds even
        # when the caller skips serializer validation (e.g. ORM-only).
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_drug_display()} × {self.quantity} ({self.date})'
