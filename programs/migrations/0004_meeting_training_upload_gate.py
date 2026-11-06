"""
Step 5 — mandatory upload gate for CoordMeeting and TrainingEvent.

Adds the following fields to both models:
  - <report file>     mandatory at model.clean() + serializer.validate_
                      level. DB schema permits empty string so existing
                      rows (if any) survive; new writes must attach a file.
  - photo             optional ImageField, 2 MiB cap enforced via
                      validate_photo_size() (model) + serializer.
  - call_up_letter    optional FileField.

The report file is enforced at every layer that accepts data:
  - model.clean()                 raises ValidationError on save without file
  - serializer.validate_*         returns 400 on POST/PATCH without file
  - frontend submit button        disabled until a file is attached

This migration intentionally adds the FileField with no `default=`. On a
fresh database (production state today — zero rows in CoordMeeting +
TrainingEvent), no existing-row backfill is needed. The model-level
blank=False enforces the gate at validation time, not at the schema
level — that way Django doesn't reject the migration and existing-row
hypothetical edge cases don't crash.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('programs', '0003_alter_adrrecord_organisation_and_more'),
    ]

    operations = [
        # ── CoordMeeting ────────────────────────────────────────────────
        migrations.AddField(
            model_name='coordmeeting',
            name='meeting_notes',
            field=models.FileField(
                default='', upload_to='coord_meetings/notes/%Y/%m/',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='coordmeeting',
            name='photo',
            field=models.ImageField(
                blank=True, null=True,
                upload_to='coord_meetings/photos/%Y/%m/',
            ),
        ),
        migrations.AddField(
            model_name='coordmeeting',
            name='call_up_letter',
            field=models.FileField(
                blank=True, null=True,
                upload_to='coord_meetings/call_up/%Y/%m/',
            ),
        ),

        # ── TrainingEvent ───────────────────────────────────────────────
        migrations.AddField(
            model_name='trainingevent',
            name='report_file',
            field=models.FileField(
                default='', upload_to='training_events/reports/%Y/%m/',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='trainingevent',
            name='photo',
            field=models.ImageField(
                blank=True, null=True,
                upload_to='training_events/photos/%Y/%m/',
            ),
        ),
        migrations.AddField(
            model_name='trainingevent',
            name='call_up_letter',
            field=models.FileField(
                blank=True, null=True,
                upload_to='training_events/call_up/%Y/%m/',
            ),
        ),
    ]
