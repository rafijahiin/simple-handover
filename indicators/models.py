"""
Indicator targets per partner per activity, plus the KoboToolbox form
registry that those targets link to.

Restructured for Step 2 of the IDMS rebuild (May 2026):
  - partner is now a FK to partners.Partner (was: organisation CharField)
  - objective_number is an integer (was: objective string like 'O1')
    Allows 0 (Overall) and the Bandhu 1/2/4 non-sequential pattern.
  - activity_code is a short string like '1.1' or '1.5a'
    (was: activity_ref 'A1.1')
  - activity_label and indicator_label are new — explicit labels
    rather than indicator_code that referenced a function name.
  - target_value is nullable — null renders as "Not Set" in UI.
  - period_start/period_end removed — one target per indicator,
    not cyclical.
  - source_form FK links to KoboFormMapping (null until workshop).
  - updated_by FK records who last edited.
"""
import uuid

from django.conf import settings
from django.db import models


class KoboFormMapping(models.Model):
    """Registry of KoboToolbox forms used in the IDMS. IndicatorTarget rows
    reference this to declare which form generates the data for an
    indicator. Filled in at the validation workshop."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    form_slug = models.CharField(
        max_length=80, unique=True,
        help_text="Stable identifier, e.g. 'spondon_clinic_visit_v1'.",
    )
    form_label = models.CharField(
        max_length=200,
        help_text="Human-readable name, e.g. 'Clinic Visit (KF-02)'.",
    )
    partner = models.ForeignKey(
        'partners.Partner',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='kobo_forms',
        help_text='Null = cross-partner form.',
    )
    kobo_asset_uid = models.CharField(
        max_length=80, blank=True,
        help_text="KoboToolbox asset UID. Mirrors KOBO_ASSET_UID_* env vars.",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['form_slug']
        verbose_name = 'Kobo Form Mapping'
        verbose_name_plural = 'Kobo Form Mappings'

    def __str__(self):
        return f'{self.form_slug} — {self.form_label}'


class IndicatorTarget(models.Model):
    """
    One target per (partner, activity, indicator). IndicatorTargets are
    seeded by migration 0004_load_target_fixtures and edited via the
    Target Config screen (/admin/targets) by Developer + Supervisor +
    Org Lead (the latter restricted to their own partner).

    Notes on the data model:

      objective_number=0 is reserved for "Overall" indicators that don't
      fit under any SIDA objective (e.g. PHD's "11 brothels covered").
      The UI renders these above Objective 1, not inside it.

      Bandhu has Objectives 1, 2, 4 — never 3. objective_number is just
      an integer, no constraint that it is sequential or in any
      pre-defined set.

      target_value is nullable. Null renders as "Not Set" in the UI
      (orange pill); a zero value would mean "the project really targets
      zero of this thing" and must be displayed as 0, not as Not Set.

      unique_together on (partner, activity_code, indicator_label) lets
      a single activity expand into multiple sub-indicator rows — e.g.
      PHD 1.5 has 5 rows (one per commodity type) with distinct
      indicator_labels.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    partner = models.ForeignKey(
        'partners.Partner',
        on_delete=models.PROTECT,
        related_name='indicator_targets',
    )

    objective_number = models.PositiveSmallIntegerField(
        default=1,
        help_text='SIDA objective number. 0 = Overall (renders above Obj 1).',
    )
    activity_code = models.CharField(
        max_length=10, db_index=True,
        help_text="Short activity ref, e.g. '1.1' or '1.5a' for sub-rows.",
    )
    activity_label = models.CharField(max_length=400)

    indicator_label = models.CharField(max_length=600)

    target_value = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        help_text='Numeric target. Null = "Not Set" — display orange pill.',
    )

    # Animesh's spec: partner-defined monthly splits, NOT evenly divided.
    # Stored as a list of {"month": "YYYY-MM", "target": <number>} entries.
    # Example for Bandhu indicator with 4,000 total: [
    #   {"month": "2026-06", "target": 200},
    #   {"month": "2026-07", "target": 2000},
    #   {"month": "2026-08", "target": 1000},
    #   {"month": "2026-09", "target": 500},
    #   {"month": "2026-10", "target": 300}
    # ]
    # Frontend renders both Monthly Achievement (this month's captured /
    # this month's target) and Overall Achievement (total captured / total
    # target) side-by-side.
    monthly_targets = models.JSONField(
        default=list, blank=True,
        help_text='Partner-defined monthly splits — list of {month, target}.',
    )

    unit = models.CharField(
        max_length=50, default='count',
        help_text="e.g. 'individuals', 'sessions', 'boxes', 'pcs', 'meetings'.",
    )

    source_form = models.ForeignKey(
        'indicators.KoboFormMapping',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='indicators',
        help_text='Which Kobo form generates this indicator. Filled at workshop.',
    )

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    class Meta:
        ordering = ['partner__code', 'objective_number', 'activity_code']
        unique_together = [('partner', 'activity_code', 'indicator_label')]
        verbose_name = 'Indicator Target'
        verbose_name_plural = 'Indicator Targets'

    def __str__(self):
        return f'[{self.partner.code}] {self.activity_code} — {self.indicator_label[:60]}'
