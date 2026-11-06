"""Seed realistic demo baseline interviews (Hijra + FSW) so the /baseline
dashboard shows real insights and the verification card shows real detail.

Creates PENDING KoboSubmissions with plausible answers keyed to the two live
forms' real field codes, then APPROVES most (the post_save signal materialises
the verified BaselineResponse), leaving a few PENDING to demo the review queue.

    python manage.py seed_baseline_demo --hijra 24 --fsw 20 --pending 6 --wipe

Idempotent-ish: --wipe first removes any prior demo rows (kobo_id prefix
DEMO-BL-) so re-runs don't accumulate. Demo-only; never run against real data
without --wipe intent.
"""
import json
import os
import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models.signals import post_save
from django.utils import timezone

from baseline.collectors import DATA_COLLECTORS
from baseline.models import BaselineResponse
from submissions.models import FormType, KoboSubmission, SubmissionStatus

PREFIX = 'DEMO-BL-'
SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'form_schema.json')

XFORM = {'hijra': 'ciprb_baseline_hijra_v1', 'fsw': 'ciprb_baseline_fsw_v1'}

# The deployed Kobo assets. A real payload stamps the ASSET UID (not the readable
# id_string) into _xform_id_string — that is exactly what broke population
# resolution, so the demo must reproduce it.
ASSET_UID = {'hijra': 'aBT7aCL9p4FGcW4WwXZcr6', 'fsw': 'aVsJ7VJ35k8GshpQpnXygC'}

# field -> 'group/sub/field' path, generated from the DEPLOYED XLSForms.
FIELD_PATHS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'field_paths.json')


def _to_kobo_payload(flat, pop, paths, submitted, lat, lng, seq):
    """Turn the flat answer dict into a payload shaped like a REAL Kobo submission.

    Kobo serialises grouped questions as 'group/field' and adds its own meta keys.
    The demo seed used to emit FLAT keys and invent fields the forms never collect
    (dc_name, interviewer_name_code, questionnaire_serial). That fiction is why the
    dashboard read healthy for weeks while the real ingest path was broken: every
    reader was validated against data no enumerator could ever produce.

    Any answer whose name is not in the deployed form is DROPPED, so the demo can
    never contain a field the real instrument lacks.
    """
    out = {}
    for key, val in flat.items():
        path = paths.get(key)
        if path is None:
            continue                      # not a field in the deployed form
        out[path] = val

    out.update({
        '_id': 900000 + seq,
        '_uuid': str(uuid.uuid4()),
        '_status': 'submitted_via_web',
        '__version__': 'vDemoSeed',
        '_xform_id_string': ASSET_UID[pop],
        '_submitted_by': 'baseline89',    # the Kobo LOGIN — must never name a collector
        '_submission_time': submitted.strftime('%Y-%m-%dT%H:%M:%S'),
        'formhub/uuid': uuid.uuid4().hex,
        'meta/rootUuid': 'uuid:' + str(uuid.uuid4()),
    })
    if lat is not None and lng is not None:
        out['_geolocation'] = [lat, lng]
    return out
# rough district -> (lat, lng) for plausible GPS
GEO = {
    'sunamganj': (25.07, 91.40), 'habiganj': (24.37, 91.41), 'manikganj': (23.86, 90.00),
    'narayanganj': (23.62, 90.50), 'chandpur': (23.23, 90.66), 'noakhali': (22.87, 91.10),
    'chittagong': (22.36, 91.83), 'bandarban': (22.19, 92.22), 'rajbari': (23.76, 89.64),
    'faridpur': (23.60, 89.84), 'jashore': (23.17, 89.21), 'khulna': (22.85, 89.56),
    'dhaka': (23.81, 90.41),
}


def _W(d):
    """Weighted pick from {code: weight}."""
    return random.choices(list(d), weights=list(d.values()), k=1)[0]


def _realistic_srhr(pop, base):
    """Give the major-SRHR-indicator fields plausible, correlated values so the
    demo dashboard shows a believable baseline (not random-fill artefacts)."""
    R = random.random
    # ── Food insecurity (FIES) — severity-ordered; most people 0–4 affirmed,
    #    ~15% affirm 7+/9 (severe). Hijra c101–c109 / FSW b301_a–i occurrence.
    lvl = random.choices(range(10), weights=[20, 15, 14, 12, 10, 8, 7, 6, 5, 3], k=1)[0]
    if pop == 'hijra':
        for i in range(1, 10):
            yes = i <= lvl
            base[f'c10{i}'] = '1' if yes else '0'
            if yes:
                base[f'c10{i}a'] = _W({'1': 45, '2': 40, '3': 15})
    else:
        for i, c in enumerate('abcdefghi', 1):
            yes = i <= lvl
            base[f'b301_{c}_occ'] = '1' if yes else '0'
            if yes:
                base[f'b301_{c}_times'] = _W({'1': 45, '2': 40, '3': 15})
    # ── PHQ-9 — mixture: a ~14% depressed subgroup gives a realistic tail so
    #    prevalence (≥10) ≈ 20%, moderate/severe (≥15) ≈ 8%, item-9 ideation ≈ 15%.
    depressed = R() < 0.14
    for i in range(1, 10):
        if i == 9:
            w = {'0': 66, '1': 18, '2': 10, '3': 6} if depressed else {'0': 89, '1': 7, '2': 3, '3': 1}
        else:
            w = {'0': 20, '1': 26, '2': 31, '3': 23} if depressed else {'0': 63, '1': 24, '2': 9, '3': 4}
        base[f'q8_3_{i}'] = _W(w)
    # ── STI symptoms Q5.4 grid — most people have NO symptoms; only ~20% report
    #    any. The generic fill randomises each of the 4–5 symptom rows, which makes
    #    "any symptom" compound to ~85% (implausible). Gate it: ~20% symptomatic,
    #    and only those affirm 1–2 specific rows; everyone else is a clean "no".
    sym_cols = 'abcd' if pop == 'hijra' else 'abcde'
    picked = (set(random.sample(list(sym_cols), random.randint(1, 2)))
              if R() < 0.20 else set())
    for c in sym_cols:
        base[f'q5_4_{c}'] = '1' if c in picked else '2'
    # ── Violence Q7.1 grid — ~13%/item so "any" over 11–12 rows ≈ 60%
    v_items = (list('abcdefghijk') if pop == 'hijra'
               else ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii'])
    for c in v_items:
        yes = R() < 0.13
        base[f'q7_1_{c}_ever'] = '1' if yes else '2'
        if yes:
            base[f'q7_1_{c}_12mo'] = '1' if R() < 0.5 else '2'
    # ── Discrimination Q2.1 grid — ~13%/item so "any" over 14–15 rows ≈ 85%
    for c in ('abcdefghijklmno' if pop == 'hijra' else 'abcdefghijklmn'):
        base[f'q2_1_{c}'] = '1' if R() < 0.13 else '2'
    # ── Consistent condom use q4_7 — Always ~62%/type so "all always" ≈ 25–30%
    for c in ('abcd' if pop == 'hijra' else 'abc'):
        base[f'q4_7_{c}'] = _W({'1': 62, '2': 24, '3': 9, '8': 5})
    # ── HIV/STI knowledge yes/no items — bias toward correct (realistic 60–70%)
    for i in ((1, 2, 3, 4, 6, 7, 8, 9, 10) if pop == 'hijra' else (1, 2, 3, 4, 6, 7, 8, 9, 10)):
        f = f'q3_{i}'
        if f in base and str(base[f]) in ('1', '2'):
            base[f] = '1' if R() < 0.68 else '2'
    # ── Key single-choice indicators that otherwise read random ──
    if pop == 'hijra':
        base['q2_5'] = _W({'1': 22, '2': 30, '3': 28, '4': 20})       # community participation
        base['q5_8'] = _W({'1': 62, '2': 38})                         # ever HIV-tested
        if base['q5_8'] == '1':
            base['q5_9'] = _W({'1': 55, '2': 28, '3': 17})            # recency
            base['q5_11'] = _W({'1': 40, '2': 18, '3': 14, '4': 28})  # counselling
        base['q5_15'] = _W({'1': 55, '2': 25, '3': 20})               # STI treatment done
        base['q6_1'] = _W({'1': 64, '2': 36})                         # facility used
        base['q6_5'] = _W({'1': 14, '2': 30, '3': 34, '4': 22})       # satisfaction
        base['q2_19'] = _W({'1': 28, '2': 72})                        # received legal
    else:
        base['q4_5'] = _W({'1': 72, '2': 28})                         # condom at last client sex
        base['q4_9'] = _W({'1': 48, '2': 38, '3': 14})                # can refuse client
        base['b112'] = _W({'1': 30, '2': 40, '3': 26, '99': 4})       # income autonomy
        base['b114'] = _W({'1': 34, '2': 66})                         # savings
        base['q5_8'] = _W({'1': 55, '2': 45})                         # ever tested for STI
        base['q5_9'] = _W({'1': 22, '2': 78})                         # diagnosed with STI (coherent w/ ~20% symptomatic)
        base['q5_11'] = _W({'1': 40, '2': 42, '3': 18})               # syphilis test
        base['q5_10'] = _W({'1': 50, '2': 28, '3': 22})               # STI treatment done
        base['q6_1'] = _W({'1': 60, '2': 40})
        base['q6_4'] = _W({'1': 16, '2': 34, '3': 32, '4': 18})       # satisfaction
        base['q7_18'] = _W({'1': 38, '2': 57, '99': 5})               # help-seeking after GBV
        base['q2_19'] = _W({'1': 34, '2': 66})


def _pick(cmap, weights_by_code=None):
    """Pick a code from a {code: label} choice dict; optional weights add realism."""
    codes = list((cmap or {}).keys())
    if not codes:
        return None
    if weights_by_code:
        w = [weights_by_code.get(c, 1) for c in codes]
        return random.choices(codes, weights=w, k=1)[0]
    return random.choice(codes)


class Command(BaseCommand):
    help = 'Seed realistic demo baseline interviews for the /baseline dashboard.'

    def add_arguments(self, parser):
        # Sample large enough that a ~14% indicator (severe food insecurity,
        # depression) reads stably instead of hitting 0% by small-sample chance —
        # at n≈20 a 14% rate lands on 0 about 6% of the time, which looks broken.
        parser.add_argument('--hijra', type=int, default=100)
        parser.add_argument('--fsw', type=int, default=80)
        parser.add_argument('--pending', type=int, default=0,
                            help='How many to leave PENDING (rest are approved).')
        parser.add_argument('--wipe', action='store_true',
                            help='Remove prior DEMO-BL- rows before seeding.')

    def handle(self, *args, **opts):
        with open(SCHEMA, encoding='utf-8') as f:
            schema = json.load(f)
        with open(FIELD_PATHS, encoding='utf-8') as f:
            paths_all = json.load(f)

        if opts['wipe']:
            subs = KoboSubmission.objects.filter(kobo_id__startswith=PREFIX)
            BaselineResponse.objects.filter(submission__in=subs).delete()
            n = subs.count()
            subs.delete()
            self.stdout.write(f'Wiped {n} prior demo submission(s).')

        # Seed with the approval post_save signal DISCONNECTED: on prod each save
        # would otherwise fan out telegram + email notifications, and this service
        # has no outbound network — the stalled calls blow past the boot healthcheck
        # window. We materialise the verified BaselineResponse directly instead.
        from submissions.signals import on_submission_status_change
        post_save.disconnect(on_submission_status_change, sender=KoboSubmission)
        try:
            plan = [('hijra', opts['hijra']), ('fsw', opts['fsw'])]
            made = []
            used_ids = []
            seq = 0
            for pop, count in plan:
                for i in range(count):
                    seq += 1
                    raw = self._build_raw(pop, schema[pop], seq)
                    dist = raw.get('district', 'dhaka')
                    lat, lng = GEO.get(dist, GEO['dhaka'])
                    jitter = lambda: random.uniform(-0.05, 0.05)
                    gps_missing = random.random() < 0.08
                    # ── Fieldwork signals (for the monitoring dashboard) ──
                    # Pick a REAL data collector: dc_code is the select_one CODE the
                    # form stores ('1'..'12'), from the same roster that generates the
                    # dropdown. The seed must never invent a code the form can't emit.
                    dc, dc_display = random.choice(list(DATA_COLLECTORS[pop].items()))
                    submitted = timezone.now() - timedelta(
                        days=random.randint(0, 18), hours=random.randint(8, 20),
                        minutes=random.randint(0, 59))
                    # The instrument runs ~50 min. `iv_len` is the REAL interview
                    # length; ~6% are rushed (<40m). Submit happens some time later
                    # (`submit_lag`) — usually minutes, sometimes hours when a form
                    # is left in draft.
                    iv_len = (random.randint(12, 34) if random.random() < 0.06
                              else int(random.triangular(42, 66, 50)))
                    # ~80% of rows are on the new form version, which stamps the end
                    # of the interview at the outcome question (interview_end_actual)
                    # — so their duration is real no matter how late they submit. The
                    # rest are legacy rows with only the submit time; among those, a
                    # big submit_lag shows up as "form left open".
                    has_true_end = random.random() < 0.80
                    if has_true_end:
                        # Mostly submitted promptly; 25% sit in draft for hours — the
                        # true-end stamp must make that invisible to the duration.
                        submit_lag = (random.randint(0, 15) if random.random() < 0.75
                                      else random.randint(150, 420))
                    else:
                        # Legacy: ~a quarter left open (>120m submit lag), rest prompt.
                        submit_lag = (random.randint(150, 300) if random.random() < 0.25
                                      else random.randint(0, 20))
                    end_actual = submitted - timedelta(minutes=submit_lag)
                    start = end_actual - timedelta(minutes=iv_len)
                    outcome = random.choices(['1', '2', '3', '4'],
                                             weights=[86, 7, 4, 3], k=1)[0]
                    # ~4% share a prior submission_id → duplicate flag demo
                    if used_ids and random.random() < 0.04:
                        sub_id = random.choice(used_ids)
                    else:
                        sub_id = f'{dc}-{dist[:3].upper()}-{seq:05d}'
                        used_ids.append(sub_id)
                    raw.update({
                        # Only dc_code — the real forms carry NO collector name.
                        # The dashboard must resolve the name from this code.
                        'dc_code': dc, 'c3': outcome,
                        'interview_start': start.strftime('%Y-%m-%dT%H:%M:%S'),
                        # interview_end = SUBMIT time (the XForm `end` meta).
                        'interview_end': submitted.strftime('%Y-%m-%dT%H:%M:%S'),
                        'submission_id': sub_id,
                    })
                    if has_true_end:
                        raw['interview_end_actual'] = end_actual.strftime('%Y-%m-%dT%H:%M:%S')
                    plat = None if gps_missing else round(lat + jitter(), 6)
                    plng = None if gps_missing else round(lng + jitter(), 6)
                    sub = KoboSubmission.objects.create(
                        kobo_id=f'{PREFIX}{pop}-{seq:04d}',
                        form_type=FormType.BASELINE,
                        partner='CIPRB',
                        worker_name='baseline89',   # Kobo login, as Kobo sends it
                        district=dist.title(),
                        region='',
                        latitude=plat,
                        longitude=plng,
                        submitted_at=submitted,
                        # A payload shaped exactly like KoboToolbox sends it:
                        # 'group/field' keys + Kobo meta. Nothing flat, nothing invented.
                        raw_data=_to_kobo_payload(raw, pop, paths_all[pop],
                                                  submitted, plat, plng, seq),
                        status=SubmissionStatus.PENDING,
                    )
                    made.append(sub)

            # Approve all but the last N (kept PENDING to demo the review queue).
            random.shuffle(made)
            keep_pending = max(0, opts['pending'])
            approve = made[keep_pending:]
            for sub in approve:
                sub.status = SubmissionStatus.APPROVED
                sub.reviewed_at = timezone.now()
                sub.save(update_fields=['status', 'reviewed_at'])
                BaselineResponse.objects.get_or_create_from_submission(sub)
        finally:
            post_save.connect(on_submission_status_change, sender=KoboSubmission)

        verified = BaselineResponse.objects.filter(submission__kobo_id__startswith=PREFIX).count()
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {len(made)} interviews · approved {len(approve)} '
            f'(verified rows: {verified}) · {keep_pending} left pending.'))

    # ── realistic answer generation ──────────────────────────────────────────
    def _build_raw(self, pop, ps, seq):
        # ps = form_schema[pop] with choices / types / order. pick() reads by field name.
        ch = ps['choices']
        types = ps['types']
        order = ps['order']

        def pick(field, weights=None):
            return _pick(ch.get(field), weights)

        age = int(random.triangular(18, 45, 26))
        serial = f'{PREFIX}{pop.upper()}-{seq:04d}'
        base = {
            '_xform_id_string': XFORM[pop],
            'population': pop,
            'consent': '1',
            'interview_language': '1',
            'survey_round': 'baseline',
        }
        if pop == 'hijra':
            dist = pick('district')
            base.update({
                'district': dist,
                'a201_district': dist,
                'interview_method': '1',
                's1_selection': pick('s1_selection'),
                's2_age': age,
                's3_member': '1',
                's4_residence': pick('s4_residence'),
                'a102_respondent_type': pick('a102_respondent_type'),
                'a204_area': pick('a204_area'),
                'a205_age': age,
                'a206_religion': pick('a206_religion', {'1': 82, '2': 12}),
                'a207_ethnicity': pick('a207_ethnicity'),
                'a208_marital': pick('a208_marital'),
                'a209_education': pick('a209_education',
                                       {'00': 22, '01': 18, '05': 20, '08': 14, '10': 12}),
                'a210_student': pick('a210_student', {'2': 80}),
                'a211_mobile': pick('a211_mobile', {'1': 45, '2': 40, '3': 15}),
                'a212_nid': pick('a212_nid', {'1': 68, '2': 32}),
                'a301': pick('a301'),
                'a302_gender': pick('a302_gender'),
                'b101_live_with': pick('b101_live_with'),
                'b102_hh_members': random.randint(1, 8),
                'b104_share': int(random.triangular(2000, 40000, 9000)),
                'b108_worked': pick('b108_worked', {'1': 70}),
                'b111_main_occupation': pick('b111_main_occupation'),
            })
        else:  # fsw
            dist = pick('district')
            base.update({
                'district': dist,
                'site_code': pick('site_code'),
                's1_age': age,
                's2_sexwork': '1',
                's3_residence': pick('s3_residence'),
                'a203': age,
                'a204': pick('a204', {'1': 78, '2': 16}),
                'a205': pick('a205'),
                'a206': pick('a206'),
                'a207': pick('a207', {'00': 30, '01': 22, '05': 20, '08': 12, '10': 8}),
                'a208': pick('a208', {'1': 40, '2': 42, '3': 18}),
                'a209': pick('a209', {'1': 60, '2': 40}),
                'a213': random.randint(0, 4),
                'a214': random.randint(0, 3),
                'b101': pick('b101'),
                'b108': int(random.triangular(3000, 45000, 12000)),
                'b114': pick('b114'),
            })
        # ── Complete the rest of the questionnaire ────────────────────────────
        # A real baseline interview answers the whole ~180-question form, so a
        # reviewer can only verify a COMPLETE record. Fill every remaining field
        # with a valid, plausible value (the weighted fields above are kept as-is
        # so the charts stay realistic). Nothing is merged or summarised — each
        # answer is stored faithfully and shown verbatim on the approval card.
        def fill(name, typ):
            low = name.lower()
            if typ == 'geopoint':
                return None  # GPS lives on the submission row, not raw_data
            # conditional "other (specify)" free-text — left blank unless its
            # parent select actually chose "other", which we don't simulate.
            if 'other' in low or 'specify' in low or low.endswith(('_oth', '_txt')):
                return None
            cmap = ch.get(name)
            if cmap:
                codes = [c for c in cmap.keys() if c != '']
                if not codes:
                    return None
                if typ.startswith('select_multiple'):
                    k = min(len(codes), random.randint(1, 3))
                    return ' '.join(random.sample(codes, k))
                return random.choice(codes)
            if typ == 'integer':
                if 'age' in low:
                    return age
                if 'year' in low:
                    return random.randint(0, 15)
                if 'month' in low:
                    return random.randint(0, 11)
                if 'child' in low:
                    return random.randint(0, 4)
                if any(w in low for w in ('member', 'hh', 'people', 'person',
                                          'count', 'number', '_no', 'no_', 'times')):
                    return random.randint(1, 6)
                if any(w in low for w in ('income', 'taka', 'bdt', 'amount', 'rent',
                                          'commission', 'fee', 'debt', 'share', 'exp',
                                          'salary', 'money', 'earn', 'cost')):
                    return random.choice([0, 1500, 3000, 5000, 8000, 12000])
                return random.randint(0, 4)
            if typ == 'decimal':
                return random.choice([0, 1, 2, 3])
            if typ == 'date':
                return '2026-06-%02d' % random.randint(1, 28)
            if typ == 'time':
                return '%02d:%02d' % (random.randint(8, 17), random.choice([0, 15, 30, 45]))
            if typ == 'text':
                if any(w in low for w in ('name', 'code', 'interviewer', 'supervisor', 'enumerator')):
                    return 'Demo Field Staff'
                if 'upazila' in low or 'thana' in low:
                    return 'Sadar'
                if 'union' in low or 'ward' in low:
                    return 'Ward 3'
                if 'mobile' in low or 'phone' in low:
                    return '017' + str(random.randint(10000000, 99999999))
                if any(w in low for w in ('district', 'ancestral', 'home', 'address', 'place')):
                    return 'Dhaka'
                if any(w in low for w in ('serial', 'cluster', 'site')):
                    return name.upper()[:20]
                return None  # unknown free text → leave blank
            return None

        for name in order:
            if name in base:  # keep the weighted demographic fields as set above
                continue
            v = fill(name, types.get(name, 'text'))
            if v is not None:
                base[name] = v

        # The generic fill above puts a RANDOM code in every scale/grid item, which
        # makes the SRHR indicators nonsense (0% food insecurity, 100% GBV, 90%
        # depression). Overwrite the fields that feed the major-indicator panel with
        # realistic, severity-ordered distributions so the review dashboard reads true.
        _realistic_srhr(pop, base)

        # drop any None (choice list absent) so we never store nulls
        return {k: v for k, v in base.items() if v is not None}
