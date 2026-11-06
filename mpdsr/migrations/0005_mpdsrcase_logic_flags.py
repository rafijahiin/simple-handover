# Generated for MPDSR QA-gate logic-flag validator.
#
# Adds the JSON list `logic_flags` to MPDSRCase. Populated at MPDSRCase
# create time by mpdsr.validators.compute_logic_flags. Advisory amber
# badge in the manager approval queue — does not alter approval rules.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mpdsr", "0004_mpdsractionplansummary_mpdsrdistrictdenominator_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="mpdsrcase",
            name="logic_flags",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
