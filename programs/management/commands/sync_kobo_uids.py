"""Fill in this installation's KoboToolbox asset UIDs, automatically.

Why this exists
---------------
When the forms are deployed in a different KoboToolbox account, every asset
UID changes. Three things need the new UIDs: the system_ref write-back, the
two lookup CSV exporters, and the reconciliation check.

Step 9e of the setup guide explains how to type them into the database by
hand. This command does the same job without the typing, and without the
chance of pasting the wrong UID against the wrong form.

It works because the form id lives inside the XLSForm and survives being
imported into another account. So the command reads every survey on YOUR
account, reads each one's form id, and matches it to the form the system
expects.

Usage
-----
    python manage.py sync_kobo_uids            # dry run, changes nothing
    python manage.py sync_kobo_uids --apply    # writes the UIDs

Needs KOBO_API_TOKEN (or KOBO_TOKEN) set to YOUR account's token, which is in
your KoboToolbox account settings.
"""
import os

from django.core.management.base import BaseCommand

from indicators.models import KoboFormMapping
from programs.kobo_assets import _id_string, _survey_assets

# Human label for the report, so a mis-match is obvious at a glance.
LABELS = {
    'ciprb_fistula_questions_v1':        'CIPRB-1  Fistula Question Bank',
    'ciprb_fistula_campaign_v1':         'CIPRB-1b Fistula Campaign',
    'ciprb_mpdsr_community_maternal_v1': 'CIPRB-2  MPDSR Community Maternal',
    'ciprb_mpdsr_community_neonatal_v1': 'CIPRB-3  MPDSR Community Neonatal',
    'ciprb_mpdsr_facility_maternal_v1':  'CIPRB-4  MPDSR Facility Maternal',
    'ciprb_mpdsr_facility_neonatal_v1':  'CIPRB-5  MPDSR Facility Neonatal',
    'ciprb_social_autopsy_v1':           'CIPRB-6  Social Autopsy',
    'ciprb_notification_slip_01_v1':     'CIPRB-7  Notification Slip 01',
    'ciprb_notification_slip_02_v1':     'CIPRB-8  Notification Slip 02',
    'ciprb_near_miss_v1':                'CIPRB-9  Maternal Near Miss',
    'ciprb_mpdsr_response_plan_v1':      'CIPRB-10 MPDSR Response Plan',
    'ciprb_safe_surgery_v1':             'CIPRB-11 Safe Surgery Checklist',
    'ciprb_baseline_fsw_v1':             'Baseline Survey, FSW',
    'ciprb_baseline_hijra_v1':           'Baseline Survey, Hijra',
}


class Command(BaseCommand):
    help = ('Read your KoboToolbox account and fill in each form\'s asset UID. '
            'Dry run unless --apply is given.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the UIDs. Without this the command only reports.')

    def handle(self, *args, **opts):
        token = (os.environ.get('KOBO_API_TOKEN', '')
                 or os.environ.get('KOBO_TOKEN', '')).strip()
        if not token:
            self.stderr.write(
                'KOBO_API_TOKEN is not set. Put your own KoboToolbox API token '
                'in .env, then run this again.')
            return

        self.stdout.write('Reading your KoboToolbox account...')
        try:
            assets = _survey_assets(token)
        except Exception as exc:  # noqa: BLE001
            self.stderr.write('Could not reach KoboToolbox: %s' % exc)
            self.stderr.write('Check the token and that the server can reach '
                              'kf.kobotoolbox.org.')
            return
        self.stdout.write('  %d surveys found on the account\n' % len(assets))

        # form id -> uid, for every survey on the account.
        self.stdout.write('Reading each form\'s id (this takes a moment)...')
        by_form_id = {}
        for a in assets:
            fid = _id_string(a['uid'], token)
            if fid:
                by_form_id.setdefault(fid, []).append(a)

        # Iterate the forms the SYSTEM needs, not the rows that happen to
        # exist. Two of them, the fistula campaign and safe surgery, have no
        # registry row seeded, and without one they would silently keep using
        # the original account's UID.
        existing = {r.form_slug: r for r in
                    KoboFormMapping.objects.filter(form_slug__in=LABELS)}

        self.stdout.write('')
        self.stdout.write('  %-34s %-24s %s' % ('FORM', 'UID FOUND', 'ACTION'))
        self.stdout.write('  ' + '-' * 86)

        to_write, missing, ambiguous, unchanged = [], [], [], 0
        for slug in sorted(LABELS, key=lambda s: LABELS[s]):
            label = LABELS[slug]
            row = existing.get(slug)
            found = by_form_id.get(slug, [])

            if not found:
                missing.append((slug, label))
                self.stdout.write('  %-34s %-24s %s'
                                  % (label[:34], '-', 'NOT FOUND on your account'))
                continue
            if len(found) > 1:
                ambiguous.append((slug, label, [a['uid'] for a in found]))
                self.stdout.write(
                    '  %-34s %-24s %s'
                    % (label[:34], found[0]['uid'],
                       'SKIPPED, %d forms share this id' % len(found)))
                continue

            uid = found[0]['uid']
            if row is None:
                to_write.append((slug, label, uid))
                self.stdout.write('  %-34s %-24s %s'
                                  % (label[:34], uid, 'will add, no registry row yet'))
            elif row.kobo_asset_uid == uid:
                unchanged += 1
                self.stdout.write('  %-34s %-24s %s' % (label[:34], uid, 'already correct'))
            else:
                to_write.append((slug, label, uid))
                was = row.kobo_asset_uid or '(blank)'
                self.stdout.write('  %-34s %-24s %s'
                                  % (label[:34], uid, 'will replace ' + was))

        self.stdout.write('')
        self.stdout.write('  to update: %d   already correct: %d   not found: %d   ambiguous: %d'
                          % (len(to_write), unchanged, len(missing), len(ambiguous)))

        if missing:
            self.stdout.write('')
            self.stdout.write('  Not found on your account:')
            for slug, label in missing:
                self.stdout.write('    %s  (%s)' % (label, slug))
            self.stdout.write('  Deploy these forms first, then run this again. '
                              'Do not edit the settings sheet in the Excel file, '
                              'because the form id in it is what this matches on.')

        if ambiguous:
            self.stdout.write('')
            self.stdout.write('  More than one form shares the same id. Delete the '
                              'duplicates in KoboToolbox, then run this again:')
            for slug, label, uids in ambiguous:
                self.stdout.write('    %s -> %s' % (label, ', '.join(uids)))

        if not opts['apply']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Dry run. Nothing was changed. Re-run with --apply to write these UIDs.'))
            return

        for slug, label, uid in to_write:
            KoboFormMapping.objects.update_or_create(
                form_slug=slug,
                defaults={'kobo_asset_uid': uid, 'form_label': label},
            )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Written. %d form(s) updated.' % len(to_write)))
        if missing or ambiguous:
            self.stdout.write(self.style.WARNING(
                'Some forms were skipped, see above. Fix those and run this again.'))
        else:
            self.stdout.write('All forms matched. The write-back, the lookup files '
                              'and the reconciliation check now point at your account.')
