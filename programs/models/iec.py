"""
IEC/SBCC Materials Log (audit FIX 12.2).

Records dissemination of Information-Education-Communication and Social
and Behaviour Change Communication materials — message boards, posters,
signboards, billboards, digital, leaflets. Feeds:

  PHD indicator 3.1a / 3.1b / 3.1c / 3.1d  (message boards / posters /
  signboards / billboards installed)
  Bandhu indicator 4.1                     (IEC / SBCC materials and
                                            multimedia products
                                            developed and disseminated)
  Bandhu indicator 4.3                     (e-billboards / digital
                                            installations)

Each row carries an approval_status that defaults to PENDING (audit FIX
2.7 — only ciprb_baseline records bypass the manager approval queue;
IEC distribution records are not surveillance and must be reviewed).
"""
from django.db import models
from .._base_choices import ORG_CHOICES
from ._base import SubmissionBase


class IECMaterial(SubmissionBase):
    MESSAGE_BOARD = 'message_board'
    POSTER        = 'poster'
    SIGNBOARD     = 'signboard'
    BILLBOARD     = 'billboard'
    DIGITAL       = 'digital'
    LEAFLET       = 'leaflet'
    OTHER         = 'other'
    MATERIAL_TYPE_CHOICES = [
        (MESSAGE_BOARD, 'Message Board'),
        (POSTER,        'Poster'),
        (SIGNBOARD,     'Signboard'),
        (BILLBOARD,     'Billboard'),
        (DIGITAL,       'Digital / E-billboard'),
        (LEAFLET,       'Leaflet / Flyer'),
        (OTHER,         'Other'),
    ]

    partner = models.ForeignKey(
        'partners.Partner',
        on_delete=models.PROTECT,
        related_name='iec_materials',
    )
    center = models.ForeignKey(
        'programs.ServiceCenter',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='iec_materials',
    )

    organisation = models.CharField(max_length=20, choices=ORG_CHOICES, db_index=True)
    material_type = models.CharField(
        max_length=20, choices=MATERIAL_TYPE_CHOICES, db_index=True,
    )
    quantity = models.PositiveIntegerField()
    date_distributed = models.DateField(db_index=True)
    district = models.CharField(max_length=100, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date_distributed']
        indexes = [
            models.Index(fields=['organisation', 'material_type', '-date_distributed']),
        ]

    def __str__(self):
        return f'{self.get_material_type_display()} × {self.quantity} ({self.date_distributed})'
