from django.db import migrations


class Migration(migrations.Migration):
    """Add SUBMISSION_GAP to AlertType choices (no schema change, choices are Python-level)."""

    dependencies = [
        ('tracker', '0001_initial'),
    ]

    operations = [
        # No DB schema change — choices are stored as varchar; this migration
        # just records the Python-level change so Django's migration state matches.
    ]
