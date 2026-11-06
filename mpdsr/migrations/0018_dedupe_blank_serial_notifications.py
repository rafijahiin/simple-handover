# -*- coding: utf-8 -*-
"""Remove the duplicate notifications created while case_serial joined the identity.

case_serial used to sit in `defaults`, so the upsert key was (slip_variant,
district, date_of_death, deceased_name) and two deaths sharing a mother and a
date merged into one row. Adding case_serial to the key fixed that, but slips
submitted WITHOUT a serial then resolved to a new 'kobo:<id>' key that did not
match the legacy row's empty case_serial — so re-delivering those slips created
a second row for the same death.

The handler now matches the legacy blank row as well, so no new duplicates can
appear. This clears the ones already written: where a 'kobo:<id>' row sits
beside a blank-serial row for the SAME slip, district, date and name, the two
are the same submission. Keep the older row (it carries the approval decision a
reviewer already made) and give it the new identity so future deliveries match.
"""
from django.db import migrations


def merge_blank_serial_duplicates(apps, schema_editor):
    Notification = apps.get_model('mpdsr', 'MPDSRDeathNotification')

    groups = {}
    for n in Notification.objects.all():
        key = (n.slip_variant, n.district, n.date_of_death, n.deceased_name)
        groups.setdefault(key, []).append(n)

    for key, rows in groups.items():
        if len(rows) < 2:
            continue
        blanks = [r for r in rows if not (r.case_serial or '').strip()]
        kobos = [r for r in rows if (r.case_serial or '').startswith('kobo:')]
        # Only touch the blank/kobo pairing. Rows with real, DIFFERENT serials
        # are genuinely different deaths (a maternal death and a stillbirth for
        # the same mother) and must both survive.
        if not blanks or not kobos:
            continue
        keep = sorted(blanks, key=lambda r: r.pk)[0]
        for dup in kobos:
            if dup.pk == keep.pk:
                continue
            if not (keep.case_serial or '').startswith('kobo:'):
                keep.case_serial = dup.case_serial
            dup.delete()
        keep.save(update_fields=['case_serial'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('mpdsr', '0017_mpdsrcase_raw_payload'),
    ]

    operations = [
        migrations.RunPython(merge_blank_serial_duplicates, noop),
    ]
