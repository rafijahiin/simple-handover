"""
Add 3 missing fields to ClinicVisit for the PHD Patient Record Register:
  - gbv_screening_done    (GBV Screening column)
  - mh_screening_done     (Mental Health Screening column)
  - referral_gbv          (GBV referral column — distinct from MHPSS referral)

Add GBVCornerRecord model from gbv_corner_establishment_database.docx.
Feeds SL16: # of GBV corners fully equipped (target 44).
"""
import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('programs', '0009_alter_adrrecord_created_at_and_more'),
    ]

    operations = [
        # ── ClinicVisit: 3 new screening / referral fields ─────────────────────
        migrations.AddField(
            model_name='clinicvisit',
            name='gbv_screening_done',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='clinicvisit',
            name='mh_screening_done',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='clinicvisit',
            name='referral_gbv',
            field=models.BooleanField(default=False),
        ),

        # ── GBVCornerRecord ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='GBVCornerRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('kobo_submission_id', models.CharField(
                    blank=True, db_index=True, max_length=100)),
                ('submitted_by_kobo_user', models.CharField(
                    blank=True, max_length=200)),
                ('latitude', models.FloatField(blank=True, null=True)),
                ('longitude', models.FloatField(blank=True, null=True)),
                ('raw_payload', models.JSONField(blank=True, default=dict)),
                ('approval_status', models.CharField(
                    choices=[('PENDING', 'Pending'),
                             ('APPROVED', 'Approved'),
                             ('REJECTED', 'Rejected')],
                    db_index=True, default='PENDING', max_length=10,
                )),
                ('organisation', models.CharField(db_index=True, max_length=20)),
                ('place_of_establishment', models.CharField(max_length=300)),
                ('date_of_establishment', models.DateField()),
                ('furniture_count', models.PositiveIntegerField(default=0)),
                ('equipment_count', models.PositiveIntegerField(default=0)),
                ('fully_functional', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True)),
                ('center', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='gbv_corners',
                    to='programs.servicecenter',
                )),
            ],
            options={'ordering': ['-date_of_establishment']},
        ),
    ]
