"""
Referral with outcome tracking — addresses the UNFPA gap flagged by
Dr. Rokhsana Yasmin: "no referral follow-up and service outcome tracking
for HIV, STI, GBV, MH, SRHR referrals to government facilities."

Every referral has an outcome field that must be updated when the client
returns or is followed up. Dashboard shows referral completion rate per
type per centre per month — feeds indicators I_BND_1_7 and I_PHD_1_6.
"""
from django.db import models
from .._base_choices import ORG_CHOICES
from ._base import SubmissionBase


class Referral(SubmissionBase):
    # Referral types matching PHD / Bandhu programme needs
    HIV = 'hiv'
    STI_KP = 'sti_kp'
    STI_PARTNER = 'sti_partner'
    ART = 'art'
    TB = 'tb'
    GBV = 'gbv'
    MENTAL_HEALTH = 'mental_health'
    SRHR = 'srhr'
    FP = 'fp'
    GENERAL_HEALTH = 'general_health'
    HEP_C = 'hep_c'
    LEGAL = 'legal'
    SHELTER = 'shelter'
    CHILD = 'child'
    MATERNAL = 'maternal'
    DIABETIC = 'diabetic'
    OTHER = 'other'
    REFERRAL_TYPE_CHOICES = [
        (ART, 'ART Enrollment'),
        (HIV, 'HIV Testing'),
        (STI_KP, 'STI (KP)'),
        (STI_PARTNER, 'STI (Partner)'),
        (TB, 'TB'),
        (GBV, 'GBV Services'),
        (MENTAL_HEALTH, 'Mental Health'),
        (SRHR, 'SRHR'),
        (FP, 'Family Planning'),
        (GENERAL_HEALTH, 'General Health'),
        (HEP_C, 'Hepatitis C'),
        (LEGAL, 'Legal Services'),
        (SHELTER, 'Shelter'),
        (CHILD, 'Child Health'),
        (MATERNAL, 'Maternal Health'),
        (DIABETIC, 'Diabetic'),
        (OTHER, 'Other'),
    ]

    # Outcome — the tracking field UNFPA flagged as missing
    PENDING = 'pending'
    LINKED = 'linked'
    COMPLETED = 'completed'
    LOST = 'lost_to_follow_up'
    REFUSED = 'refused'
    OUTCOME_CHOICES = [
        (PENDING, 'Pending — awaiting follow-up'),
        (LINKED, 'Linked — client reached facility'),
        (COMPLETED, 'Completed — treatment/service received'),
        (LOST, 'Lost to Follow-Up'),
        (REFUSED, 'Refused by client'),
    ]

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter', on_delete=models.PROTECT, related_name='referrals'
    )
    client = models.ForeignKey(
        'programs.Client', on_delete=models.PROTECT, related_name='referrals'
    )

    referral_date = models.DateField(db_index=True)
    referral_type = models.CharField(max_length=30, choices=REFERRAL_TYPE_CHOICES, db_index=True)
    referral_reason = models.TextField(blank=True)
    referred_to = models.CharField(max_length=300, blank=True)
    referred_by_name = models.CharField(max_length=200, blank=True)
    referred_by_designation = models.CharField(max_length=200, blank=True)

    follow_up_date = models.DateField(null=True, blank=True)

    # Outcome tracking — updated when client is followed up
    outcome = models.CharField(
        max_length=30, choices=OUTCOME_CHOICES, default=PENDING, db_index=True
    )
    outcome_date = models.DateField(null=True, blank=True)
    outcome_notes = models.TextField(blank=True)
    outcome_updated_by = models.ForeignKey(
        'accounts.User',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='referral_outcomes_updated',
    )

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-referral_date']

    def __str__(self):
        return f'Referral {self.referral_type} — {self.referral_date} ({self.outcome})'

    @property
    def is_overdue(self):
        """Flag if follow_up_date has passed and outcome is still pending."""
        if self.outcome != self.PENDING:
            return False
        if not self.follow_up_date:
            return False
        from django.utils import timezone
        return self.follow_up_date < timezone.now().date()
