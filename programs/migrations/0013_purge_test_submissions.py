"""
One-off cleanup: delete the test submissions created while proving the Bandhu
webhook end-to-end. They carry recognisable kobo_submission_id markers
(BNDTEST-*, the direct-webhook run-proof records). One TrainingEvent was
accidentally approved during the finicky Manager-Approvals cleanup and was
inflating indicator 2.2 (Midwives trained = 20) and the "What's being
submitted" tile. This removes them so the pre-launch dashboard is clean.

Safe: only rows whose kobo_submission_id starts with a test prefix are
touched. Idempotent — re-running deletes nothing new.
"""
from django.db import migrations

_TEST_PREFIXES = ('BNDTEST', 'PHDTEST', 'CIPRBTEST', 'TESTONLY')

_MODELS = [
    'ClinicVisit', 'HIVSTITestResult', 'GBVCase', 'IndividualCounselling',
    'Referral', 'OutreachSession', 'MobileHealthCamp', 'TrainingEvent',
    'CoordMeeting', 'IECMaterial', 'HTCCounselling', 'GroupEducationSession',
]


def _forward(apps, schema_editor):
    from django.db.models import Q
    for model_name in _MODELS:
        try:
            Model = apps.get_model('programs', model_name)
        except LookupError:
            continue
        q = Q()
        for pref in _TEST_PREFIXES:
            q |= Q(kobo_submission_id__startswith=pref)
        try:
            Model.objects.filter(q).delete()
        except Exception:
            # field may not exist on a given model — skip quietly
            pass


def _reverse(apps, schema_editor):
    pass  # deletion of test data is not reversible


class Migration(migrations.Migration):

    dependencies = [
        ('programs', '0012_bandhu_centres_reconcile'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
