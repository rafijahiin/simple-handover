"""The rendered schema must cover every question the forms actually ask.

schema.humanize() falls back to the RAW KEY for any field it does not know, so a
missing entry means a CIPRB reviewer sees `q7_14_a_perp_12mo` and `1` instead of
the question and the answer. form_schema.json was built from a hand-taken
snapshot (_baseline_schema.json) and had drifted 66 FSW / 71 Hijra questions
behind the deployed forms — the entire *_perp_12mo violence battery among them.

This guard needs no network: field_paths.json and form_schema.json are both
repo artefacts regenerated from the same deploy, so if someone rebuilds the forms
and forgets `manage.py build_form_schema`, CI fails here rather than the review
card degrading silently in front of the client.
"""
import json
import os

from django.conf import settings
from django.test import TestCase

from .schema import load_schema

# Kobo metadata / routing keys that carry no answer to render.
_NOT_RENDERED = {
    'interview_end', 'interview_start', 'interview_start_disp', 'interview_end_actual',
    'start', 'end', 'today', 'deviceid', 'username', '__version__', '_id_ts',
    '_proceed', 'organisation', 'population', 'survey_round',
}


def _field_paths():
    with open(os.path.join(settings.BASE_DIR, 'baseline', 'field_paths.json'),
              encoding='utf-8') as fh:
        return json.load(fh)


class SchemaDriftTest(TestCase):
    def test_schema_covers_every_field_on_the_form(self):
        paths, schema = _field_paths(), load_schema()
        for pop in ('fsw', 'hijra'):
            types = schema[pop]['types']
            missing = sorted(f for f in paths[pop]
                             if f not in types and f not in _NOT_RENDERED)
            self.assertEqual(missing, [], (
                f'{pop}: {len(missing)} question(s) the form asks are absent from '
                f'form_schema.json, so the review card will show their raw field '
                f'name and raw coded answer. Run: manage.py build_form_schema'))

    def test_the_violence_battery_renders(self):
        """The *_perp_12mo recall battery is the most sensitive module in the study
        and was entirely absent from the schema."""
        schema = load_schema()
        for pop, expected in (('fsw', 26), ('hijra', 24)):
            coded = [f for f in schema[pop]['types']
                     if '_perp_12mo' in f and f in schema[pop]['choices']]
            self.assertGreaterEqual(len(coded), expected,
                                    f'{pop}: perpetrator answers would render as raw codes')

    def test_schema_pins_the_version_it_was_taken_from(self):
        schema = load_schema()
        for pop in ('fsw', 'hijra'):
            self.assertTrue(schema[pop].get('deployed_version'),
                            f'{pop}: schema does not record which deployed form it '
                            f'projects — drift would be undetectable')

    def test_retired_questions_stay_renderable(self):
        """Fields removed from the form still exist in the records collected while
        they were live; the card renders those records too."""
        schema = load_schema()
        for pop in ('fsw', 'hijra'):
            retired = schema[pop].get('retired_fields', [])
            self.assertTrue(retired, f'{pop}: expected retired fields to be retained')
            for f in retired:
                self.assertIn(f, schema[pop]['labels'],
                              f'{pop}: retired field {f} lost its question text')
