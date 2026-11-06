# -*- coding: utf-8 -*-
"""Regenerate baseline/form_schema.json from the DEPLOYED Kobo forms.

schema.py turns coded answers into readable text on the verification card and in
the insights aggregation. When a field is missing from the schema, humanize()
falls back to the raw key, so a CIPRB reviewer sees `q7_14_a_perp_12mo` and `1`
instead of the question and the answer.

It used to be built by a loose script reading `_baseline_schema.json`, a local
snapshot taken by hand. Snapshots rot: by 2026-07-17 the committed schema was
missing 66 FSW and 71 Hijra live questions — including the ENTIRE `*_perp_12mo`
violence battery (26 FSW / 24 Hijra select_multiples) added by the NK redeploys.
That was live, user-visible degradation on the most sensitive module in the study.

This reads the deployed asset itself — the form respondents actually answered —
so the schema cannot lag the questionnaire. Run it after every form deploy:

    railway run python manage.py build_form_schema

`test_schema_covers_every_field_on_the_form` fails if the committed schema drifts
from the forms the builders produce, so a forgotten run breaks CI rather than
quietly degrading the review card.
"""
import json
import os
import re

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

ASSETS = {
    'hijra': 'aBT7aCL9p4FGcW4WwXZcr6',
    'fsw': 'aVsJ7VJ35k8GshpQpnXygC',
}
API = 'https://kf.kobotoolbox.org/api/v2/assets/{uid}/?format=json'
OUT = os.path.join(settings.BASE_DIR, 'baseline', 'form_schema.json')

# Types that carry no answer to render.
_SKIP_TYPES = {'note', 'begin_group', 'end_group', 'begin_repeat', 'end_repeat',
               'start', 'end', 'today', 'deviceid', 'phonenumber', 'username',
               'audit'}


def _clip(s, n):
    return (s or '').strip()[:n]


def _first(label):
    """Kobo stores bilingual labels as [English, Bangla]."""
    if isinstance(label, list):
        return label[0] if label else ''
    return label or ''


def _section_of(name):
    n = (name or '').lower()
    if n in ('district', 'site_code') or n.startswith(('interview_', 'consent',
                                                       's1', 's2', 's3', 's4')):
        return 'Screening & identification'
    m = re.match(r'([a-z])', n)
    return {
        'a': 'A · Respondent profile',
        'b': 'B · Livelihood & household',
        'c': 'C · Sexual & reproductive health',
        'd': 'D · Health services & access',
        'e': 'E · Rights, violence & wellbeing',
        'f': 'F · Knowledge & awareness',
        'g': 'G · Additional',
    }.get(m.group(1) if m else '', 'Other')


class Command(BaseCommand):
    help = 'Rebuild baseline/form_schema.json from the deployed Kobo forms.'

    def handle(self, *args, **opts):
        token = getattr(settings, 'KOBO_TOKEN', '') or os.environ.get('KOBO_TOKEN', '')
        if not token:
            raise CommandError('KOBO_TOKEN is not set — run via `railway run`.')
        headers = {'Authorization': f'Token {token}'}

        try:
            with open(OUT, encoding='utf-8') as f:
                previous = json.load(f)
        except (OSError, ValueError):
            previous = {}

        out = {}
        for pop, uid in ASSETS.items():
            r = requests.get(API.format(uid=uid), headers=headers, timeout=180)
            r.raise_for_status()
            asset = r.json()
            content = asset['content']

            clists = {}
            for c in content.get('choices', []):
                clists.setdefault(c['list_name'], []).append(
                    (str(c.get('name')), _clip(_first(c.get('label')), 90)))

            labels, choices, sections, types, order = {}, {}, {}, {}, []
            section = ''
            for q in content['survey']:
                qtype = (q.get('type') or '').split()[0] if q.get('type') else ''
                name = q.get('name')
                if qtype == 'begin_group':
                    section = _clip(_first(q.get('label')), 80) or section
                    continue
                if qtype == 'end_group':
                    continue
                if not name or qtype in _SKIP_TYPES:
                    continue
                order.append(name)
                labels[name] = _clip(_first(q.get('label')), 180)
                sections[name] = section or _section_of(name)
                types[name] = q.get('type')
                lst = q.get('select_from_list_name')
                if lst and lst in clists:
                    cmap = {code: lab for code, lab in clists[lst]}
                    if cmap:
                        choices[name] = cmap

            # MERGE, don't replace. Questions removed from the form in an earlier
            # redeploy (questionnaire_serial, dc_name, supervisor_name_code, …) are
            # still present in the records collected while they existed, and the
            # verification card renders those records too. The live form wins for
            # every field it defines; retired fields keep their last known text so
            # history stays readable.
            prev = previous.get(pop, {})
            def _merge(fresh, old_key):
                merged = dict(prev.get(old_key, {}))
                merged.update(fresh)
                return merged

            retired = sorted(set(prev.get('types', {})) - set(types))
            out[pop] = {
                'uid': uid,
                'name': asset.get('name', ''),
                # Pin what this projection was taken from, so drift is visible.
                'deployed_version': asset.get('deployed_version_id'),
                'labels': _merge(labels, 'labels'),
                'choices': _merge(choices, 'choices'),
                'sections': _merge(sections, 'sections'),
                'types': _merge(types, 'types'),
                'order': order,          # order reflects the CURRENT form only
                'retired_fields': retired,
            }
            self.stdout.write(self.style.SUCCESS(
                f'  {pop:5s} {len(labels):4d} fields  {len(choices):3d} coded  '
                f'version {asset.get("deployed_version_id")}'))

        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
        self.stdout.write(self.style.SUCCESS(
            f'WROTE {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)'))
