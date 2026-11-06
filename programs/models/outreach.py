"""
Outreach and community education models:
  - OutreachSession       (Daily Outreach — KF-08)
  - GroupEducationSession (Group Education — KF-10)
"""
from django.db import models
from .._base_choices import ORG_CHOICES
from ._base import SubmissionBase


class OutreachSession(SubmissionBase):
    """
    Daily outreach session submitted by CO / Peer Educator.
    individual_contacts feeds directly into indicator I_BND_1_4B / I_PHD_1_4.

    Audit FIX 7.6 — Outreach Movement Register fields added (out_time,
    return_time, purpose, manager_endorsement). Manager endorsement acts
    as a soft approval gate: rows with manager_endorsement=False stay in
    SubmissionBase PENDING and are not counted toward the indicator until
    the manager flips the flag.
    """

    # Audit FIX 12.3 (Commit 3 also touches this — variant flag) — fixed-site
    # vs mobile camp. Bandhu 1.9 indicator counts mobile-camp variants only.
    FIXED_SITE  = 'fixed_site'
    MOBILE_CAMP = 'mobile_camp'
    SESSION_VARIANT_CHOICES = [
        (FIXED_SITE,  'Fixed Site'),
        (MOBILE_CAMP, 'Mobile Camp'),
    ]

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='outreach_sessions'
    )

    session_date = models.DateField(db_index=True)
    peer_educator_name = models.CharField(max_length=200)
    spot_name = models.CharField(max_length=200, blank=True)

    # ─── Audit FIX 7.6 — Outreach Movement Register fields ─────────────────
    out_time = models.TimeField(null=True, blank=True)
    return_time = models.TimeField(null=True, blank=True)
    purpose = models.TextField(blank=True)
    # Manager endorsement gate. False = stays unapproved; manager flips
    # to True when accepting the outreach record.
    manager_endorsement = models.BooleanField(default=False)

    # Audit FIX 12.3 — fixed-site vs mobile-camp variant.
    session_variant = models.CharField(
        max_length=20, choices=SESSION_VARIANT_CHOICES, default=FIXED_SITE,
        db_index=True,
    )

    individual_contacts = models.PositiveIntegerField(default=0)
    individual_health_edu_count = models.PositiveIntegerField(default=0)
    group_health_edu_count = models.PositiveIntegerField(default=0)
    condoms_distributed_free = models.PositiveIntegerField(default=0)
    lubricants_distributed_free = models.PositiveIntegerField(default=0)
    iec_bcc_materials_distributed = models.PositiveIntegerField(default=0)

    # Session type counts
    hiv_aids_sti_knowledge_sessions = models.PositiveSmallIntegerField(default=0)
    gbv_sessions = models.PositiveSmallIntegerField(default=0)

    # Referrals made during outreach
    referral_mental_health = models.PositiveSmallIntegerField(default=0)
    referral_legal_services = models.PositiveSmallIntegerField(default=0)
    referral_htc_hts = models.PositiveSmallIntegerField(default=0)
    referral_gbv = models.PositiveSmallIntegerField(default=0)
    referral_other = models.PositiveSmallIntegerField(default=0)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-session_date']

    def __str__(self):
        return f'Outreach {self.session_date} — {self.peer_educator_name}'


class GroupEducationSession(SubmissionBase):
    """
    Group education / health awareness session.
    participant_count feeds into I_BND_1_4B (KP reached).
    session count feeds into I_BND_1_4A / I_PHD_1_4.
    """
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='group_edu_sessions'
    )

    session_date = models.DateField(db_index=True)
    spot_name = models.CharField(max_length=200, blank=True)
    facilitator_name = models.CharField(max_length=200, blank=True)
    topic = models.CharField(max_length=300)

    participant_count = models.PositiveIntegerField(default=0)
    male_count = models.PositiveIntegerField(default=0)
    female_count = models.PositiveIntegerField(default=0)
    tg_count = models.PositiveIntegerField(default=0)

    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    materials_distributed = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-session_date']

    def __str__(self):
        return f'Group Ed {self.session_date} — {self.topic[:40]}'


class WellnessLogbookEntry(SubmissionBase):
    """F-01 Wellness Centre Service Logbook — the consolidated per-client, per-day
    service record and the CANONICAL Bandhu service source.

    Bandhu records all per-client services here (they do not file the separate
    F-05/F-06 registers), so as of the 2026-07 MIS review the individual service
    flags below are mapped to columns and READ by the Bandhu service indicators
    (1.2 GBV, 1.3 MHPSS, 1.5a STI, 1.5b HIV, 4.1 IEC). Because F-05/F-06 carry no
    Bandhu rows, counting this logbook is the single source — it does not
    double-count. The full submission is still kept in raw_payload for review."""
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT,
        related_name='wellness_logbook_entries',
    )
    service_date = models.DateField(null=True, blank=True, db_index=True)
    # As-submitted ID kept verbatim for audit; client_id_norm is the DD-NNNN
    # normalised form the indicators/join use (backfilled from centre + serial).
    client_id = models.CharField(max_length=50, blank=True)
    client_id_norm = models.CharField(max_length=50, blank=True, db_index=True)
    tg_code = models.CharField(max_length=10, blank=True)

    # ─── Service flags (F-01 services block) — counted by the Bandhu indicators ──
    sti_screening = models.BooleanField(default=False)   # → 1.5a STI services
    htc = models.BooleanField(default=False)             # → 1.5b HIV testing
    clinical = models.BooleanField(default=False)
    gbv = models.BooleanField(default=False)             # → 1.2 GBV
    mental_health = models.BooleanField(default=False)   # → 1.3 MHPSS
    counseling = models.BooleanField(default=False)
    legal = models.BooleanField(default=False)
    recreation = models.BooleanField(default=False)
    group_edu = models.BooleanField(default=False)
    referral_codes = models.CharField(max_length=100, blank=True)

    # ─── Service counts ──────────────────────────────────────────────────────
    condom = models.PositiveIntegerField(default=0)
    condom_demo = models.PositiveIntegerField(default=0)
    lubricant = models.PositiveIntegerField(default=0)
    awareness = models.PositiveIntegerField(default=0)
    iec = models.PositiveIntegerField(default=0)         # → 4.1 IEC distributed

    class Meta:
        ordering = ['-service_date']
        verbose_name = 'Wellness logbook entry'
        verbose_name_plural = 'Wellness logbook entries'

    def __str__(self):
        return f'F-01 logbook {self.service_date} — {self.client_id}'
