"""Every pinned FieldMap role must name a column that actually exists.

A role can fail two ways. UNRESOLVED (None) is visible — the console prints null.
A DEAD PIN is not: it names a column that is never built, so every rule reading
it skips silently while `resolved_fields` displays the name as if it worked.

Hijra's expenses_total was pinned to 'expenses_total' — a key _shape_record only
builds from the FSW b110_* block — so the expense check did nothing across 370
interviews and looked healthy doing it. This is the guard that would have caught
it on the day it was written.
"""
import json
import os

from django.conf import settings
from django.test import TestCase

from .anomaly import (FIELD_MAP_BUILDERS, _EXPENSE_FIELDS, dead_pins)
from .schema import load_schema

# Columns _shape_record synthesises rather than copying from the questionnaire.
_DERIVED = {'_uuid', '__version__', '_submission_time', 'enumerator_name',
            'site_code', 'consent', 'interview_start', 'interview_end_actual',
            'latitude', 'longitude', 'gps_precision'}


def _form_fields(population):
    with open(os.path.join(settings.BASE_DIR, 'baseline', 'field_paths.json'),
              encoding='utf-8') as fh:
        return set(json.load(fh)[population])


def _available(population):
    """Columns a shaped record of this population can actually carry.

    'expenses_total' is NOT unconditionally derived — _shape_record only creates it
    when at least one _EXPENSE_FIELDS column is present, which is true of FSW and
    false of Hijra. Whitelisting it for every population is what let the original
    dead pin pass this guard: the check has to know the column is built for THIS
    form, not that the name looks synthetic.
    """
    fields = _form_fields(population) | _DERIVED
    if any(f in fields for f in _EXPENSE_FIELDS):
        fields.add('expenses_total')
    return fields


class FieldMapPinTest(TestCase):
    def test_every_pinned_role_exists_on_the_form(self):
        for population in FIELD_MAP_BUILDERS:
            fields = _available(population)
            fm = FIELD_MAP_BUILDERS[population](load_schema().get(population, {}))
            for role, col in fm.__dict__.items():
                if role == 'headers' or not col:
                    continue
                # select_multiple roles are pinned by LABEL, not field name.
                if '/' in str(col):
                    continue
                self.assertIn(col, fields,
                              f'{population}.{role} is pinned to {col!r}, which no '
                              f'question on the deployed form produces')

    def test_dead_pins_detects_a_pin_with_no_column(self):
        fm = FIELD_MAP_BUILDERS['hijra'](load_schema().get('hijra', {}))
        self.assertIn('age_demographic', dead_pins(fm, headers=[]))
        self.assertEqual(dead_pins(fm, headers=list(fm.__dict__.values())), [])

    def test_expense_fields_all_exist_on_the_fsw_form(self):
        # Four names in this tuple (b110_food/other/children/health) existed on
        # NEITHER form and had never matched anything.
        fields = _form_fields('fsw')
        for f in _EXPENSE_FIELDS:
            self.assertIn(f, fields, f'{f} is not asked by the FSW form')

    def test_hijra_expense_role_points_at_the_question_hijra_actually_asks(self):
        fm = FIELD_MAP_BUILDERS['hijra'](load_schema().get('hijra', {}))
        self.assertEqual(fm.expenses_total, 'b105_shared_exp')
        self.assertIn('b105_shared_exp', _form_fields('hijra'))
