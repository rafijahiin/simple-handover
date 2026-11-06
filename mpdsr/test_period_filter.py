"""The reporting period filters on when a case ENTERED surveillance, not on
when the person died.

MPDSR reviews deaths retrospectively: fieldwork began in June 2026 and reviewed
deaths back to January. The dashboard's only reporting period is the contract
window (21 May → 20 Nov); filtered on date_of_death it kept 3 of 62 approved
cases and 0 of 26 community maternal deaths — every visualization below the
fold (cause-of-death, reporting rate) rendered its empty state while the data
sat approved in the database.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from mpdsr.models import MPDSRCase


def _case(**over):
    kw = dict(partner='CIPRB', sub_form_type='f1', district='Bhola',
              date_of_death='2026-01-15', death_type='maternal',
              cause_of_death='pph', approval_status='APPROVED')
    kw.update(over)
    return MPDSRCase.objects.create(**kw)


class PeriodFilterTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user(
            email='pf@ciprb.org', password='p', full_name='PF',
            organisation=Organisation.CIPRB, role=Role.ORG_LEAD))

    def test_a_january_death_reviewed_now_is_inside_the_contract_window(self):
        """created_at is auto_now_add (today), date_of_death is January. The
        contract window must include it — it is contract-period output."""
        _case(case_hash='pf-1')
        r = self.client.get('/api/mpdsr/cases/?from=2026-05-21&to=2026-11-20')
        rows = r.json()
        rows = rows if isinstance(rows, list) else rows.get('results', [])
        self.assertEqual(len(rows), 1,
                         'a retrospectively-reviewed death was hidden by the '
                         'reporting-period filter')

    def test_a_case_reported_outside_the_window_is_excluded(self):
        _case(case_hash='pf-2')
        r = self.client.get('/api/mpdsr/cases/?from=2030-01-01&to=2030-12-31')
        rows = r.json()
        rows = rows if isinstance(rows, list) else rows.get('results', [])
        self.assertEqual(len(rows), 0)

    def test_no_period_returns_everything_approved(self):
        _case(case_hash='pf-3')
        _case(case_hash='pf-4', approval_status='PENDING')
        r = self.client.get('/api/mpdsr/cases/')
        rows = r.json()
        rows = rows if isinstance(rows, list) else rows.get('results', [])
        self.assertEqual(len(rows), 1, 'pending cases must stay out of the dashboard')
