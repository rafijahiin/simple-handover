"""The deployed Kobo forms must still carry the fields and choice codes the CIPRB
handlers read.

When a form is redeployed and a field is renamed or a choice code changed, the
handler's `payload.get('x')` silently returns nothing and its `== 'code'` branch
silently stops matching — so a death gets miscoded or a panel goes blank with no
error anywhere. This test fetches each deployed CIPRB form from Kobo and asserts
the load-bearing contract still holds:

  * REQUIRED fields exist (fallback sets: at least ONE alternative must exist).
  * CHOICE CODES the handler BRANCHES ON exist in that field's choice list —
    these are the silent-misclassification risks (place 'home'/'on_the_way',
    death_kind maternal/neonatal/stillbirth, sa_death_type '1', fistula stages,
    ap_mode 'update_action').

It hits the live Kobo API, so it is skipped when KOBO_TOKEN is absent (the
hermetic suite stays offline); run it with the token present — e.g.
`railway run python manage.py test programs.test_ciprb_form_contract` — before
trusting a form redeploy. The contract mirrors programs/ciprb_handlers.py; keep
them in step (see SEMANTICS.md and the field-ref map).
"""
import os
import unittest

import requests
from django.test import SimpleTestCase

KOBO_TOKEN = os.environ.get('KOBO_TOKEN', '')
B = 'https://kf.kobotoolbox.org/api/v2'

# slug -> deployed Kobo asset UID. There is NO id_string on the assets that
# equals the webhook slug (the slug is the REST-service URL key CIPRB configured,
# not a stored asset field), so the mapping is pinned here. These UIDs are stable
# across redeploys — a redeploy PATCHes the same asset (see the MPDSR recovery),
# so a form update keeps its UID. Only a brand-new asset needs a change here, and
# that is a deliberate, reviewed event. If CIPRB creates a new asset for a slug,
# this map (and the webhook REST service) must be updated together.
SLUG_TO_UID = {
    'ciprb_fistula_questions_v1':        'aH86Euq2AeJ8S9VYdry4PC',
    'ciprb_mpdsr_community_maternal_v1': 'apvPk7qq94nry2aW3z7y4H',
    'ciprb_mpdsr_community_neonatal_v1': 'awQXeYhuLoLrM38fwSrF8y',
    'ciprb_mpdsr_facility_maternal_v1':  'aVQbxhGnDHNCe6AazSJByM',
    'ciprb_mpdsr_facility_neonatal_v1':  'a6pg47mTt8E56igHnK8SSD',
    'ciprb_social_autopsy_v1':           'a6vQiCJ3tz4MRxKqdMHCbA',
    'ciprb_notification_slip_01_v1':     'aSnEgQT6DUooVanZXubhAF',
    'ciprb_notification_slip_02_v1':     'aaCnfRHHgkukkhDgXwUnXX',
    'ciprb_near_miss_v1':                'aTzdRTvhZ8yUQCGhA8UG5R',
    'ciprb_mpdsr_response_plan_v1':      'auFCf7bfBDtrP6xeW5F2KJ',
}

# slug -> {required: [field | (a, b, ...) fallback set], choices: {field: [codes]}}
# Only load-bearing fields/codes — those whose rename silently breaks a number.
CONTRACT = {
    'ciprb_fistula_questions_v1': {
        'required': ['district', 'stage',
                     ('patient_code_final', 'patient_code', 'patient_code_sel')],
        'choices': {
            'stage': ['suspected', 'diagnosed', 'referred', 'repaired', 'rehabilitated'],
            'genital_fistula_type': ['other'],
        },
    },
    'ciprb_mpdsr_community_maternal_v1': {
        'required': ['district', 'icd_cause', ('death_date', 'date_of_death')],
        'choices': {},
    },
    'ciprb_mpdsr_community_neonatal_v1': {
        'required': ['district', 'icd_cause', ('death_date', 'date_of_death')],
        'choices': {},
    },
    'ciprb_mpdsr_facility_maternal_v1': {
        'required': ['district', 'cause_of_death', ('date_of_death', 'death_date')],
        'choices': {},
    },
    'ciprb_mpdsr_facility_neonatal_v1': {
        'required': ['district', 'cod_cause', ('death_date', 'date_of_death')],
        'choices': {},
    },
    'ciprb_social_autopsy_v1': {
        'required': ['district', 'meeting_date', 'sa_death_type'],
        # '1' = maternal — the marker the tile and cohort depend on.
        'choices': {'sa_death_type': ['1']},
    },
    'ciprb_notification_slip_01_v1': {
        'required': ['district', 'death_kind',
                     ('death_date', 'date_of_death'),
                     ('mother_name', 'deceased_name')],
        'choices': {
            'death_kind': ['maternal', 'neonatal', 'stillbirth'],
            'place_of_death': ['home', 'on_the_way', 'govt_facility', 'private_ngo'],
        },
    },
    'ciprb_notification_slip_02_v1': {
        'required': ['district', 'death_kind',
                     ('death_date', 'date_of_death'),
                     ('mother_name', 'deceased_name')],
        'choices': {'death_kind': ['maternal', 'neonatal', 'stillbirth']},
    },
    'ciprb_near_miss_v1': {
        # Screening checkboxes are many; assert a representative pair so a
        # wholesale rename of the battery is caught.
        'required': ['district', 'event_date', 'woman_name', 'sev_pph', 'eclampsia'],
        'choices': {},
    },
    'ciprb_mpdsr_response_plan_v1': {
        # act_factor carries master Table 2's first column (the common
        # modifiable factor) into MPDSRAction.sub_category; losing it would
        # silently un-attribute every factor-table action.
        'required': ['ap_mode', 'act_factor', 'act_factor_other'],
        # 'update_action' branch drives whether a submission mutates or creates.
        'choices': {
            'ap_mode': ['update_action'],
            'rp_section': ['community_va', 'facility_dr'],
            'act_factor': ['pph_management', 'referral_linkages',
                           'home_delivery_tba', 'other'],
        },
    },
}


def _form(uid):
    r = requests.get('%s/assets/%s/?format=json' % (B, uid),
                     headers={'Authorization': 'Token ' + KOBO_TOKEN}, timeout=120)
    r.raise_for_status()
    content = r.json().get('content', {})
    # leaf field names present on the form
    fields = {q.get('name') for q in content.get('survey', []) if q.get('name')}
    # per-field choice codes
    lists = {}
    for c in content.get('choices', []):
        lists.setdefault(c['list_name'], set()).add(str(c.get('name')))
    field_list = {q.get('name'): q.get('select_from_list_name')
                  for q in content.get('survey', []) if q.get('name')}
    choices = {name: lists.get(lst, set())
               for name, lst in field_list.items() if lst}
    return fields, choices


@unittest.skipUnless(KOBO_TOKEN, 'KOBO_TOKEN not set — run with `railway run` to hit live Kobo')
class CIPRBFormContractTest(SimpleTestCase):
    databases = set()

    def test_every_contract_slug_has_a_uid(self):
        # Every CIPRB webhook slug in the contract must have a pinned UID, and
        # every pinned UID must return a deployed form (guards against a UID typo
        # or a form being un-deployed).
        missing = [slug for slug in CONTRACT if slug not in SLUG_TO_UID]
        self.assertEqual(missing, [], 'no pinned UID for slug(s): %s' % missing)
        for slug, uid in SLUG_TO_UID.items():
            fields, _ = _form(uid)
            self.assertTrue(fields, '%s (%s) returned no form fields' % (slug, uid))

    def test_required_fields_and_choice_codes_exist(self):
        problems = []
        for slug, spec in CONTRACT.items():
            uid = SLUG_TO_UID.get(slug)
            if not uid:
                continue  # covered by the test above
            fields, choices = _form(uid)
            for req in spec['required']:
                alts = req if isinstance(req, tuple) else (req,)
                if not any(a in fields for a in alts):
                    problems.append('%s: none of %s on the form' % (slug, list(alts)))
            for field, codes in spec['choices'].items():
                have = choices.get(field, set())
                if field not in fields:
                    problems.append('%s: choice field %r missing' % (slug, field))
                    continue
                for code in codes:
                    if str(code) not in have:
                        problems.append(
                            '%s: %s choice %r missing (handler branches on it)'
                            % (slug, field, code))
        self.assertEqual(problems, [], '\n' + '\n'.join(problems))
