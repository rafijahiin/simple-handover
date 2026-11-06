"""
GBV Corner Establishment Record.
Source: gbv corner establishment database.docx

Fields mirror the source register exactly:
  Place of establishment | Date of establishment |
  Furniture [Add numbers] | Essential equipment/Commodities [Add numbers] |
  Fully functional [Yes/No]

Feeds indicator SL16: # of corners at DH and UHCs fully equipped (target 44).
Counted as: rows where fully_functional=True.
"""
import uuid
from django.db import models
from .._base_choices import ORG_CHOICES
from ._base import SubmissionBase


class GBVCornerRecord(SubmissionBase):
    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    center = models.ForeignKey(
        'programs.ServiceCenter',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='gbv_corners',
    )
    place_of_establishment = models.CharField(max_length=300)
    date_of_establishment = models.DateField()
    furniture_count = models.PositiveIntegerField(default=0)
    equipment_count = models.PositiveIntegerField(default=0)
    fully_functional = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date_of_establishment']

    def __str__(self):
        status = 'functional' if self.fully_functional else 'not functional'
        return f'GBV Corner — {self.place_of_establishment} ({status})'
