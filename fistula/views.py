from django.db.models import Sum
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import (
    CanAccessFistulaCases,
    IsSupervisorOrManager,
    OrgFilterMixin,
)
from .ciprb_models import CIPRBFistulaCaseCost
from .geo_names import canon, canon_pair
from .models import FistulaCampaign, FistulaCornerCase, FistulaCampaignVisit
from .serializers import (
    FistulaCampaignSerializer,
    FistulaCornerCaseSerializer,
    FistulaCampaignVisitSerializer,
)


class FistulaCampaignViewSet(OrgFilterMixin, ModelViewSet):
    """Legacy aggregate campaign sessions (one row per CHW day)."""
    queryset = FistulaCampaign.objects.select_related('submission', 'created_by').all()
    permission_classes = [IsSupervisorOrManager]
    http_method_names = ['get', 'head', 'options']
    org_field = 'partner'

    def get_queryset(self):
        qs = super().get_queryset()
        partner_param = self.request.query_params.get('partner')
        district_param = self.request.query_params.get('district')
        date_from = self.request.query_params.get('from')
        date_to = self.request.query_params.get('to')
        if partner_param and getattr(self.request.user, 'can_see_all_orgs', False):
            qs = qs.filter(partner=partner_param)
        if district_param:
            qs = qs.filter(district__icontains=district_param)
        # Donor-filter pill (GAC / SIDA) sends a comma-separated district
        # list. Match case-insensitively against the district field.
        districts_param = self.request.query_params.get('districts')
        if districts_param:
            names = [n.strip() for n in districts_param.split(',') if n.strip()]
            if names:
                from django.db.models import Q
                q = Q()
                for n in names:
                    q |= Q(district__iexact=n)
                qs = qs.filter(q)
        # Reporting-period filter from the CIPRB Dashboard toggle.
        if date_from:
            qs = qs.filter(campaign_date__gte=date_from)
        if date_to:
            qs = qs.filter(campaign_date__lte=date_to)
        return qs

    def get_serializer_class(self):
        return FistulaCampaignSerializer

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        today = timezone.now().date()
        month_start = today.replace(day=1)
        month_qs = qs.filter(campaign_date__gte=month_start)

        totals = month_qs.aggregate(
            women_screened=Sum('women_screened'),
            confirmed=Sum('confirmed_fistula_cases'),
            referred=Sum('cases_referred'),
            surgery=Sum('cases_surgery_completed'),
        )

        return Response({
            'total_sessions': qs.count(),
            'this_month_sessions': month_qs.count(),
            'this_month_women_screened': totals['women_screened'] or 0,
            'this_month_confirmed_cases': totals['confirmed'] or 0,
            'this_month_cases_referred': totals['referred'] or 0,
            'this_month_surgery_completed': totals['surgery'] or 0,
        })


class FistulaCornerCaseViewSet(ModelViewSet):
    """CRUD for District Hospital Fistula Corner diagnostic records.

    CIPRB-owned clinical data carrying decrypted patient PII (name, husband
    name, mobile). Access is restricted to CIPRB roles by
    CanAccessFistulaCases — developer/supervisor (all) and org_lead (CIPRB
    only). PHD/Bandhu managers and field staff are denied (audit FIX C1).
    """
    queryset = FistulaCornerCase.objects.all()
    serializer_class = FistulaCornerCaseSerializer
    permission_classes = [CanAccessFistulaCases]
    http_method_names = ['get', 'head', 'options', 'post', 'patch', 'delete']

    def get_queryset(self):
        qs = super().get_queryset().order_by('-diagnosis_date', '-created_at')
        district = self.request.query_params.get('district')
        date_from = self.request.query_params.get('from')
        date_to = self.request.query_params.get('to')
        if district:
            qs = qs.filter(district__icontains=district)
        # Donor filter — comma-separated district list from the pill.
        districts_param = self.request.query_params.get('districts')
        if districts_param:
            names = [n.strip() for n in districts_param.split(',') if n.strip()]
            if names:
                from django.db.models import Q
                q = Q()
                for n in names:
                    q |= Q(district__iexact=n)
                qs = qs.filter(q)
        # Reporting-period filter — uses diagnosis_date (event date for a
        # corner-case workflow).
        if date_from:
            qs = qs.filter(diagnosis_date__gte=date_from)
        if date_to:
            qs = qs.filter(diagnosis_date__lte=date_to)
        return qs

    def perform_create(self, serializer):
        serializer.save(submitted_by=self.request.user)


class FistulaCampaignVisitViewSet(ModelViewSet):
    """CRUD for house-to-house screening visit records.

    CIPRB-owned and PII-bearing (patient name, husband name, contact).
    Restricted to CIPRB roles by CanAccessFistulaCases — audit FIX C1.
    """
    queryset = FistulaCampaignVisit.objects.all()
    serializer_class = FistulaCampaignVisitSerializer
    permission_classes = [CanAccessFistulaCases]
    http_method_names = ['get', 'head', 'options', 'post', 'patch', 'delete']

    def get_queryset(self):
        qs = super().get_queryset().order_by('-visit_date', '-created_at')
        district = self.request.query_params.get('district')
        union = self.request.query_params.get('union')
        date_from = self.request.query_params.get('from')
        date_to = self.request.query_params.get('to')
        if district:
            qs = qs.filter(district__icontains=district)
        if union:
            qs = qs.filter(union__icontains=union)
        # Donor filter — comma-separated district list from the pill.
        districts_param = self.request.query_params.get('districts')
        if districts_param:
            names = [n.strip() for n in districts_param.split(',') if n.strip()]
            if names:
                from django.db.models import Q
                q = Q()
                for n in names:
                    q |= Q(district__iexact=n)
                qs = qs.filter(q)
        # Reporting-period filter — visit_date is the event date.
        if date_from:
            qs = qs.filter(visit_date__gte=date_from)
        if date_to:
            qs = qs.filter(visit_date__lte=date_to)
        return qs

    def perform_create(self, serializer):
        serializer.save(submitted_by=self.request.user)


# ─── CIPRB Fistula Question Bank aggregates — the 17 dashboard indicators ─────
from rest_framework.decorators import api_view, permission_classes as _drf_perms
from rest_framework.permissions import IsAuthenticated
from collections import Counter as _Counter
import re as _re

# Shared with the MPDSR indicators so both dashboards speak one vocabulary.
from mpdsr.code_labels import canonicalise
from .ciprb_models import CIPRBFistulaCase


def _fis_band(values, edges, labels):
    """Histogram helper: bucket integers into labelled bands."""
    out = {l: 0 for l in labels}
    for v in values:
        if v is None:
            continue
        for (lo, hi), l in zip(edges, labels):
            if lo <= v < hi:
                out[l] += 1
                break
    return out


def _fis_count(qs, field):
    return dict(_Counter(qs.exclude(**{field: ''}).values_list(field, flat=True)))


_DUR_LABELS = ['<1mo', '1-6mo', '6-12mo', '1-3yr', '3yr+', 'unparsed']


def _parse_duration_months(text):
    """Free-text duration ('2 months' / '3 years' / '6 mo') → months int, or None."""
    if not text:
        return None
    s = str(text).lower()
    m = _re.search(r'(\d+(?:\.\d+)?)', s)
    if not m:
        return None
    n = float(m.group(1))
    if 'year' in s or 'yr' in s or 'বছর' in s:
        return n * 12
    if 'week' in s or 'wk' in s or 'সপ্তাহ' in s:
        return n / 4.345
    if 'day' in s or 'দিন' in s:
        return n / 30.0
    return n  # assume months


def _dur_band(values):
    out = {l: 0 for l in _DUR_LABELS}
    for v in values:
        mo = _parse_duration_months(v)
        if mo is None:
            if v and str(v).strip():
                out['unparsed'] += 1
            continue
        if mo < 1:        out['<1mo'] += 1
        elif mo < 6:      out['1-6mo'] += 1
        elif mo < 12:     out['6-12mo'] += 1
        elif mo < 36:     out['1-3yr'] += 1
        else:             out['3yr+'] += 1
    return out


@api_view(['GET'])
@_drf_perms([IsAuthenticated])
def fistula_aggregates(request):
    """All 17 CIPRB Fistula Question Bank indicators, aggregated for the
    dashboard. Optional ?districts=A,B,C donor filter for parity with
    /api/mpdsr/aggregates/."""
    qs = CIPRBFistulaCase.objects.filter(approval_status='APPROVED')
    districts = request.GET.get('districts', '').strip()
    if districts:
        wanted = {d.strip().lower() for d in districts.split(',') if d.strip()}
        qs = qs.filter(district__in=[d for d in
                       qs.values_list('district', flat=True).distinct()
                       if d.lower() in wanted])

    # ── Monotonic pipeline from current_stage. A case at a later stage has
    #    passed through every earlier one, so the counts are cumulative and
    #    can NEVER violate suspected ≥ diagnosed ≥ referred ≥ repaired ≥
    #    rehabilitated. This is the single source of truth for the funnel and
    #    the At-a-glance KPI band (replacing the legacy dual-source split that
    #    produced the suspected=0 / diagnosed=6 contradiction).
    ORDER = ['suspected', 'diagnosed', 'referred', 'repaired', 'rehabilitated']
    stage_counts = dict(_Counter(qs.values_list('current_stage', flat=True)))
    pipeline = {}
    for i, st in enumerate(ORDER):
        pipeline[st] = sum(stage_counts.get(s, 0) for s in ORDER[i:])

    ages   = list(qs.values_list('age', flat=True))
    aam    = list(qs.values_list('age_at_marriage', flat=True))
    aafd   = list(qs.values_list('age_at_first_delivery', flat=True))
    nchild = list(qs.values_list('number_of_children', flat=True))

    # ind 10 — select_multiple stored pipe/space-separated.
    reasons = _Counter()
    for raw in qs.exclude(reasons_no_institutional_delivery='').values_list(
            'reasons_no_institutional_delivery', flat=True):
        for tok in _re.split(r'[|\s,]+', str(raw).strip()):
            if tok:
                reasons[tok] += 1

    # ── Case-registry coverage. This is how far the REGISTERED CASES reach; it
    #    is NOT campaign activity (see `campaign` below), and the two must never
    #    be relabelled into each other — that mix-up put case-funnel numbers
    #    under a "Fistula Campaign" heading (CIPRB meeting, 3 Aug 2026).
    campaign_reach = {
        'districts': qs.exclude(district='').values('district').distinct().count(),
        'upazilas': (qs.exclude(upazila='')
                       .values('district', 'upazila').distinct().count()),
        'patients': qs.count(),
    }

    # ── The ACTUAL community campaign: the daily CHW activity report
    #    (ciprb_fistula_campaign_v1 -> FistulaCampaign). Separate measure,
    #    separate denominator, separate source chip. Its own suspected/confirmed
    #    tallies are deliberately NOT merged into the case funnel (they are a
    #    field day-count, not the patient registry — merging double-counts).
    camp_qs = FistulaCampaign.objects.filter(approval_status='APPROVED')
    if districts:
        # Same ?districts= donor filter the case queryset above honours, so the
        # two panels always describe the same geography.
        camp_qs = camp_qs.filter(district__in=[
            d for d in camp_qs.values_list('district', flat=True).distinct()
            if d and d.lower() in wanted])
    camp_sum = camp_qs.aggregate(
        households=Sum('households_visited'),
        population=Sum('population_covered'),
        sessions=Sum('community_sessions'),
        suspected=Sum('suspected_fistula_cases'),
        confirmed=Sum('confirmed_fistula_cases'),
        referred=Sum('cases_referred'),
    )
    # Dot map, placed by REPORTED UPAZILA, not by raw GPS. The device GPS is
    # not trustworthy for this form: 30 of the 71 approved reports name a
    # Gaibandha upazila but carry Khagrachari coordinates (23.11 N vs
    # Gaibandha's real 25.3 N), and the whole set collapses onto 6 distinct
    # coordinates, so a raw-GPS plot draws one blob in the wrong district.
    # The district/upazila the field team types is internally consistent and
    # is what we place on. `gps_lat/lng` is the mean of whatever GPS the group
    # carried, kept only so the client can flag the disagreement.
    #
    # Grouping is on the CANONICAL name, not the raw string: one week of
    # submissions carries `Sadullahpur` and `Sadullapur`, `guimara` and
    # `Guimara`, and sometimes Bengali — raw grouping splits one upazila into
    # several dots and several table rows. The most frequent raw spelling is
    # what gets displayed; `spellings` keeps the variants visible so a genuine
    # data-entry problem is never hidden by the merge.
    by_upazila = []
    groups = {}
    for c in camp_qs:
        district = (c.district or '').strip()
        upazila = (c.upazila or '').strip()
        key = canon_pair(district, upazila)
        g = groups.setdefault(key, {
            'key': key, 'dkey': canon(district),
            'district': district, 'upazila': upazila, 'reports': 0,
            'households': 0, 'population': 0, 'suspected': 0,
            'confirmed': 0, 'referred': 0,
            '_lat': [], '_lng': [], 'dates': [], '_names': _Counter(),
            '_dnames': _Counter(),
        })
        g['_names'][upazila] += 1
        g['_dnames'][district] += 1
        g['reports'] += 1
        g['households'] += c.households_visited or 0
        g['population'] += c.population_covered or 0
        g['suspected'] += c.suspected_fistula_cases or 0
        g['confirmed'] += c.confirmed_fistula_cases or 0
        g['referred'] += c.cases_referred or 0
        if c.latitude is not None and c.longitude is not None:
            g['_lat'].append(float(c.latitude))
            g['_lng'].append(float(c.longitude))
        if c.campaign_date:
            g['dates'].append(c.campaign_date)
    for g in groups.values():
        lats, lngs, dates = g.pop('_lat'), g.pop('_lng'), g.pop('dates')
        names, dnames = g.pop('_names'), g.pop('_dnames')
        # Display the spelling the field team used most often.
        g['upazila'] = names.most_common(1)[0][0] if names else ''
        g['district'] = dnames.most_common(1)[0][0] if dnames else ''
        g['spellings'] = sorted(n for n in names if n)
        g['gps_lat'] = round(sum(lats) / len(lats), 6) if lats else None
        g['gps_lng'] = round(sum(lngs) / len(lngs), 6) if lngs else None
        g['gps_rows'] = len(lats)
        g['date_from'] = min(dates).isoformat() if dates else None
        g['date_to'] = max(dates).isoformat() if dates else None
        by_upazila.append(g)
    # ── Q1/Q2 paper-archive overlay (RCH request, confirmed 17 Aug 2026) ─────
    # Archive figures WIN for their upazila (CIPRB's signed compilation); live
    # daily rows stay authoritative only where the archive is silent. Rows are
    # tagged source/quarters so the map and table can label provenance.
    from django.conf import settings as _settings
    from .campaign_archive import CAMPAIGN_ARCHIVE
    from collections import defaultdict
    _archive_on = getattr(_settings, 'FISTULA_CAMPAIGN_ARCHIVE', True)
    _archive_rows = CAMPAIGN_ARCHIVE if _archive_on else []
    arch = defaultdict(lambda: {'quarters': set(), 'households': 0,
                                'population': 0, 'suspected': 0,
                                'sessions': 0, 'reports': 0,
                                'dates': [], 'district': '', 'upazila': ''})
    for a in _archive_rows:
        k = canon_pair(a['district'], a['upazila'])
        g = arch[k]
        g['quarters'].add(a['quarter'])
        g['district'], g['upazila'] = a['district'], a['upazila']
        g['households'] += a['households'] or 0
        g['population'] += a['population'] or 0
        g['suspected'] += a['suspected'] or 0
        g['sessions'] += (a['awareness'] or 0) + (a['courtyard'] or 0)
        g['reports'] += 1
        for d in (a['start'], a['end']):
            if d: g['dates'].append(d)
    live_by_key = {g['key']: g for g in by_upazila}
    for k, a in arch.items():
        row = live_by_key.get(k)
        if row is None:
            row = {'key': k, 'dkey': canon(a['district']),
                   'district': a['district'], 'upazila': a['upazila'],
                   'reports': 0, 'spellings': [a['upazila']],
                   'gps_lat': None, 'gps_lng': None, 'gps_rows': 0,
                   'confirmed': 0, 'referred': 0,
                   'date_from': None, 'date_to': None}
            by_upazila.append(row)
        row['households'] = a['households']
        row['population'] = a['population']
        row['suspected'] = a['suspected']
        row['source'] = 'archive'
        row['quarters'] = sorted(a['quarters'])
        row['date_from'] = min(a['dates']) if a['dates'] else row.get('date_from')
        row['date_to'] = max(a['dates']) if a['dates'] else row.get('date_to')
    for g in by_upazila:
        g.setdefault('source', 'live')
        g.setdefault('quarters', [])
    # Totals now come from the merged rows so tiles, map and table agree.
    camp_sum['households'] = sum(g['households'] or 0 for g in by_upazila)
    camp_sum['population'] = sum(g['population'] or 0 for g in by_upazila)
    camp_sum['suspected'] = sum(g['suspected'] or 0 for g in by_upazila)
    camp_sum['sessions'] = ((camp_sum['sessions'] or 0)
                            + sum(a['sessions'] for a in arch.values()))
    by_upazila.sort(key=lambda g: (-(g['population'] or 0),
                                   g['district'], g['upazila']))
    dates = [c for c in camp_qs.values_list('campaign_date', flat=True) if c]
    campaign = {
        'reports': camp_qs.count(),
        # Counted on the CANONICAL name, so the tile and the map agree. Raw
        # DISTINCT would say 8 upazilas while the map draws 6 dots, because
        # `Sadullahpur`/`Sadullapur` and `guimara`/`Guimara` are each one place.
        'districts': len({g['dkey'] for g in by_upazila if g['dkey']}),
        'upazilas': len([g for g in by_upazila if g['upazila']]),
        'households': camp_sum['households'] or 0,
        'population': camp_sum['population'] or 0,
        'sessions': camp_sum['sessions'] or 0,
        'suspected': camp_sum['suspected'] or 0,
        'confirmed': camp_sum['confirmed'] or 0,
        'referred': camp_sum['referred'] or 0,
        'date_from': min(dates).isoformat() if dates else None,
        'date_to': max(dates).isoformat() if dates else None,
        'by_upazila': by_upazila,
        'archive_rows': _archive_rows,
    }

    # ── The campaign funnel, per district (RCH, 2 Sep 2026) ──────────────────
    #    The CHW activity form records only `suspected`. Diagnosed, referred,
    #    repaired and rehabilitated exist nowhere but the case registry, so
    #    those four are read from `qs` and scoped to the districts the campaign
    #    actually worked in.
    #
    #    The CHW suspected tally is carried alongside as its own column and is
    #    deliberately NOT folded in as the funnel's first stage. A CHW day-count
    #    and a registered patient are different units; merging them is what put
    #    two denominators under one heading and drew the CIPRB complaint on
    #    3 Aug 2026. Both numbers are shown, each labelled with its source.
    camp_names = {}
    chw_suspected = {}
    for g in by_upazila:
        d = (g.get('district') or '').strip()
        if not d:
            continue
        k = d.lower()
        camp_names.setdefault(k, d)
        chw_suspected[k] = chw_suspected.get(k, 0) + (g.get('suspected') or 0)

    stage_by_district = _Counter()
    for d, st in qs.values_list('district', 'current_stage'):
        k = (d or '').strip().lower()
        if k in camp_names:
            stage_by_district[(k, st)] += 1

    camp_by_district = []
    for k in camp_names:
        row = {'district': camp_names[k], 'chw_suspected': chw_suspected.get(k, 0)}
        # Same monotonic rule as the national pipeline: a case at a later stage
        # has passed through every earlier one, so suspected >= diagnosed >=
        # referred >= repaired >= rehabilitated can never be violated.
        for i, st in enumerate(ORDER):
            row[st] = sum(stage_by_district.get((k, s), 0) for s in ORDER[i:])
        camp_by_district.append(row)
    camp_by_district.sort(key=lambda r: (-r['suspected'], -r['chw_suspected'],
                                         r['district']))

    # Districts are disjoint, so summing the per-district cumulative counts
    # gives the same national figures the strip needs.
    campaign['funnel'] = {st: sum(r[st] for r in camp_by_district)
                          for st in ORDER}
    campaign['funnel']['chw_suspected'] = sum(chw_suspected.values())
    campaign['by_district'] = camp_by_district

    # ── Treatment cost. CIPRB pays the whole cost of a fistula patient's
    #    treatment, so these are NOT out-of-pocket figures (which by definition
    #    are what the household pays); they are the actual cost per patient
    #    borne by the project. The question they exist to answer is whether the
    #    BDT 10,000-12,000 per patient the project budgets matches reality.
    #    (Dr Tanjina Pervin, RCH CIPRB, 9 September 2026.)
    BUDGET_LOW, BUDGET_HIGH = 10000, 12000
    cost_rows = list(CIPRBFistulaCaseCost.objects
                     .filter(case__in=qs)
                     .values('case_id', 'cost_point', 'amount_disbursed',
                             'medical_cost', 'investigation_cost', 'ot_cost',
                             'travel_cost', 'food_cost', 'other_cost'))
    HEADS = [('medical_cost', 'Medical'), ('investigation_cost', 'Investigation'),
             ('ot_cost', 'OT'), ('travel_cost', 'Travel'),
             ('food_cost', 'Food'), ('other_cost', 'Others')]

    by_head = []
    for fld, label in HEADS:
        vals = [r[fld] for r in cost_rows if r[fld] is not None]
        by_head.append({'head': label, 'total': sum(vals), 'entries': len(vals)})

    def _row_total(r):
        return sum(r[f] or 0 for f, _ in HEADS)

    per_patient = _Counter()
    for r in cost_rows:
        per_patient[r['case_id']] += _row_total(r)

    repair_totals = [_row_total(r) for r in cost_rows
                     if r['cost_point'] == 'repaired']
    patient_totals = sorted(per_patient.values())
    grand_total = sum(patient_totals)

    # Only patients with a figure recorded are averaged. Dividing by every
    # registered woman would report an average that no one actually spent.
    n_patients = len(patient_totals)

    # ── Released against spent. CIPRB does not pay the facility: a District
    #    Coordinator releases the money to the woman and she settles the bill,
    #    and CIPRB transacts the total. So the programme's real financial
    #    control question is not only "what did it cost" but "does what we
    #    released match what was spent", which is what CIPRB's ledger has to
    #    reconcile against. Only episodes with a disbursement recorded are
    #    counted, so an unrecorded release is never read as a zero release.
    disb_rows = [r for r in cost_rows if r['amount_disbursed'] is not None]
    total_disbursed = sum(r['amount_disbursed'] for r in disb_rows)
    spent_where_disbursed = sum(_row_total(r) for r in disb_rows)
    vs_disbursed = {'matched': 0, 'underspent': 0, 'overspent': 0}
    for r in disb_rows:
        gap = r['amount_disbursed'] - _row_total(r)
        key = ('matched' if gap == 0
               else 'underspent' if gap > 0 else 'overspent')
        vs_disbursed[key] += 1

    cost = {
        'episodes_with_disbursement': len(disb_rows),
        'total_disbursed': total_disbursed,
        'spent_where_disbursed': spent_where_disbursed,
        # Positive = money released but not spent (returnable). Negative =
        # spent beyond what was released, which someone absorbed.
        'balance': total_disbursed - spent_where_disbursed,
        'vs_disbursed': vs_disbursed,
        'entries': len(cost_rows),
        'patients_costed': n_patients,
        'total_bdt': grand_total,
        'avg_per_patient': round(grand_total / n_patients) if n_patients else 0,
        'median_per_patient': (patient_totals[n_patients // 2]
                               if n_patients else 0),
        'avg_per_operation': (round(sum(repair_totals) / len(repair_totals))
                              if repair_totals else 0),
        'operations_costed': len(repair_totals),
        'by_head': by_head,
        'budget_low': BUDGET_LOW,
        'budget_high': BUDGET_HIGH,
        # How the reality sits against the allocation. This is the whole point
        # of collecting the figures, so it is computed here rather than left
        # for the frontend to guess at.
        'vs_budget': {
            'under': sum(1 for t in patient_totals if t < BUDGET_LOW),
            'within': sum(1 for t in patient_totals
                          if BUDGET_LOW <= t <= BUDGET_HIGH),
            'over': sum(1 for t in patient_totals if t > BUDGET_HIGH),
        },
        'basis': ('Actual cost per patient, borne by the project. A District '
                  'Coordinator releases the money to the patient and she '
                  'settles the bill with it, so the household spends nothing '
                  'of its own: these are not out-of-pocket figures. Budget '
                  f'allocation is BDT {BUDGET_LOW:,}-{BUDGET_HIGH:,} per '
                  'patient.'),
    }

    return Response({
        'total': qs.count(),
        'pipeline': pipeline,
        'cost': cost,
        'campaign_reach': campaign_reach,
        'campaign': campaign,
        'age': _fis_band(ages, [(0,18),(18,25),(25,35),(35,45),(45,200)],
                         ['<18','18-24','25-34','35-44','45+']),                       # 1
        'education': _fis_count(qs, 'education'),                                       # 2
        'marital_status': _fis_count(qs, 'marital_status'),                            # 3
        'age_at_marriage': _fis_band(aam, [(0,15),(15,18),(18,21),(21,200)],
                                     ['<15','15-17','18-20','21+']),                    # 4
        'age_at_first_delivery': _fis_band(aafd, [(0,16),(16,19),(19,22),(22,200)],
                                           ['<16','16-18','19-21','22+']),              # 5
        'number_of_children': _fis_band(nchild, [(0,1),(1,2),(2,3),(3,4),(4,200)],
                                        ['0','1','2','3','4+']),                        # 6
        'mode_of_last_delivery': _fis_count(qs, 'mode_of_last_delivery'),              # 7
        'place_of_last_delivery': _fis_count(qs, 'place_of_last_delivery'),            # 8
        'conducted_last_delivery': _fis_count(qs, 'conducted_last_delivery'),          # 9
        'reasons_no_institutional_delivery': dict(reasons),                            # 10
        'time_duration_fistula_occurrence': _dur_band(
            qs.values_list('time_duration_fistula_occurrence', flat=True)),            # 11
        'duration_suffering': _dur_band(
            qs.values_list('duration_suffering', flat=True)),                          # 12
        'delivery_outcome': _fis_count(qs, 'delivery_outcome'),                        # 13
        # 14 + 16 — MERGE spelling variants, but onto the canonical CODE, not
        # an English label. 'iterogenic' was rendering as its own slice beside
        # the correctly spelled 'Iatrogenic', inventing a fistula type that
        # does not exist. Codes are kept because the Fistula Corner charts are
        # keyed on them (PIE_COLORS['obstetric'], GENITAL_TYPES 'vvf'/'rvf');
        # relabelling here emptied both of those charts.
        'fistula_type_v2': canonicalise('fistula_type',
                                        _fis_count(qs, 'fistula_type_v2')),            # 14
        'iatrogenic_cause': _fis_count(
            qs.filter(fistula_type_v2='iatrogenic'), 'iatrogenic_cause'),              # 15
        'genital_fistula_type': canonicalise(
            'genital_fistula_type', _fis_count(qs, 'genital_fistula_type')),           # 16
        'surgery_outcome_v2': _fis_count(qs, 'surgery_outcome_v2'),                    # 17
        # The outcome breakdown is captioned "of all surgically repaired
        # patients" but only counts cases that HAVE an outcome recorded (27),
        # while the funnel headline says 35 repaired. Ship the denominator so
        # the gap reads as "outcome not yet recorded" instead of as a
        # contradiction between two numbers on the same page.
        'surgery_outcome_coverage': {
            'recorded': sum(_fis_count(qs, 'surgery_outcome_v2').values()),
            'repaired_total': pipeline['repaired'],
            'pending': max(0, pipeline['repaired']
                           - sum(_fis_count(qs, 'surgery_outcome_v2').values())),
        },
    })
