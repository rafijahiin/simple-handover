from django.core.management import call_command
from django.test import TestCase

from .insights import compute_insights
from .models import BaselineResponse
from .schema import headline, humanize, value_label


class BaselineInsightsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_baseline_demo', '--hijra', '12', '--fsw', '8',
                     '--pending', '3', verbosity=0)

    def test_seed_materialises_verified_responses(self):
        # 20 seeded, 3 kept pending -> 17 approved -> 17 verified rows.
        self.assertEqual(BaselineResponse.objects.count(), 17)

    def test_insights_shape_and_values(self):
        data = compute_insights(BaselineResponse.objects.all())
        self.assertEqual(data['total'], 17)
        pops = {p['key']: p['value'] for p in data['population']}
        self.assertEqual(pops['hijra'] + pops['fsw'], 17)
        # Every core dimension yields labelled buckets for at least one population.
        for dim in ('age_band', 'district', 'education', 'marital', 'income_band'):
            buckets = data[dim]['hijra'] + data[dim]['fsw']
            self.assertTrue(buckets, f'{dim} produced no buckets')
            for b in buckets:
                self.assertIn('name', b)
                self.assertIsInstance(b['value'], int)
        # KPIs are sane percentages / averages.
        for pop in ('hijra', 'fsw'):
            k = data['kpis'][pop]
            if k['nid_pct'] is not None:
                self.assertGreaterEqual(k['nid_pct'], 0)
                self.assertLessEqual(k['nid_pct'], 100)
            if k['avg_age'] is not None:
                self.assertGreater(k['avg_age'], 10)

    def test_age_bands_are_readable_not_codes(self):
        data = compute_insights(BaselineResponse.objects.all())
        names = {b['name'] for b in data['age_band']['hijra'] + data['age_band']['fsw']}
        self.assertTrue(names <= {'≤19', '20–24', '25–29', '30–34', '35–39', '40–49', '50+'})

    def test_value_label_translates_codes(self):
        # Hijra a212_nid: 1 = Yes.
        self.assertEqual(value_label('hijra', 'a212_nid', '1'), 'Yes')
        # Unknown code passes through.
        self.assertEqual(value_label('hijra', 'a212_nid', 'zzz'), 'zzz')

    def test_seeded_interview_is_complete(self):
        # A reviewer must see the WHOLE questionnaire, not a thin subset. Each
        # seeded interview answers most of the ~180-question form, grouped into
        # its real modules (not a generic "Other" bucket).
        r = BaselineResponse.objects.filter(population='hijra').first()
        rows = humanize('hijra', r.raw_data)
        self.assertGreater(len(rows), 150)
        sections = {row['section'] for row in rows}
        self.assertGreater(len(sections), 8)
        self.assertLess(sum(1 for s in sections if s == 'Other'), 3)
        self.assertTrue(any('Module' in s for s in sections))

    def test_humanize_and_headline_readable(self):
        r = BaselineResponse.objects.filter(population='hijra').first()
        rows = humanize('hijra', r.raw_data)
        self.assertTrue(rows)
        # No Kobo meta keys leak into the review.
        self.assertFalse(any(row['field'].startswith('_') for row in rows))
        # Questions resolve to text, not the bare code.
        edu = next((row for row in rows if row['field'] == 'a209_education'), None)
        if edu:
            self.assertNotEqual(edu['question'], 'a209_education')
        head = headline('hijra', r.raw_data)
        self.assertTrue(any(h['label'] == 'Age' for h in head))
