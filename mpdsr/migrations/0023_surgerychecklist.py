# Safe Surgery Checklist (CIPRB-11) — new model only.
#
# makemigrations wanted to bundle two UNRELATED pre-existing drifts into this
# file (a StockEntry.source_submission_ids removal in `programs`, and an
# MPDSRAction.section choices-label tweak). Those predate this work and are left
# as-is so this migration is purely additive: it creates SurgeryChecklist and
# nothing else.
import django.db.models.deletion
import fistula.encryption
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mpdsr", "0022_maternalnearmisscase_system_ref_mpdsrcase_system_ref_and_more"),
        ("programs", "0026_stockentry_source_submission_ids"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SurgeryChecklist",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "organisation",
                    models.CharField(db_index=True, default="CIPRB", max_length=20),
                ),
                ("district", models.CharField(db_index=True, max_length=100)),
                ("upazila", models.CharField(blank=True, max_length=100)),
                ("union", models.CharField(blank=True, max_length=100)),
                ("village", models.CharField(blank=True, max_length=100)),
                ("facility_name", models.CharField(blank=True, max_length=200)),
                ("ward_unit", models.CharField(blank=True, max_length=120)),
                ("operation_name", models.CharField(max_length=300)),
                (
                    "op_datetime",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("collection_date", models.DateField(blank=True, null=True)),
                ("surgeon", models.CharField(blank=True, max_length=200)),
                ("anesthesiologist", models.CharField(blank=True, max_length=200)),
                ("patient_name", fistula.encryption.EncryptedCharField(blank=True)),
                ("signin_total", models.PositiveSmallIntegerField(default=0)),
                ("signin_done", models.PositiveSmallIntegerField(default=0)),
                ("signin_complete", models.BooleanField(db_index=True, default=False)),
                ("timeout_total", models.PositiveSmallIntegerField(default=0)),
                ("timeout_done", models.PositiveSmallIntegerField(default=0)),
                ("timeout_complete", models.BooleanField(db_index=True, default=False)),
                ("signout_total", models.PositiveSmallIntegerField(default=0)),
                ("signout_done", models.PositiveSmallIntegerField(default=0)),
                ("signout_complete", models.BooleanField(db_index=True, default=False)),
                ("fully_compliant", models.BooleanField(db_index=True, default=False)),
                (
                    "latitude",
                    models.DecimalField(
                        blank=True, decimal_places=7, max_digits=10, null=True
                    ),
                ),
                (
                    "longitude",
                    models.DecimalField(
                        blank=True, decimal_places=7, max_digits=10, null=True
                    ),
                ),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("enumerator_name", fistula.encryption.EncryptedCharField(blank=True)),
                (
                    "enumerator_mobile",
                    fistula.encryption.EncryptedCharField(blank=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approval_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                        ],
                        db_index=True,
                        default="APPROVED",
                        max_length=20,
                    ),
                ),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_reason", models.TextField(blank=True, default="")),
                (
                    "kobo_submission_id",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=100
                    ),
                ),
                (
                    "submitted_by_kobo_user",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                (
                    "system_ref",
                    models.CharField(
                        blank=True, db_index=True, max_length=24, null=True, unique=True
                    ),
                ),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "center",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="programs.servicecenter",
                    ),
                ),
            ],
            options={
                "verbose_name": "Safe Surgery Checklist",
                "verbose_name_plural": "Safe Surgery Checklists",
                "ordering": ["-op_datetime", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["organisation", "op_datetime"],
                        name="mpdsr_surge_organis_d145b9_idx",
                    ),
                    models.Index(
                        fields=["district", "fully_compliant"],
                        name="mpdsr_surge_distric_8631a4_idx",
                    ),
                ],
            },
        ),
    ]
