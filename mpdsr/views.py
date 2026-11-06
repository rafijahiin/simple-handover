import datetime

from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from accounts.permissions import CanAccessMPDSR, OrgFilterMixin
from .models import (
    DeathType, MPDSRCase, ReviewStatus,
    MPDSRDistrictDenominator, MPDSRFacilityCount, MPDSRActionPlanSummary,
)
from .code_labels import band_pnc, band_time_of_death, relabel
from .serializers import MPDSRCaseSerializer, MPDSRCaseUpdateSerializer


class MPDSRCaseViewSet(OrgFilterMixin, ModelViewSet):
    queryset = MPDSRCase.objects.select_related('submission', 'created_by').filter(approval_status='APPROVED')
    # MPDSR is CIPRB-owned per the IDMS handoff. PHD + Bandhu managers
    # lose access here; only Dev, Supervisor, and CIPRB Org Lead see records.
    permission_classes = [CanAccessMPDSR]
    http_method_names = ['get', 'head', 'options', 'patch']
    org_field = 'partner'

    def get_queryset(self):
        qs = super().get_queryset()
        partner = self.request.query_params.get('partner')
        cause = self.request.query_params.get('cause_of_death')
        date_from = self.request.query_params.get('from')
        date_to = self.request.query_params.get('to')
        if partner and self.request.user.can_see_all_orgs:
            qs = qs.filter(partner=partner)
        if cause:
            qs = qs.filter(cause_of_death=cause)
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
        # Hide stillbirth review sub-forms (F3, F6) from the dashboard
        # — Animesh decision in the 2026-06-01 meeting. Records stay in DB
        # for audit, just don't surface in API responses.
        qs = qs.exclude(sub_form_type__in=['f3', 'f6'])
        # Reporting-period filter — CIPRB Dashboard reporting-period toggle
        # passes ?from=YYYY-MM-DD&to=YYYY-MM-DD.
        #
        # This filters on WHEN THE CASE ENTERED SURVEILLANCE (created_at), not on
        # date_of_death. MPDSR reviews deaths retrospectively: fieldwork began in
        # June 2026 and reviewed deaths back to January, so of 62 approved cases
        # only 3 had a death date inside the contract window (21 May → 20 Nov) —
        # the old date_of_death filter blanked every visualization on the CIPRB
        # dashboard (cause-of-death, reporting rate, review pipeline) while the
        # data sat in the database. A January death reviewed in July IS
        # contract-period output; date_of_death remains on each case for the
        # event-date views.
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return MPDSRCaseUpdateSerializer
        return MPDSRCaseSerializer

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        old_status = instance.status

        serializer = MPDSRCaseUpdateSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data.get('status', old_status)

        serializer.save()

        if new_status != old_status:
            instance.add_audit_entry(
                user_email=request.user.email,
                action=f'Status changed: {old_status} → {new_status}',
                notes=serializer.validated_data.get('notes', ''),
            )
            instance.save(update_fields=['audit_trail'])

        return Response(MPDSRCaseSerializer(instance).data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        qs = self.get_queryset()
        today = datetime.date.today()
        month_start = today.replace(day=1)

        by_status = {
            status: qs.filter(status=status).count()
            for status in ReviewStatus.values
        }
        by_death_type = {
            dt: qs.filter(death_type=dt).count()
            for dt in DeathType.values
        }
        overdue_committee = qs.filter(
            committee_date__lt=today,
            committee_date__isnull=False,
        ).exclude(status=ReviewStatus.CLOSED).count()

        return Response({
            'total': qs.count(),
            'by_status': by_status,
            'by_death_type': by_death_type,
            'overdue_committee': overdue_committee,
            'this_month': qs.filter(date_of_death__gte=month_start).count(),
        })


# ─── Aggregate endpoint feeding the CIPRB Dashboard visualizations ───────────


@api_view(['GET'])
@drf_permission_classes([IsAuthenticated, CanAccessMPDSR])
def mpdsr_aggregates(request):
    """One endpoint, one shot — returns everything the CIPRB Dashboard needs
    for the visualizations Animesh asked for:

    {
      "denominators": [ { district, project_deaths_md, ... }, ... ],
      "facility_counts": [ { district, facility_name, fdn_md, fdr_md, ... }, ... ],
      "facility_totals": { fdn_md, fdr_md, fdn_nd, fdr_nd, ... },
      "action_plan_summaries": [ { district, level, planned, executed, pct }, ... ],
      "totals": { mpdsr_cases, fistula_corner_cases, fistula_campaign_visits }
    }
    """
    from fistula.models import FistulaCornerCase, FistulaCampaignVisit
    from django.db.models import Sum, Q
    from .ciprb_models import MPDSRDeathNotification

    # Donor filter — comma-separated district list from the pill.
    districts_param = request.query_params.get('districts')
    district_names = None
    if districts_param:
        district_names = [n.strip() for n in districts_param.split(',') if n.strip()]

    def apply_donor(qs, field='district'):
        if not district_names:
            return qs
        q = Q()
        for n in district_names:
            q |= Q(**{f'{field}__iexact': n})
        return qs.filter(q)

    denom_qs = apply_donor(MPDSRDistrictDenominator.objects.all())
    denominators = list(
        denom_qs.values(
            'district', 'project_deaths_md', 'project_deaths_nd', 'project_deaths_sb',
        )
    )

    facility_qs = apply_donor(MPDSRFacilityCount.objects.all())
    facility_counts = list(
        facility_qs.values(
            'district', 'facility_name', 'period',
            'fdn_md', 'fdn_nd', 'fdn_sb', 'fdr_md', 'fdr_nd', 'fdr_sb',
        )
    )
    # MPDSRFacilityCount holds the per-facility aggregate counts ingested from
    # Sayeed's Excel reporting sheet. When that import has not run the table is
    # empty and .aggregate() returns a dict of Nones — a dict that is still
    # TRUTHY. The frontend guards with `totals ? excelNumbers : liveCounts`
    # ("falls back to live-only counts if the import hasn't run"), so an
    # all-empty dict silently defeated its own fallback and the Notified-vs-
    # Reviewed panel rendered zeros instead of the real Kobo numbers. Return
    # None when there is nothing in the table so that fallback actually fires.
    facility_totals = facility_qs.aggregate(
        cdn_md=Sum('cdn_md'), cdn_nd=Sum('cdn_nd'), cdn_sb=Sum('cdn_sb'),
        fdn_md=Sum('fdn_md'), fdn_nd=Sum('fdn_nd'), fdn_sb=Sum('fdn_sb'),
        fdr_md=Sum('fdr_md'), fdr_nd=Sum('fdr_nd'), fdr_sb=Sum('fdr_sb'),
    )
    if not any(v for v in facility_totals.values()):
        facility_totals = None

    # Notification by level (Animesh: "separated by Community / Facility").
    # CDN = community death notification, FDN = facility death notification.
    #
    # Preferred source is the Excel ingest above, because it covers the whole
    # programme rather than only what has come through Kobo. With that table
    # empty this panel showed 0 across all six cells while 86 real notification
    # slips sat in the database — so fall back to the live slips, counted the
    # same way the `notifications` block does (facility place = facility level,
    # home / in_transit / blank = community surveillance) and restricted to
    # APPROVED rows, per the rule that indicators count approved records only.
    def _ft(k):
        return int((facility_totals or {}).get(k) or 0)

    if facility_totals:
        notification_by_level = {
            'md': {'community': _ft('cdn_md'), 'facility': _ft('fdn_md')},
            'nd': {'community': _ft('cdn_nd'), 'facility': _ft('fdn_nd')},
            'sb': {'community': _ft('cdn_sb'), 'facility': _ft('fdn_sb')},
        }
        notification_by_level_source = 'excel'
    else:
        _nq = apply_donor(
            MPDSRDeathNotification.objects.filter(approval_status='APPROVED'))

        # CDN / FDN means WHICH SLIP WAS FILED: Slip 01 is the community death
        # notification (CHW-filed), Slip 02 the facility one. The first version
        # of this fallback classified by PLACE OF DEATH instead, which fabricated
        # the whole split: a mother who died at a hospital but was notified by a
        # CHW on Slip 01 is still a COMMUNITY notification, and Slip 02 does not
        # even carry a place field. Against the real slips the place-based split
        # showed stillbirths as 41 community / 2 facility when 41 of 43 sit on
        # the FACILITY slip — exactly backwards. Rafi caught it on the panel.
        def _lvl(kind):
            k = _nq.filter(death_kind=kind)
            return {
                'community': k.filter(slip_variant=MPDSRDeathNotification.SLIP_01).count(),
                'facility': k.filter(slip_variant=MPDSRDeathNotification.SLIP_02).count(),
            }

        notification_by_level = {
            'md': _lvl(MPDSRDeathNotification.KIND_MATERNAL),
            'nd': _lvl(MPDSRDeathNotification.KIND_NEONATAL),
            'sb': _lvl(MPDSRDeathNotification.KIND_STILLBIRTH),
        }
        notification_by_level_source = 'kobo'

    action_plan_summaries = []
    for a in apply_donor(MPDSRActionPlanSummary.objects.all()):
        action_plan_summaries.append({
            'district': a.district,
            'level': a.level,
            'place_of_meeting': a.place_of_meeting,
            'meeting_date': a.meeting_date,
            'participants': a.participants,
            'meetings_planned': a.meetings_planned,
            'activities_planned': a.activities_planned,
            'activities_implemented': a.activities_implemented,
            'completion_pct': a.completion_pct,
            'actions': a.actions or [],
            # Lets the frontend show the "interim placeholder" caveat only for
            # seed/Excel rows — real Kobo submissions (source kobo_response_plan)
            # carry true implemented counts, so the banner auto-hides for them.
            'source': a.source,
        })

    # ── Live per-action tracker (CIPRB-10 Action Plan → MPDSRAction) ──────────
    # One row per agreed action with its OWN completion %, so the dashboard can
    # show per-action progress + a true cumulative %. Distinct from the
    # Excel-sourced action_plan_summaries roll-up above.
    from mpdsr.models import MPDSRAction, STUB_ACTIVITY_SENTINEL
    mpdsr_actions = []
    for a in apply_donor(MPDSRAction.objects.filter(approval_status='APPROVED')
                         .exclude(activity=STUB_ACTIVITY_SENTINEL)):
        mpdsr_actions.append({
            'action_id': a.action_id,
            'district': a.district,
            'section': a.section,
            'section_label': a.get_section_display(),
            'sub_category': a.sub_category,
            'sub_category_label': a.sub_category_label,
            'activity': a.activity,
            'responsible': a.responsible,
            'timeline': a.timeline.isoformat() if a.timeline else None,
            'status': a.status,
            'status_label': a.get_status_display(),
            'completion_pct': a.completion_pct,
            'completion_date': a.completion_date.isoformat() if a.completion_date else None,
            'is_overdue': a.is_overdue,
        })

    # Exclude F3 / F6 stillbirth reviews from dashboard surface counts
    # (Animesh decision, 2026-06-01 meeting). Records remain in DB.
    mpdsr_qs = MPDSRCase.objects.filter(approval_status='APPROVED').exclude(sub_form_type__in=['f3', 'f6'])
    totals = {
        'mpdsr_cases': apply_donor(mpdsr_qs).count(),
        'fistula_corner_cases': apply_donor(FistulaCornerCase.objects.all()).count(),
        'fistula_campaign_visits': apply_donor(FistulaCampaignVisit.objects.all()).count(),
    }

    # Per-sub-form review counts (f1/f2/f4/f5/sa_md), donor-filtered.
    #
    # This block used to fabricate a key: `notified_md = f1 + f2` — the count of
    # maternal COMMUNITY REVIEWS plus NEONATAL community reviews, labelled "MD
    # notified". The frontend used it as the denominator of every review tile,
    # so the panel read "0 of 86 notified" where 86 was neither notifications
    # nor maternal. Notified counts come from the notification SLIPS
    # (notification_by_level above); reviews come from the review forms here.
    # The two must never be derived from each other.
    from django.db.models import Count
    md_donor_qs = apply_donor(mpdsr_qs)
    review_rows = (
        md_donor_qs.values('sub_form_type')
        .annotate(c=Count('id'))
    )
    review_counts = {r['sub_form_type']: r['c'] for r in review_rows}
    # The Social Autopsy tile is titled "(Maternal Death)" but the SA form also
    # re-reviews neonatal deaths (sa_death_type 2) — 3 of the 17 live autopsies
    # are neonatal. Give the tile a maternal-only count so its number matches
    # its own title and its MD-reviews denominator.
    review_counts['sa_md_maternal'] = md_donor_qs.filter(
        sub_form_type='sa_md', death_type=DeathType.MATERNAL).count()
    # Stillbirth reviews. None of the four structured review forms accepts a
    # stillbirth (F-02 has no stillbirth field, F-05 records live-born neonates
    # only), but the Social Autopsy form does — sa_death_type 3, মৃতজন্ম on the
    # paper tool. Ingest used to fold that into 'perinatal' and the dashboard
    # then had nowhere to put it, so 45 notified stillbirths looked unreviewed
    # by definition. Count them properly.
    review_counts['sb_reviewed'] = md_donor_qs.filter(
        sub_form_type='sa_md', sa_death_kind='stillbirth').count()

    # ── CIPRB dashboard "major indicators" (11) — per-case breakdowns from
    #    the donor-filtered maternal cohort (Form 01 community + Form 04
    #    facility). Categorical counts + integer histograms. Existing keys
    #    unchanged → no frontend regression.
    from collections import Counter as _Counter

    # The 11 MPDSR indicators are MATERNAL-death indicators sourced from
    # Form 01 (community, f1) + Form 04 (facility, f4) per the CIPRB spec.
    # Restrict to that cohort so every indicator counts the SAME cases:
    #  - death_type=maternal  → drop neonatal (f2/f5)
    #  - sub_form_type in f1/f4 → drop Social Autopsy (sa_md, a re-review,
    #    not a distinct death) and any historical verbal-autopsy import
    #  This is what makes Place-of-Death consistent with the other 10
    #  (previously it counted the whole cohort and showed ~495 vs ~18).
    ind_qs = md_donor_qs.filter(
        death_type=DeathType.MATERNAL,
        sub_form_type__in=['f1', 'f4'],
    )

    def _cnt(field):
        return dict(_Counter(
            ind_qs.exclude(**{field: ''}).values_list(field, flat=True)))

    def _band(field, edges, labels):
        vals = [v for v in ind_qs.values_list(field, flat=True) if v is not None]
        out = {l: 0 for l in labels}
        for v in vals:
            for (lo, hi), l in zip(edges, labels):
                if lo <= v < hi:
                    out[l] += 1
                    break
        return out

    # Decode raw choice codes to readable labels HERE, at the aggregate, so
    # every consumer (dashboard, monthly report, export) gets one clean
    # vocabulary. Rendering these raw is what put 'doctor_mbbs', 'upazila_hc'
    # and 'vaginal_spontaneous' in front of CIPRB and UNFPA, and what split one
    # clinical fact across two slices ('normal' beside 'vaginal_spontaneous').
    # See mpdsr/code_labels.py; mpdsr/test_code_labels.py stops it drifting
    # from the deployed forms.
    indicators = {
        'place_of_death':           relabel('place_of_death',
                                            _cnt('place_of_death')),   # 1
        # Stored as a clock time, not a phase of pregnancy: charting it raw
        # produced 46 individual timestamps at 2% each.
        'time_of_death':            band_time_of_death(
                                        _cnt('time_of_death')),        # 2
        'gestational_weeks':        _band('gestational_weeks',
            [(0, 28), (28, 34), (34, 37), (37, 42), (42, 99)],
            ['<28', '28-33', '34-36', '37-41', '42+']),                # 3
        'anc_visits_count':         relabel('anc_visits_count',
                                            _cnt('anc_visits_count')), # 4
        # A VISIT COUNT, never a yes/no. The old yes/no tile is what reported
        # "Received: 0 of 22" while its own breakdown showed 19 women with at
        # least one visit.
        'pnc_received':             band_pnc(_cnt('pnc_received')),    # 5 (PNC)
        'mode_of_delivery':         relabel('mode_of_delivery',
                                            _cnt('mode_of_delivery')), # 6
        'delivery_outcome':         relabel('delivery_outcome',
                                            _cnt('delivery_outcome')), # 7
        'place_of_delivery':        relabel('place_of_delivery',
                                            _cnt('place_of_delivery')),# 8
        'person_assisted_delivery': relabel('person_assisted_delivery',
                                            _cnt('person_assisted_delivery')),  # 9
        'maternal_age': _band('age_years',
            [(0, 20), (20, 25), (25, 30), (30, 35), (35, 40), (40, 45), (45, 99)],
            ['<20', '20-24', '25-29', '30-34', '35-39', '40-44', '45+']),  # 10
        'time_death_after_birth_hours': _band('time_death_after_birth_hours',
            [(0, 24), (24, 48), (48, 168), (168, 99999)],
            ['0-24h', '24-48h', '2-7d', '7d+']),                       # 11
    }

    # ── Facility (Form 04) deep-dive — the facility maternal-death form
    #    carries richer review data than the community form. Two extra
    #    breakdowns surfaced next to the facility cause donut:
    #      (a) admission→death interval — care-timeliness signal
    #      (b) facility review committee progress + action-plan coverage
    fac_qs = md_donor_qs.filter(
        death_type=DeathType.MATERNAL, sub_form_type='f4',
    )

    # (a) admission→death interval. days = date_of_death - admission_date.
    _adm_labels = ['<1 day', '1-2 days', '3-7 days', '7+ days']
    admission_to_death = {l: 0 for l in _adm_labels}
    admission_to_death['Unknown'] = 0
    for adm, dod in fac_qs.values_list('admission_date', 'date_of_death'):
        if not adm or not dod:
            admission_to_death['Unknown'] += 1
            continue
        days = (dod - adm).days
        if days < 1:      admission_to_death['<1 day'] += 1
        elif days < 3:    admission_to_death['1-2 days'] += 1
        elif days < 8:    admission_to_death['3-7 days'] += 1
        else:             admission_to_death['7+ days'] += 1

    # (b) review committee progress (status distribution) + action-plan reach.
    review_status_dist = dict(_Counter(fac_qs.values_list('status', flat=True)))
    fac_total = fac_qs.count()
    with_plan = fac_qs.exclude(action_plan='').count()
    facility = {
        'total': fac_total,
        'admission_to_death': admission_to_death,
        'review_status': review_status_dist,
        'action_plan_coverage': {
            'with_plan': with_plan,
            'without_plan': fac_total - with_plan,
        },
    }

    # ── Phase 2 gap charts — forms that feed the DB but had no dashboard
    #    surface yet: neonatal deaths (CIPRB 3 community + CIPRB 5 facility),
    #    death notification slips (CIPRB 7 + 8), and Social Autopsy (CIPRB 6).
    #    All additive — existing keys above are untouched.

    # (1) Neonatal deaths — community (f2) + facility (f5) review forms.
    #     death_type='perinatal' is the canonical neonatal/perinatal cohort.
    #     cause_of_death stores the raw `cod_neonatal` slug (preterm_lbw /
    #     asphyxia / sepsis / pneumonia / congenital / diarrhoea / other /
    #     unknown). Anything unrecognised folds into 'unknown' so the donut
    #     never grows a stray slice.
    _NEO_CAUSES = [
        'preterm_lbw', 'asphyxia', 'sepsis', 'pneumonia',
        'congenital', 'diarrhoea', 'other', 'unknown',
    ]
    neo_qs = apply_donor(mpdsr_qs).filter(death_type=DeathType.PERINATAL)

    def _neo_bucket(raw):
        s = (raw or '').strip().lower()
        if not s:
            return 'unknown'
        if s in _NEO_CAUSES:
            return s
        # Forgive verbose strings (e.g. "Neonatal sepsis", "Birth asphyxia").
        for key in _NEO_CAUSES:
            if key != 'other' and key.split('_')[0] in s:
                return key
        return 'other'

    neo_cause = {c: 0 for c in _NEO_CAUSES}
    for raw in neo_qs.values_list('cause_of_death', flat=True):
        neo_cause[_neo_bucket(raw)] += 1
    # Community (f2) vs facility (f5) split — the two source forms.
    neo_level = {
        'community': neo_qs.filter(sub_form_type='f2').count(),
        'facility': neo_qs.filter(sub_form_type='f5').count(),
    }
    # ── RCH review additions (confirmed by Dr. Tanjina, 17 Aug 2026) ────────
    # B7: period of maternal death (Form 01 Q2 `death_period`). Not a
    # normalised column — read from the raw payload (flat key or group path).
    _DEATH_PERIOD = [
        ('pregnancy', 'During pregnancy'),
        ('post_abortion_28w', 'After abortion'),
        ('delivery', 'During delivery'),
        ('postpartum_42d', 'After delivery'),
    ]
    _DP_MAP = dict(_DEATH_PERIOD)

    def _payload_leaf(rp, leaf):
        if not isinstance(rp, dict):
            return ''
        v = rp.get(leaf)
        if v in (None, ''):
            for k, kv in rp.items():
                if str(k).split('/')[-1] == leaf:
                    v = kv
                    break
        return str(v or '').strip()

    death_period = {lbl: 0 for _, lbl in _DEATH_PERIOD}
    death_period['Unknown'] = 0
    for rp in ind_qs.values_list('raw_payload', flat=True):
        death_period[_DP_MAP.get(_payload_leaf(rp, 'death_period'),
                                 'Unknown')] += 1
    indicators['death_period'] = death_period

    # B5: how many MPDSR review records each district has contributed.
    records_by_district = dict(sorted(
        _Counter(apply_donor(mpdsr_qs).exclude(district='')
                 .values_list('district', flat=True)).items(),
        key=lambda kv: -kv[1]))

    # B9: newborn danger signs (Form 05 Q11, select_multiple — codes are
    # space-separated in the payload). Codes per the verbatim form.
    _DANGER = {
        'body_arching': 'Body arching / stiffening',
        'not_feeding': 'Not feeding / refuses to feed',
        'fast_breathing': 'Fast breathing',
        'fast_breathing_chest_indraw': 'Fast breathing with chest indrawing',
        'cold_extremities': 'Cold hands and feet',
        'fever': 'Fever',
        'no_movement': 'No or reduced movement',
        'jaundice': 'Jaundice',
        'umbilical_infection': 'Red / discharging umbilicus',
        'skin_pustules': 'Skin pustules / boils',
        'diarrhoea': 'Diarrhoea',
        'dont_know': "Don't know",
        'other': 'Other',
    }
    f5_qs = neo_qs.filter(sub_form_type='f5')
    danger_signs = {lbl: 0 for lbl in _DANGER.values()}
    for rp in f5_qs.values_list('raw_payload', flat=True):
        for code in _payload_leaf(rp, 'danger_signs').split():
            if code in _DANGER:
                danger_signs[_DANGER[code]] += 1
    danger_signs = {k: v for k, v in danger_signs.items() if v}

    # B10: place of neonatal death (Form 05 Q1) — normalised column, shared
    # relabel vocabulary.
    neo_place = relabel('place_of_death', dict(_Counter(
        f5_qs.exclude(place_of_death='')
        .values_list('place_of_death', flat=True))))

    neonatal = {
        'total': neo_qs.count(),
        'cause_of_death': neo_cause,
        'by_level': neo_level,
        'danger_signs': danger_signs,
        'place_of_death': neo_place,
    }

    # (2) Death notifications — slips 01 + 02 (MPDSRDeathNotification).
    #     By death type (maternal/neonatal/stillbirth), by LEVEL (= which slip
    #     was filed: Slip 01 = community/CDN, Slip 02 = facility/FDN — NOT place
    #     of death; see the split below and SEMANTICS.md "CDN/FDN"), and by
    #     district.
    notif_qs = apply_donor(MPDSRDeathNotification.objects.filter(approval_status='APPROVED'))
    notif_by_kind = dict(_Counter(
        notif_qs.exclude(death_kind='').values_list('death_kind', flat=True)))
    # Level = WHICH SLIP was filed (Slip 01 = community/CDN, Slip 02 =
    # facility/FDN). Place of death is a separate attribute of the death, not
    # of the notification: the place-based split this block used to make put a
    # hospital death notified by a CHW under "facility" and all 41 Slip-02
    # stillbirths under "community" (Slip 02 carries no place field at all).
    notif_community = notif_qs.filter(
        slip_variant=MPDSRDeathNotification.SLIP_01).count()
    notif_facility = notif_qs.filter(
        slip_variant=MPDSRDeathNotification.SLIP_02).count()
    notif_by_district = dict(_Counter(
        notif_qs.exclude(district='').values_list('district', flat=True)))
    notifications = {
        'total': notif_qs.count(),
        'by_kind': notif_by_kind,
        'by_level': {'community': notif_community, 'facility': notif_facility},
        'by_district': notif_by_district,
    }

    # ── Maternal notification against the year's projection, per district ────
    #    RCH's ask (Dr Tanjina, 6 Sep 2026): show each district's reported
    #    maternal deaths beside what 2026 is projected to produce there, so a
    #    reader can see reporting performance rather than only volume.
    #
    #    The numerator is the notification slip, not the review. A death can
    #    carry a community review and a facility review, so counting reviews
    #    would report some districts at over a hundred per cent for the wrong
    #    reason. The slip is filed once per death, and "reported" is what the
    #    request asks for.
    #
    #    The denominator is a FULL YEAR projection. The percentage is
    #    therefore against the whole of 2026 regardless of how much of the year
    #    has run, and the payload says so rather than leaving the reader to
    #    assume it is a year-to-date figure.
    #    Scoped to the CIPRB working districts. RCH's projection file also
    #    covers districts CIPRB does not work in (Bogura, Rajshahi), and those
    #    would have read as reporting failures when they are simply outside
    #    the programme.
    from .ciprb_districts import is_ciprb_district

    md_slip_qs = apply_donor(
        MPDSRDeathNotification.objects.filter(approval_status='APPROVED',
                                              death_kind='maternal'))
    md_reported = _Counter(
        d.strip() for d in md_slip_qs.values_list('district', flat=True)
        if d and is_ciprb_district(d))
    projected = {}
    for row in MPDSRDistrictDenominator.objects.exclude(
            project_deaths_md__isnull=True).values('district', 'project_deaths_md'):
        if is_ciprb_district(row['district']):
            projected[row['district'].strip().lower()] = row['project_deaths_md']

    maternal_reporting = []
    for district, reported in md_reported.items():
        proj = projected.get(district.lower())
        maternal_reporting.append({
            'district': district,
            'reported': reported,
            'projected': proj,
            'pct': round((reported / proj) * 100, 1) if proj else None,
        })
    # Districts with a projection but nothing reported are the point of the
    # panel, so they are listed too rather than silently dropped.
    seen = {d.lower() for d in md_reported}
    for row in MPDSRDistrictDenominator.objects.exclude(
            project_deaths_md__isnull=True).values('district', 'project_deaths_md'):
        name = row['district'].strip()
        if name.lower() in seen or not is_ciprb_district(name):
            continue
        if district_names and name.lower() not in {d.lower() for d in district_names}:
            continue
        maternal_reporting.append({'district': name, 'reported': 0,
                                   'projected': row['project_deaths_md'], 'pct': 0.0})
    maternal_reporting.sort(key=lambda r: (r['pct'] is None, -(r['pct'] or 0),
                                           -r['reported']))

    # (3) Social Autopsy (sa_md). The paper form reviews maternal deaths,
    #     neonatal deaths AND stillbirths (sa_death_type 1/2/3), so the whole
    #     sa_md cohort is NOT "social autopsy of maternal deaths". This block
    #     used to return that whole cohort while the tile above counted only
    #     the maternal ones, which is why the same page showed 15 in one place
    #     and 18 in another with nothing to explain the difference.
    #     Report maternal as the headline (matching the tile and the section
    #     title) and give the other kinds their own counts so none is hidden.
    sa_all_qs = apply_donor(mpdsr_qs).filter(sub_form_type='sa_md')
    sa_qs = sa_all_qs.filter(death_type=DeathType.MATERNAL)
    sa_place = dict(_Counter(
        sa_qs.exclude(place_of_death='').values_list('place_of_death', flat=True)))
    social_autopsy = {
        'total': sa_qs.count(),
        'place_of_death': relabel('place_of_death', sa_place),
        # Every social autopsy, whatever it reviewed. maternal + neonatal +
        # stillbirth + unclassified == all_kinds_total, by construction.
        'all_kinds_total': sa_all_qs.count(),
        'by_kind': {
            'maternal': sa_qs.count(),
            'neonatal': sa_all_qs.filter(sa_death_kind='neonatal').count(),
            'stillbirth': sa_all_qs.filter(sa_death_kind='stillbirth').count(),
            'unclassified': sa_all_qs.exclude(
                death_type=DeathType.MATERNAL).exclude(
                sa_death_kind__in=['neonatal', 'stillbirth']).count(),
        },
    }

    return Response({
        'denominators': denominators,
        'facility_counts': facility_counts,
        # None (not a dict of zeros) when the Excel ingest has not run — this
        # coercion is what turned the empty aggregate into the truthy all-zero
        # dict that defeated the frontend's fallback.
        'facility_totals': ({k: int(v or 0) for k, v in facility_totals.items()}
                            if facility_totals else None),
        'notification_by_level': notification_by_level,
        # 'excel' = Sayeed's programme-wide ingest, 'kobo' = live notification
        # slips. The dashboard should say which, so a partial figure is never
        # read as the programme total.
        'notification_by_level_source': notification_by_level_source,
        'action_plan_summaries': action_plan_summaries,
        'mpdsr_actions': mpdsr_actions,
        'totals': totals,
        'review_counts': review_counts,
        'indicators': indicators,
        'records_by_district': records_by_district,
        'facility': facility,
        'neonatal': neonatal,
        'notifications': notifications,
        'maternal_reporting': {
            'rows': maternal_reporting,
            'reported_total': sum(r['reported'] for r in maternal_reporting),
            'projected_total': sum(r['projected'] or 0 for r in maternal_reporting),
            'basis': 'Notification slips against the full-year 2026 projection, CIPRB working districts only',
        },
        'social_autopsy': social_autopsy,
    })


@api_view(['GET'])
@drf_permission_classes([IsAuthenticated, CanAccessMPDSR])
def mpdsr_action_aggregates(request):
    """Dedicated, lightweight aggregate for the CIPRB-10 Action-Plan tracker —
    the dashboard's headline 'is the response plan actually being implemented?'
    surface. One row per APPROVED MPDSRAction (stubs excluded) plus server-side
    roll-ups: cumulative completion %, overdue count, status breakdown, and
    mean-completion bars by district and by section. Honours the donor
    `districts` filter the rest of the CIPRB dashboard uses."""
    from mpdsr.models import MPDSRAction, ActionStatus, STUB_ACTIVITY_SENTINEL

    qs = (MPDSRAction.objects
          .filter(approval_status='APPROVED')
          .exclude(activity=STUB_ACTIVITY_SENTINEL))
    districts_param = request.query_params.get('districts')
    if districts_param:
        names = [n.strip() for n in districts_param.split(',') if n.strip()]
        if names:
            qs = qs.filter(district__in=names)

    actions, comp = [], []
    overdue = 0
    status_counts = {}
    by_district, by_section = {}, {}
    for a in qs.order_by('district', 'action_id'):
        actions.append({
            'action_id': a.action_id,
            'district': a.district,
            'section': a.section,
            'section_label': a.get_section_display(),
            'sub_category': a.sub_category,
            'sub_category_label': a.sub_category_label,
            'activity': a.activity,
            'responsible': a.responsible,
            'timeline': a.timeline.isoformat() if a.timeline else None,
            'status': a.status,
            'status_label': a.get_status_display(),
            'completion_pct': a.completion_pct,
            'completion_date': a.completion_date.isoformat() if a.completion_date else None,
            'is_overdue': a.is_overdue,
        })
        comp.append(a.completion_pct)
        if a.is_overdue:
            overdue += 1
        status_counts[a.status] = status_counts.get(a.status, 0) + 1
        by_district.setdefault(a.district or '—', []).append(a.completion_pct)
        by_section.setdefault(a.get_section_display() or '—', []).append(a.completion_pct)

    def _rollup(m):
        rows = [{'key': k, 'pct': round(sum(v) / len(v)), 'n': len(v)}
                for k, v in m.items()]
        rows.sort(key=lambda r: -r['pct'])
        return rows

    overall = round(sum(comp) / len(comp)) if comp else 0
    by_status = [{'status': val, 'label': label, 'count': status_counts.get(val, 0)}
                 for val, label in ActionStatus.choices]

    return Response({
        'overall_pct': overall,
        'total': len(actions),
        'overdue': overdue,
        'by_status': by_status,
        'by_district': _rollup(by_district),
        'by_section': _rollup(by_section),
        'actions': actions,
    })


@api_view(['GET'])
@drf_permission_classes([IsAuthenticated, CanAccessMPDSR])
def mnm_aggregates(request):
    """Aggregate endpoint for the Maternal Near Miss panel on /ciprb.

    Returns the 6 CIPRB-requested indicators (severe maternal
    complications, critical interventions, life-threatening conditions,
    mode of delivery, causes, contributory conditions) as district-rolled
    counts. Drop-in for the React MaternalNearMissPanel component."""
    from collections import Counter
    from django.db.models import Q
    from .ciprb_models import MaternalNearMissCase
    qs = MaternalNearMissCase.objects.filter(approval_status='APPROVED')
    # Honour the donor (GAC / SIDA) district filter so the Near Miss panel
    # scopes with the rest of the CIPRB dashboard instead of always showing
    # all 18 districts.
    districts_param = request.query_params.get('districts')
    if districts_param:
        names = [n.strip() for n in districts_param.split(',') if n.strip()]
        if names:
            q = Q()
            for n in names:
                q |= Q(district__iexact=n)
            qs = qs.filter(q)
    total = qs.count()
    by_district = Counter(qs.values_list('district', flat=True))

    # The 17 screening flags are now 3-state (True = Yes, False = No,
    # None = Unknown). Report all three counts per flag so the No/Unknown
    # distinction the form captures is no longer lost. Shape per flag is
    # {'yes': n, 'no': n, 'unknown': n}; 'yes' preserves the old per-flag
    # count for any existing consumer.
    def _three_state(field):
        yes = qs.filter(**{field: True}).count()
        no = qs.filter(**{field: False}).count()
        unknown = qs.filter(**{field + '__isnull': True}).count()
        return {'yes': yes, 'no': no, 'unknown': unknown}

    severe = {f: _three_state(f) for f in (
        'sev_pph', 'sev_preec', 'eclampsia', 'sepsis',
        'rupt_uterus', 'sev_abortion',
    )}
    critical = {f: _three_state(f) for f in (
        'crit_blood', 'crit_radiol', 'crit_laparot', 'crit_icu',
    )}
    life_threat = {f: _three_state(f) for f in (
        'life_cardio', 'life_resp', 'life_renal', 'life_coag',
        'life_hepatic', 'life_neuro', 'life_uterine',
    )}
    mode_of_delivery = Counter(
        qs.exclude(mode_of_delivery='').values_list('mode_of_delivery', flat=True)
    )
    causes = Counter(
        qs.exclude(cause_of_near_miss='').values_list('cause_of_near_miss', flat=True)
    )
    # Indicator 6 — Contributory / associated conditions. Free text; expose
    # the non-empty excerpts as a read-only list for the dashboard notes panel.
    contributory = list(
        qs.exclude(contributory_conditions='')
          .values_list('contributory_conditions', flat=True)[:200]
    )
    return Response({
        'total': total,
        'by_district': dict(by_district),
        'severe_complications': severe,
        'critical_interventions': critical,
        'life_threatening': life_threat,
        'mode_of_delivery': dict(mode_of_delivery),
        'causes': dict(causes),
        'contributory_conditions': contributory,
    })


@api_view(['GET'])
@drf_permission_classes([IsAuthenticated, CanAccessMPDSR])
def safe_surgery(request):
    """Safe Surgery Checklist surface for the CIPRB dashboard (CIPRB-11).

    Returns the operations list — each with its automatic ID, operation name,
    facility, date/time and the three WHO-phase completion states (Sign In /
    Time Out / Sign Out) — plus a compliance summary, so Tanjina can track
    checklist compliance at a glance. patient_name is deliberately OMITTED: it
    is PII and the dashboard is an at-a-glance view, not the patient register."""
    from django.db.models import Q
    from .ciprb_models import SurgeryChecklist
    qs = SurgeryChecklist.objects.filter(approval_status='APPROVED')
    # Honour the donor (GAC / SIDA / CP) district filter like the rest of /ciprb.
    districts_param = request.query_params.get('districts')
    if districts_param:
        names = [n.strip() for n in districts_param.split(',') if n.strip()]
        if names:
            q = Q()
            for n in names:
                q |= Q(district__iexact=n)
            qs = qs.filter(q)

    from collections import Counter
    total = qs.count()
    compliant = qs.filter(fully_compliant=True).count()
    phase_complete = {
        'signin':  qs.filter(signin_complete=True).count(),
        'timeout': qs.filter(timeout_complete=True).count(),
        'signout': qs.filter(signout_complete=True).count(),
    }
    by_district = dict(Counter(qs.values_list('district', flat=True)))

    operations = []
    for o in qs[:500]:   # newest first (model default ordering)
        operations.append({
            'id': str(o.id),
            'system_ref': o.system_ref or '',
            'operation_name': o.operation_name,
            'facility_name': o.facility_name,
            'ward_unit': o.ward_unit,
            'district': o.district,
            'op_datetime': o.op_datetime.isoformat() if o.op_datetime else None,
            'surgeon': o.surgeon,
            'phases': {
                'signin':  {'total': o.signin_total,  'done': o.signin_done,
                            'complete': o.signin_complete},
                'timeout': {'total': o.timeout_total, 'done': o.timeout_done,
                            'complete': o.timeout_complete},
                'signout': {'total': o.signout_total, 'done': o.signout_done,
                            'complete': o.signout_complete},
            },
            'fully_compliant': o.fully_compliant,
        })

    return Response({
        'total': total,
        'compliant': compliant,
        'compliance_pct': round(compliant / total * 100, 1) if total else None,
        'phase_complete': phase_complete,
        'by_district': by_district,
        'operations': operations,
    })


@api_view(['GET'])
@drf_permission_classes([IsAuthenticated, CanAccessMPDSR])
def ciprb_reconciliation(request):
    """Read-only health snapshot for the CIPRB dashboard strip.

    Returns the latest stored CIPRBReconSnapshot (written by the
    `reconcile_ciprb` management command / daemon): per CIPRB form, how many
    Kobo submissions are missing from the app (`stranded`), handler crashes, and
    webhook delivery health. This endpoint NEVER runs the reconciliation itself
    (that replays payloads and must happen where the prod DB lives) — it only
    reads what was stored, so it is cheap and side-effect free. No alerting.
    """
    from .reconcile import latest_snapshot

    snap = latest_snapshot()
    if snap is None:
        # No snapshot yet — the strip renders an "unknown / not yet run" state
        # rather than implying everything is healthy.
        return Response({'available': False, 'forms': []})

    data = snap.data or {}
    return Response({
        'available': True,
        'run_at': snap.run_at.isoformat(),
        'forms': data.get('forms', []),
        'total_stranded': data.get('total_stranded', 0),
        'total_crashes': data.get('total_crashes', 0),
        'all_ok': data.get('all_ok', False),
    })
