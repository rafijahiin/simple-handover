# -*- coding: utf-8 -*-
"""
Export the baseline respondent dedup CSVs (one per population) attached to the
Kobo forms as media. The form's `pulldata('respondents_<pop>','serial','serial',
NORM_SERIAL)=''` constraint blocks re-entering a questionnaire serial that is
already on file. Serials are stored UPPERCASED to match the form's XPath
translate()-based normalisation. Re-run + re-upload periodically to keep the
duplicate-block current (same lag pattern as export_phd_clients.py).

Run:
    python manage.py export_baseline_respondents
"""
import csv
import os

from django.core.management.base import BaseCommand

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.normpath(os.path.join(HERE, '..', '..', '..', '..', 'koboforms_baseline'))


class Command(BaseCommand):
    help = 'Export respondents_hijra.csv / respondents_fsw.csv for the baseline pulldata dedup.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', default=OUTDIR)

    def handle(self, *args, **opts):
        from baseline.models import BaselineResponse
        out = opts['output_dir']
        os.makedirs(out, exist_ok=True)
        for pop, fname in (('hijra', 'respondents_hijra.csv'),
                           ('fsw', 'respondents_fsw.csv')):
            serials = (BaselineResponse.objects
                       .filter(population=pop)
                       .exclude(serial='')
                       .values_list('serial', flat=True))
            path = os.path.join(out, fname)
            n = 0
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['serial'])
                seen = set()
                for s in serials:
                    key = (s or '').strip().upper()
                    if key and key not in seen:
                        seen.add(key)
                        w.writerow([key])
                        n += 1
            self.stdout.write(self.style.SUCCESS(f'  {fname}: {n} serial(s)'))
        self.stdout.write(f'Written to {os.path.abspath(out)}/')
