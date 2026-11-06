"""Backfill sa_death_kind on Social Autopsy cases already in the database.

Ingest used to collapse sa_death_type 2 (neonatal) and 3 (stillbirth) into
DeathType.PERINATAL, so a reviewed stillbirth was indistinguishable from a
reviewed neonatal death and appeared nowhere on the dashboard. The handler now
records the reviewer's actual answer; this replays it for the rows written
before that. Every Social Autopsy case keeps its raw Kobo payload, so nothing
has to be re-fetched.
"""

from django.db import migrations

_KIND = {'1': 'maternal', '2': 'neonatal', '3': 'stillbirth'}


def backfill(apps, schema_editor):
    MPDSRCase = apps.get_model('mpdsr', 'MPDSRCase')
    updated = []
    for case in MPDSRCase.objects.filter(sub_form_type='sa_md', sa_death_kind=''):
        payload = case.raw_payload or {}
        if not isinstance(payload, dict):
            continue
        # Kobo may nest answers under a group prefix, so match on the leaf name.
        raw = ''
        for key, value in payload.items():
            if str(key).split('/')[-1] == 'sa_death_type' and value not in (None, ''):
                raw = str(value).strip()
                break
        kind = _KIND.get(raw)
        if not kind:
            continue
        case.sa_death_kind = kind
        updated.append(case)
    if updated:
        MPDSRCase.objects.bulk_update(updated, ['sa_death_kind'], batch_size=200)


def unbackfill(apps, schema_editor):
    MPDSRCase = apps.get_model('mpdsr', 'MPDSRCase')
    MPDSRCase.objects.filter(sub_form_type='sa_md').update(sa_death_kind='')


class Migration(migrations.Migration):

    dependencies = [
        ('mpdsr', '0020_add_sa_death_kind'),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
