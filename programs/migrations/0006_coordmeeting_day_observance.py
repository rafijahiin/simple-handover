"""
Audit FIX 12.4 — add `day_observance` choice to CoordMeeting.meeting_type.

Lets the Meeting form attribute Bandhu indicator 2.6 ("Support day
observances — World AIDS Day, Human Rights Day, etc.") to its own
meeting type instead of forcing those events into Internal or Multi.
The choices are validated on save() — adding a new choice is a no-op
at the database column level (still varchar(20)) but Django still
emits a state-only AlterField operation so future migration history
records the choice change.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('programs', '0005_alter_coordmeeting_photo_alter_trainingevent_photo'),
    ]

    operations = [
        migrations.AlterField(
            model_name='coordmeeting',
            name='meeting_type',
            field=models.CharField(
                choices=[
                    ('GOB',            'GOB / Health Staff'),
                    ('CBO',            'CBO / Community Network'),
                    ('internal',       'Internal'),
                    ('multi',          'Multi-Stakeholder'),
                    ('day_observance', 'Day Observance / Awareness Event'),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
    ]
