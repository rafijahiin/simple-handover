"""
Add approval workflow fields to Client (KF-01 registrations now require
manager approval before becoming active in the dashboard).
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('programs', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='approval_status',
            field=models.CharField(
                choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')],
                db_index=True,
                default='APPROVED',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='approved_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='rejected_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='client',
            name='kobo_submission_id',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='client',
            name='submitted_by_kobo_user',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='client',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='raw_payload',
            field=models.JSONField(default=dict),
        ),
    ]
