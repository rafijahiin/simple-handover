"""
Partner — canonical registry of implementing partners for the IDMS.

Three rows: CIPRB, Bandhu, PHD. UNFPA is NOT a partner — it is the
funder/supervisor org. Anything that needs a partner reference (indicator
targets, kobo form mappings, map color codes) FK's to this table.

Seeded by migration 0001 — do not insert manually outside of migrations
or seeding management commands.
"""
import uuid

from django.db import models


class Partner(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    code = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text="Canonical short code: 'CIPRB' | 'Bandhu' | 'PHD'.",
    )
    name = models.CharField(max_length=200)
    name_bangla = models.CharField(max_length=200, blank=True)

    color_hex = models.CharField(
        max_length=7,
        default='#00658C',
        help_text='Hex color for map and dashboard accents. '
                  "CIPRB=#0072BC (blue), Bandhu=#00B050 (green), PHD=#ED7D31 (orange).",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Partner'
        verbose_name_plural = 'Partners'

    def __str__(self):
        return self.code
