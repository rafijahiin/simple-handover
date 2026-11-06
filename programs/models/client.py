"""
Client — the master client registry (Mother List).
Every service event links back to a Client record.
KF-01 registrations go through the manager approval workflow before
becoming active in the dashboard.
"""
import uuid
from django.db import models
from django.conf import settings
from .._base_choices import ORG_CHOICES
from ._base import TimestampedModel
from .gbv import EncryptedCharField  # Fernet at rest for client PII


class Client(TimestampedModel):
    # --- Gender ---
    MALE = '01'
    FEMALE = '02'
    TRANSGENDER = '03'
    OTHER_GENDER = '04'
    GENDER_CHOICES = [
        (MALE, 'Male'),
        (FEMALE, 'Female'),
        (TRANSGENDER, 'Transgender'),
        (OTHER_GENDER, 'Other'),
    ]

    # --- Target Group (Key Population) ---
    MSM = '01'
    MSW = '02'
    TG_KP = '03'
    OTHERS_KP = '04'
    FSW = '05'
    PWID = '06'
    TG_CHOICES = [
        (MSM, 'MSM'),
        (MSW, 'MSW / Kothi'),
        (TG_KP, 'Transgender'),
        (OTHERS_KP, 'Others'),
        (FSW, 'FSW'),
        (PWID, 'PWID'),
    ]

    # --- Client Status ---
    ACTIVE = '1'
    JAILED = '2'
    RELOCATED = '3'
    OTHER_STATUS = '4'
    DECEASED = '5'
    NOT_FOUND = '6'
    STATUS_CHOICES = [
        (ACTIVE, 'Active'),
        (JAILED, 'Jailed'),
        (RELOCATED, 'Relocated'),
        (OTHER_STATUS, 'Other'),
        (DECEASED, 'Deceased'),
        (NOT_FOUND, 'Not Found'),
    ]

    # ── Approval workflow ──────────────────────────────────────────────────
    PENDING  = 'PENDING'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'
    APPROVAL_CHOICES = [
        (PENDING,  'Pending'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    ]
    approval_status = models.CharField(
        max_length=10, choices=APPROVAL_CHOICES, default=APPROVED, db_index=True
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    approved_at  = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True)
    # ── KoboToolbox provenance ─────────────────────────────────────────────
    kobo_submission_id    = models.CharField(max_length=100, unique=True, null=True, blank=True)
    submitted_by_kobo_user = models.CharField(max_length=100, blank=True)
    latitude  = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    raw_payload = models.JSONField(default=dict)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter',
        on_delete=models.PROTECT,
        related_name='clients',
    )
    client_id = models.CharField(max_length=50, unique=True, db_index=True)
    # name stays plaintext: it's a lookup key (admin search_fields + the
    # export .exclude(name='Unknown') filter). The parents' names + address
    # are NOT keys, so they are Fernet-encrypted at rest.
    name = models.CharField(max_length=200)
    mother_name = EncryptedCharField(blank=True)
    father_name = EncryptedCharField(blank=True)

    # Demographics
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=2, choices=GENDER_CHOICES, blank=True)
    target_group_code = models.CharField(max_length=2, choices=TG_CHOICES, blank=True)

    # Location
    current_address = EncryptedCharField(blank=True)   # Fernet at rest
    spot_name = models.CharField(max_length=200, blank=True)

    # Socioeconomic. Kobo select_one values are short codes ('1'..'5'), but
    # the Mother List `ml_occupation` field comes through as free text
    # ('Sex Worker', 'Family income', etc.), so occupation_code holds the
    # label, not a 1-char code. Widened generously so a longer answer can
    # never overflow the column and 500 the webhook (the previous max_length=1
    # silently dropped every Bandhu registration with a typed occupation).
    marital_status = models.CharField(max_length=32, blank=True)
    education_level = models.CharField(max_length=32, blank=True)
    occupation_code = models.CharField(max_length=100, blank=True)

    # FSW-specific
    years_in_profession = models.PositiveSmallIntegerField(null=True, blank=True)
    avg_clients_per_day = models.PositiveSmallIntegerField(null=True, blank=True)
    children_under_18 = models.PositiveSmallIntegerField(null=True, blank=True)
    uses_injecting_drugs = models.BooleanField(null=True)
    has_nid = models.BooleanField(null=True)
    uses_fp_method = models.BooleanField(null=True)

    enrolled_date = models.DateField(null=True, blank=True)
    current_status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=ACTIVE)
    telegram_chat_id = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    # Mother List (F-1.1) occupation is now a coded select_one (1-6); legacy
    # rows hold free text. Labels live here so a code never displays as a digit.
    OCCUPATION_LABELS = {
        '1': 'Service / job holder', '2': 'Businessman', '3': 'Student',
        '4': 'Sex work', '5': 'Unemployed', '6': 'Others',
    }

    @property
    def occupation_label(self):
        return self.OCCUPATION_LABELS.get(self.occupation_code, self.occupation_code)

    class Meta:
        ordering = ['-enrolled_date']

    def __str__(self):
        return f'{self.client_id} — {self.name} ({self.organisation})'
