"""
Supply chain and facility management models:
  - StockEntry            (Monthly Stock Summary — KF-14)
  - TemperatureLog        (Cold chain monitoring — KF-15)
  - SafetyHygieneKit      (Safety & Hygiene Kit Distribution — KF-12)
  - StoreRequisition      (Store Requisition — KF-22)
"""
import uuid
from django.db import models
from django.conf import settings
from .._base_choices import ORG_CHOICES
from ._base import TimestampedModel, SubmissionBase


class StockEntry(TimestampedModel):
    """
    Monthly stock summary per item per centre.
    Browser-based entry (no GPS required).
    commodity tracking feeds PHD indicators 1.5b/c/d/e (test kits).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    MEDICINE = 'medicine'
    CONTRACEPTIVE = 'contraceptive'
    CONDOM = 'condom'
    TEST_KIT = 'test_kit'
    IPC = 'ipc'
    GBV_DIGNITY = 'gbv_dignity'
    OTHER = 'other'
    CATEGORY_CHOICES = [
        (MEDICINE, 'Medicine'),
        (CONTRACEPTIVE, 'Contraceptive'),
        (CONDOM, 'Condom / Lubricant'),
        (TEST_KIT, 'Test Kit'),
        (IPC, 'IPC / Sterilisation'),
        (GBV_DIGNITY, 'GBV / Dignity Kit'),
        (OTHER, 'Other'),
    ]

    PENDING = 'PENDING'
    APPROVED = 'APPROVED'
    APPROVAL_CHOICES = [(PENDING, 'Pending'), (APPROVED, 'Approved')]

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='stock_entries'
    )

    reporting_month = models.DateField(db_index=True)  # first day of the month
    item_name = models.CharField(max_length=200)
    item_category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default=OTHER)
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    delivery_challan_no = models.CharField(max_length=100, blank=True)

    opening_balance = models.IntegerField(default=0)
    quantity_received = models.IntegerField(default=0)
    quantity_issued = models.IntegerField(default=0)
    quantity_expired_lost = models.IntegerField(default=0)

    # Kobo submission _ids already folded into the running totals above. Field
    # staff submit the same item/centre/month MANY times (per issue, not once
    # monthly), so the webhook ACCUMULATES quantities across submissions rather
    # than overwriting with the last one. This list is the idempotency guard:
    # a replayed/retried submission whose _id is already here is a no-op, so a
    # Kobo retry never double-counts. See programs.webhook._accumulate_stock.
    source_submission_ids = models.JSONField(default=list, blank=True)

    approval_status = models.CharField(max_length=10, choices=APPROVAL_CHOICES, default=PENDING)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-reporting_month', 'item_name']
        unique_together = [('center', 'reporting_month', 'item_name')]

    @property
    def closing_balance(self):
        return self.opening_balance + self.quantity_received - self.quantity_issued - self.quantity_expired_lost

    @property
    def is_low_stock(self):
        """Flag if closing balance < 10% of issued (proxy for low stock alert)."""
        if self.quantity_issued == 0:
            return False
        return self.closing_balance < (self.quantity_issued * 0.1)

    def __str__(self):
        return f'{self.item_name} — {self.center} ({self.reporting_month:%b %Y})'


class TemperatureLog(TimestampedModel):
    """
    Daily cold-chain temperature log.
    is_out_of_range triggers Telegram alert to org manager immediately.
    Normal range: 2–8 °C.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='temperature_logs'
    )

    log_date = models.DateField(db_index=True)
    morning_temp_celsius = models.DecimalField(max_digits=4, decimal_places=1)
    afternoon_temp_celsius = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    recorded_by = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-log_date']
        unique_together = [('center', 'log_date')]

    @property
    def is_out_of_range(self):
        if self.morning_temp_celsius < 2 or self.morning_temp_celsius > 8:
            return True
        if self.afternoon_temp_celsius is not None:
            if self.afternoon_temp_celsius < 2 or self.afternoon_temp_celsius > 8:
                return True
        return False

    def __str__(self):
        return f'Temp {self.log_date} — {self.center} ({self.morning_temp_celsius}°C)'


class SafetyHygieneKit(SubmissionBase):
    """Safety & Hygiene Kit distribution / Service Logbook (KF-12, Bandhu)."""
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='safety_kits'
    )
    client = models.ForeignKey(
        'programs.Client', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='safety_kits'
    )

    distribution_date = models.DateField()
    condom_count = models.PositiveIntegerField(default=0)
    condom_demo = models.BooleanField(default=False)
    awareness_session = models.BooleanField(default=False)
    iec_distributed = models.PositiveIntegerField(default=0)
    clinical_service_provided = models.BooleanField(default=False)
    counselling_provided = models.BooleanField(default=False)
    referral_done = models.BooleanField(default=False)
    group_session = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-distribution_date']

    def __str__(self):
        return f'Hygiene kit {self.distribution_date} ({self.organisation})'


class StoreRequisition(TimestampedModel):
    """Store requisition form (browser-based, no GPS)."""
    PENDING = 'pending'
    FULFILLED = 'fulfilled'
    PARTIAL = 'partial'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (FULFILLED, 'Fulfilled'),
        (PARTIAL, 'Partially Fulfilled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='store_requisitions'
    )

    requisition_date = models.DateField()
    requirement_date = models.DateField(null=True, blank=True)
    requested_by = models.CharField(max_length=200)
    requested_by_designation = models.CharField(max_length=200, blank=True)
    event_name = models.CharField(max_length=300, blank=True)

    # items: [{"item_name": "...", "quantity_requested": N, "quantity_supplied": N}]
    items = models.JSONField(default=list)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    fulfilled_by = models.CharField(max_length=200, blank=True)
    fulfillment_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-requisition_date']
