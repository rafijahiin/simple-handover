"""
Per-partner report content — what each organisation's report is ABOUT.

The old collect_programme_data() counted the same seventeen service models for
every scope. That template fit exactly one partner: PHD. Bandhu records every
service in the F-01 wellness logbook (none of the seventeen), so its report
showed "Clinic Visits 0 · HIV tests 0" under a large registration number; and
CIPRB delivers no client services at all, so its report opened with a giant
orange "0 activities" above the MPDSR and fistula work it actually did.

This module gives each scope its own content model, and takes achievement
numbers from indicators.service — the same compute functions behind the
dashboard — so a report can never disagree with the dashboard it summarises.

Every collector returns the same envelope, so the four renderers (document,
poster, deck, web) stay scope-agnostic:

  {
    'org', 'org_label', 'period_label', 'period_start', 'period_end',
    'hero':   {'value', 'en', 'bn', 'note'},
    'kpis':   [{'value', 'en', 'bn'}, ...]           # 4-6 headline tiles
    'blocks': [{'en', 'bn', 'rows': [{'en','bn','value'}, ...]}, ...]
    'geo':    {'en', 'bn', 'rows': [(name, n), ...], 'coverage': str|None}
    'indicators': [{'code','label','target','achieved','pct'}, ...]
    'trend':  [12 ints, oldest first]
    'mom_pct': float|None,     # None unless last month is comparable
    'partners': [...overall only...],
  }

Honesty rules enforced here, not in the templates:
  - a month-on-month % is shown only when the previous month had at least
    MOM_FLOOR records under the SAME counting rules (the July set shipped
    with "▲ 576.1% vs Jun" because June was counted differently);
  - no "active field workers" — shared collection accounts made it 2;
  - geography comes from each partner's own footprint (Bandhu's wellness
    centres, CIPRB's 19 MPDSR districts), never another partner's frame.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

APPROVED = 'APPROVED'
MOM_FLOOR = 50          # records last month before a % comparison is honest
MPDSR_DISTRICTS = 19    # the CIPRB MPDSR frame

BN_MONTHS = {1: 'জানুয়ারি', 2: 'ফেব্রুয়ারি', 3: 'মার্চ', 4: 'এপ্রিল',
             5: 'মে', 6: 'জুন', 7: 'জুলাই', 8: 'অগাস্ট',
             9: 'সেপ্টেম্বর', 10: 'অক্টোবর', 11: 'নভেম্বর', 12: 'ডিসেম্বর'}


def month_labels(ps: date, pe: date) -> tuple[str, str]:
    en = pe.strftime('%B %Y')
    bn = f"{BN_MONTHS[pe.month]} {pe.year}"
    return en, bn


def _month_windows(pe: date, n: int = 12):
    """(start, end) for the n calendar months ending with pe's month."""
    out = []
    y, m = pe.year, pe.month
    for i in range(n - 1, -1, -1):
        idx = (y * 12 + m - 1) - i
        my, mm = idx // 12, idx % 12 + 1
        out.append((date(my, mm, 1), date(my, mm, calendar.monthrange(my, mm)[1])))
    return out


def _mom(trend: list[int]) -> float | None:
    """% change of the last month vs the one before, honest or absent.

    Absent both when the base is too small (July shipped with "▲ 576.1%"
    because June was counted under different rules) and when the jump is so
    large it can only mean a counting change or a launch month — a four-digit
    percentage informs nobody."""
    if len(trend) < 2 or trend[-2] < MOM_FLOOR:
        return None
    pct = round((trend[-1] - trend[-2]) / trend[-2] * 100, 1)
    return pct if abs(pct) <= 400 else None


def _row(en, bn, value):
    return {'en': en, 'bn': bn, 'value': int(value or 0)}


def _indicator_rows(org: str, ps: date, pe: date, limit: int = 10) -> list[dict]:
    """Dashboard indicator rows (target/achieved/%) for the report table.
    Rows without a compute module and rows with neither target nor achievement
    are noise in a monthly document — dropped."""
    try:
        from indicators.service import get_partner_indicator_progress
        rows = get_partner_indicator_progress(org, ps, pe)
    except Exception as exc:                                # pragma: no cover
        logger.warning('indicator progress unavailable for %s: %s', org, exc)
        return []
    keep = []
    for r in rows:
        if r.get('unlinked'):
            continue
        if not r.get('achievement') and r.get('target_value') is None:
            continue
        keep.append({
            'code':     r['activity_code'],
            'label':    r['indicator_label'] or r['activity_label'],
            'target':   r['target_value'],
            'achieved': r['achievement'],
            'pct':      r['percentage'],
        })
    keep.sort(key=lambda r: (r['pct'] is None, -(r['pct'] or 0)))
    return keep[:limit]


# ─── PHD — FSW service delivery ────────────────────────────────────────────────

_PHD_SERVICE_MODELS = None


def _phd_models():
    global _PHD_SERVICE_MODELS
    if _PHD_SERVICE_MODELS is None:
        from programs.models import (
            Client, ClinicVisit, HIVSTITestResult, HTCCounselling,
            IndividualCounselling, MHScreening, GBVCase, OutreachSession,
            GroupEducationSession, Referral, SafetyHygieneKit, ADRRecord,
            AntenatalCard, TrainingEvent, CoordMeeting, MobileHealthCamp,
            AutoclaveLog,
        )
        _PHD_SERVICE_MODELS = dict(
            Client=Client, ClinicVisit=ClinicVisit, HIVSTITestResult=HIVSTITestResult,
            HTCCounselling=HTCCounselling, IndividualCounselling=IndividualCounselling,
            MHScreening=MHScreening, GBVCase=GBVCase, OutreachSession=OutreachSession,
            GroupEducationSession=GroupEducationSession, Referral=Referral,
            SafetyHygieneKit=SafetyHygieneKit, ADRRecord=ADRRecord,
            AntenatalCard=AntenatalCard, TrainingEvent=TrainingEvent,
            CoordMeeting=CoordMeeting, MobileHealthCamp=MobileHealthCamp,
            AutoclaveLog=AutoclaveLog,
        )
    return _PHD_SERVICE_MODELS


def _count(model, ps, pe, org, date_field='created_at'):
    try:
        kw = {f'{date_field}__date__gte': ps, f'{date_field}__date__lte': pe} \
            if date_field == 'created_at' else {f'{date_field}__range': (ps, pe)}
        qs = model.objects.filter(approval_status=APPROVED, **kw)
        if org:
            qs = qs.filter(organisation=org)
        return qs.count()
    except Exception as exc:
        logger.debug('count failed for %s: %s', getattr(model, '__name__', model), exc)
        return 0


def _phd_volume(ps, pe):
    M = _phd_models()
    return sum(_count(m, ps, pe, 'PHD') for m in M.values())


def collect_phd(ps: date, pe: date) -> dict:
    M = _phd_models()
    c = {k: _count(m, ps, pe, 'PHD') for k, m in M.items()}

    from programs.models import Client
    registry = Client.objects.filter(organisation='PHD', approval_status=APPROVED) \
                             .exclude(name='').exclude(name='Unknown').count()

    # Distinct women who received at least one clinical service this month —
    # a service-reach number no single form count gives.
    served = 0
    try:
        ids = set()
        for key in ('ClinicVisit', 'HIVSTITestResult', 'HTCCounselling',
                    'IndividualCounselling', 'Referral', 'SafetyHygieneKit'):
            ids.update(
                M[key].objects.filter(
                    organisation='PHD', approval_status=APPROVED,
                    created_at__date__gte=ps, created_at__date__lte=pe,
                ).exclude(client__isnull=True).values_list('client_id', flat=True)
            )
        served = len(ids)
    except Exception as exc:
        logger.debug('phd served-distinct failed: %s', exc)

    geo_rows = []
    try:
        from django.db.models import Count
        from programs.models import Client as _C
        rows = (_C.objects.filter(organisation='PHD', approval_status=APPROVED,
                                  created_at__date__gte=ps, created_at__date__lte=pe)
                .exclude(center__isnull=True)
                .values('center__district').annotate(n=Count('id')).order_by('-n')[:6])
        geo_rows = [(r['center__district'] or '—', r['n']) for r in rows]
    except Exception as exc:
        logger.debug('phd geo failed: %s', exc)

    trend = [ _phd_volume(a, b) for a, b in _month_windows(pe) ]
    total = sum(c.values())

    # Hero adapts to what the month actually was. July 2026 was a mass
    # registration drive (3,419 registrations, 22 clinic visits) — leading
    # that month with "22 women served" would bury the story.
    if c['Client'] >= max(served, 1) * 3:
        hero = {'value': c['Client'],
                'en': 'new FSW registered this month',
                'bn': 'নতুন এফএসডব্লিউ নিবন্ধিত',
                'note': f'{served:,} women received a clinical service'}
    else:
        hero = {'value': served or total,
                'en': 'women received a service this month' if served else 'approved field records',
                'bn': 'নারী এ মাসে সেবা পেয়েছেন' if served else 'অনুমোদিত মাঠ রেকর্ড',
                'note': f'{total:,} approved records'}

    return {
        'org': 'PHD', 'org_label': 'PHD — FSW Programme',
        'hero': hero,
        'kpis': [
            _row('New FSW registered', 'নতুন নিবন্ধন', c['Client']),
            _row('Clinic visits', 'ক্লিনিক ভিজিট', c['ClinicVisit']),
            _row('HIV/STI tests', 'এইচআইভি/এসটিআই পরীক্ষা', c['HIVSTITestResult']),
            _row('Counselling sessions', 'কাউন্সেলিং সেশন',
                 c['HTCCounselling'] + c['IndividualCounselling'] + c['MHScreening']),
            _row('Referrals', 'রেফারেল', c['Referral']),
            _row('Registry to date', 'মোট নিবন্ধিত', registry),
        ],
        'blocks': [
            {'en': 'Clinical services', 'bn': 'ক্লিনিক সেবা', 'rows': [
                _row('Clinic visits', 'ক্লিনিক ভিজিট', c['ClinicVisit']),
                _row('HIV/STI test results', 'এইচআইভি/এসটিআই পরীক্ষা', c['HIVSTITestResult']),
                _row('HTC counselling', 'এইচটিসি কাউন্সেলিং', c['HTCCounselling']),
                _row('Individual counselling', 'ব্যক্তিগত কাউন্সেলিং', c['IndividualCounselling']),
                _row('Mental-health screening', 'মানসিক স্বাস্থ্য স্ক্রিনিং', c['MHScreening']),
                _row('Antenatal cards', 'গর্ভকালীন কার্ড', c['AntenatalCard']),
            ]},
            {'en': 'Protection & outreach', 'bn': 'সুরক্ষা ও আউটরিচ', 'rows': [
                _row('GBV cases supported', 'জিবিভি সহায়তা', c['GBVCase']),
                _row('Referrals made', 'রেফারেল', c['Referral']),
                _row('Safety & hygiene kits', 'সেফটি-হাইজিন কিট', c['SafetyHygieneKit']),
                _row('Outreach sessions', 'আউটরিচ সেশন', c['OutreachSession']),
                _row('Group education', 'দলীয় শিক্ষা', c['GroupEducationSession']),
                _row('Mobile health camps', 'মোবাইল ক্যাম্প', c['MobileHealthCamp']),
            ]},
        ],
        'geo': {'en': 'New registrations by district', 'bn': 'জেলাভিত্তিক নতুন নিবন্ধন',
                'rows': geo_rows, 'coverage': None},
        'indicators': _indicator_rows('PHD', ps, pe),
        'trend': trend, 'mom_pct': _mom(trend),
    }


# ─── Bandhu — everything lives in the F-01 logbook ────────────────────────────

def _bandhu_logbook(ps, pe):
    from programs.models import WellnessLogbookEntry
    return WellnessLogbookEntry.objects.filter(
        organisation='Bandhu', approval_status=APPROVED,
        service_date__range=(ps, pe),
    )


def _bandhu_volume(ps, pe):
    from programs.models import Client
    reg = Client.objects.filter(
        organisation='Bandhu', approval_status=APPROVED,
        created_at__date__gte=ps, created_at__date__lte=pe,
    ).exclude(name='').exclude(name='Unknown').count()
    return reg + _bandhu_logbook(ps, pe).count()


def collect_bandhu(ps: date, pe: date) -> dict:
    from django.db.models import Count, Sum
    from programs.models import Client

    from django.db.models import Q

    lb = _bandhu_logbook(ps, pe)
    contacts = lb.count()
    flags = lb.aggregate(
        sti=Count('id', filter=Q(sti_screening=True)),
        htc=Count('id', filter=Q(htc=True)),
        clinical=Count('id', filter=Q(clinical=True)),
        gbv=Count('id', filter=Q(gbv=True)),
        mh=Count('id', filter=Q(mental_health=True)),
        counseling=Count('id', filter=Q(counseling=True)),
        legal=Count('id', filter=Q(legal=True)),
        group_edu=Count('id', filter=Q(group_edu=True)),
        condom=Sum('condom'), lubricant=Sum('lubricant'),
        condom_demo=Sum('condom_demo'),
    )

    new_reg = Client.objects.filter(
        organisation='Bandhu', approval_status=APPROVED,
        created_at__date__gte=ps, created_at__date__lte=pe,
    ).exclude(name='').exclude(name='Unknown').count()
    registry = Client.objects.filter(organisation='Bandhu', approval_status=APPROVED) \
                             .exclude(name='').exclude(name='Unknown').count()

    members = lb.exclude(client_id_norm='').values('client_id_norm').distinct().count()

    geo_rows = []
    try:
        rows = (lb.exclude(center__isnull=True)
                  .values('center__name').annotate(n=Count('id')).order_by('-n')[:8])
        geo_rows = [(r['center__name'].replace('Bandhu Wellness Center ', ''), r['n'])
                    for r in rows]
    except Exception as exc:
        logger.debug('bandhu geo failed: %s', exc)
    centres_active = len(geo_rows)

    trend = [_bandhu_volume(a, b) for a, b in _month_windows(pe)]

    return {
        'org': 'Bandhu', 'org_label': 'Bandhu — Wellness Centres',
        'hero': {'value': contacts,
                 'en': 'service contacts in the wellness logbook',
                 'bn': 'ওয়েলনেস লগবুকে সেবা যোগাযোগ',
                 'note': f'{members:,} individual members served'},
        'kpis': [
            _row('New members registered', 'নতুন সদস্য নিবন্ধন', new_reg),
            _row('Members served', 'সেবা পাওয়া সদস্য', members),
            _row('HIV testing (HTC)', 'এইচআইভি পরীক্ষা', flags['htc'] or 0),
            _row('STI screening', 'এসটিআই স্ক্রিনিং', flags['sti'] or 0),
            _row('Condoms distributed', 'কনডম বিতরণ', flags['condom'] or 0),
            _row('Registry to date', 'মোট নিবন্ধিত', registry),
        ],
        'blocks': [
            {'en': 'Services recorded in the F-01 logbook',
             'bn': 'F-01 লগবুকে নথিভুক্ত সেবা', 'rows': [
                _row('HIV testing & counselling', 'এইচআইভি পরীক্ষা ও কাউন্সেলিং', flags['htc'] or 0),
                _row('STI screening', 'এসটিআই স্ক্রিনিং', flags['sti'] or 0),
                _row('Clinical care', 'চিকিৎসা সেবা', flags['clinical'] or 0),
                _row('Counselling', 'কাউন্সেলিং', flags['counseling'] or 0),
                _row('Mental-health support (MHPSS)', 'মানসিক স্বাস্থ্য সহায়তা', flags['mh'] or 0),
                _row('GBV support', 'জিবিভি সহায়তা', flags['gbv'] or 0),
                _row('Legal support', 'আইনি সহায়তা', flags['legal'] or 0),
                _row('Group education', 'দলীয় শিক্ষা', flags['group_edu'] or 0),
            ]},
            {'en': 'Commodities', 'bn': 'সামগ্রী বিতরণ', 'rows': [
                _row('Condoms', 'কনডম', flags['condom'] or 0),
                _row('Lubricant', 'লুব্রিকেন্ট', flags['lubricant'] or 0),
                _row('Condom demonstrations', 'কনডম প্রদর্শনী', flags['condom_demo'] or 0),
            ]},
        ],
        'geo': {'en': 'Logbook volume by wellness centre', 'bn': 'কেন্দ্রভিত্তিক লগবুক',
                'rows': geo_rows,
                'coverage': f'{centres_active} wellness centres active' if centres_active else None},
        'indicators': _indicator_rows('Bandhu', ps, pe),
        'trend': trend, 'mom_pct': _mom(trend),
    }


# ─── CIPRB — surveillance and response, not service delivery ──────────────────

def _ciprb_volume(ps, pe):
    try:
        from submissions.models import KoboSubmission, SubmissionStatus
        return KoboSubmission.objects.filter(
            partner='CIPRB', status=SubmissionStatus.APPROVED,
            submitted_at__date__gte=ps, submitted_at__date__lte=pe,
        ).count()
    except Exception:
        return 0


def collect_ciprb(ps: date, pe: date) -> dict:
    from django.db.models import Count, Q, Sum

    # MPDSR pipeline — notifications → reviews → actions.
    notif_m = notif_n = 0
    try:
        from mpdsr.ciprb_models import MPDSRDeathNotification
        nq = MPDSRDeathNotification.objects.filter(
            approval_status=APPROVED,
            created_at__date__gte=ps, created_at__date__lte=pe)
        agg = nq.aggregate(m=Count('id', filter=Q(death_kind__icontains='maternal')),
                           t=Count('id'))
        notif_m, notif_n = agg['m'] or 0, (agg['t'] or 0) - (agg['m'] or 0)
    except Exception as exc:
        logger.debug('ciprb notifications failed: %s', exc)

    rev_mat = rev_peri = rev_comm = rev_fac = 0
    try:
        from mpdsr.models import MPDSRCase, DeathType, PlaceOfDeath
        rq = MPDSRCase.objects.filter(created_at__date__gte=ps,
                                      created_at__date__lte=pe)
        agg = rq.aggregate(
            mat=Count('id', filter=Q(death_type=DeathType.MATERNAL)),
            peri=Count('id', filter=Q(death_type=DeathType.PERINATAL)),
            fac=Count('id', filter=Q(place_of_death=PlaceOfDeath.FACILITY)),
            t=Count('id'))
        rev_mat, rev_peri = agg['mat'] or 0, agg['peri'] or 0
        rev_fac = agg['fac'] or 0
        rev_comm = (agg['t'] or 0) - rev_fac
    except Exception as exc:
        logger.debug('ciprb reviews failed: %s', exc)
    reviews = rev_mat + rev_peri

    act_open = act_done = 0
    act_pct = None
    try:
        from mpdsr.models import MPDSRAction, ActionStatus
        aq = MPDSRAction.objects.all()
        act_done = aq.filter(status=ActionStatus.COMPLETED).count() \
            if hasattr(ActionStatus, 'COMPLETED') else aq.filter(completion_pct=100).count()
        act_open = aq.exclude(completion_pct=100).count()
        avg = aq.aggregate(a=Sum('completion_pct'), n=Count('id'))
        if avg['n']:
            act_pct = round((avg['a'] or 0) / avg['n'])
    except Exception as exc:
        logger.debug('ciprb actions failed: %s', exc)

    # Fistula cascade — same source as the dashboard funnel.
    f_susp = f_diag = f_ref = f_rep = 0
    try:
        from fistula.ciprb_models import CIPRBFistulaCase
        fq = CIPRBFistulaCase.objects.filter(approval_status=APPROVED)
        agg = fq.aggregate(
            susp=Count('id'),
            diag=Count('id', filter=Q(current_stage__in=['diagnosed', 'referred',
                                                         'repaired', 'rehabilitated'])),
            ref=Count('id', filter=Q(current_stage__in=['referred', 'repaired',
                                                        'rehabilitated'])),
            rep=Count('id', filter=Q(current_stage__in=['repaired', 'rehabilitated'])))
        f_susp, f_diag = agg['susp'] or 0, agg['diag'] or 0
        f_ref, f_rep = agg['ref'] or 0, agg['rep'] or 0
    except Exception as exc:
        logger.debug('ciprb fistula failed: %s', exc)

    camp_visits = camp_house = 0
    try:
        from fistula.models import FistulaCampaign
        cq = FistulaCampaign.objects.filter(campaign_date__range=(ps, pe))
        camp_visits = cq.count()
        for f in ('households_visited', 'households_reached', 'people_reached'):
            try:
                camp_house = cq.aggregate(t=Sum(f))['t'] or 0
                if camp_house:
                    break
            except Exception:
                continue
    except Exception as exc:
        logger.debug('ciprb campaign failed: %s', exc)

    nearmiss = 0
    try:
        from mpdsr.ciprb_models import MaternalNearMissCase
        nearmiss = MaternalNearMissCase.objects.filter(
            approval_status=APPROVED,
            created_at__date__gte=ps, created_at__date__lte=pe).count()
    except Exception as exc:
        logger.debug('ciprb nearmiss failed: %s', exc)

    geo_rows = []
    districts = 0
    try:
        from mpdsr.models import MPDSRCase
        rows = (MPDSRCase.objects.exclude(district='')
                .filter(created_at__date__gte=ps, created_at__date__lte=pe)
                .values('district').annotate(n=Count('id')).order_by('-n'))
        geo_rows = [(r['district'], r['n']) for r in rows[:6]]
        districts = len(rows)
    except Exception as exc:
        logger.debug('ciprb geo failed: %s', exc)

    trend = [_ciprb_volume(a, b) for a, b in _month_windows(pe)]

    return {
        'org': 'CIPRB', 'org_label': 'CIPRB — MPDSR & Fistula',
        'hero': {'value': reviews,
                 'en': 'maternal & perinatal death reviews this month',
                 'bn': 'মাতৃ ও নবজাতক মৃত্যু পর্যালোচনা',
                 'note': f'{notif_m + notif_n:,} death notifications received'},
        'kpis': [
            _row('Death notifications', 'মৃত্যু নোটিফিকেশন', notif_m + notif_n),
            _row('Reviews conducted', 'পর্যালোচনা সম্পন্ন', reviews),
            _row('Response actions tracked', 'ব্যবস্থা ট্র্যাকিংয়ে', act_open + act_done),
            _row('Fistula cases identified', 'ফিস্টুলা শনাক্ত', f_susp),
            _row('Repairs completed', 'মেরামত সম্পন্ন', f_rep),
            _row('Near-miss audits', 'নিয়ার-মিস অডিট', nearmiss),
        ],
        'blocks': [
            {'en': 'MPDSR — surveillance to response', 'bn': 'এমপিডিএসআর', 'rows': [
                _row('Maternal death notifications', 'মাতৃমৃত্যু নোটিফিকেশন', notif_m),
                _row('Neonatal death notifications', 'নবজাতক মৃত্যু নোটিফিকেশন', notif_n),
                _row('Maternal death reviews', 'মাতৃমৃত্যু পর্যালোচনা', rev_mat),
                _row('Perinatal death reviews', 'নবজাতক মৃত্যু পর্যালোচনা', rev_peri),
                _row('Community reviews', 'কমিউনিটি পর্যালোচনা', rev_comm),
                _row('Facility reviews', 'ফ্যাসিলিটি পর্যালোচনা', rev_fac),
                _row('Actions completed', 'সম্পন্ন ব্যবস্থা', act_done),
            ]},
            {'en': 'Fistula — identification to repair', 'bn': 'ফিস্টুলা', 'rows': [
                _row('Suspected cases identified', 'সন্দেহভাজন শনাক্ত', f_susp),
                _row('Diagnosed at district hospital', 'জেলা হাসপাতালে নির্ণীত', f_diag),
                _row('Referred for surgery', 'অস্ত্রোপচারে রেফার', f_ref),
                _row('Repairs completed', 'মেরামত সম্পন্ন', f_rep),
                _row('Campaign reports this month', 'এ মাসের ক্যাম্পেইন রিপোর্ট', camp_visits),
                _row('Households reached', 'পরিবারে পৌঁছানো', camp_house),
            ]},
            {'en': 'Quality of care', 'bn': 'সেবার মান', 'rows': [
                _row('Maternal near-miss audits', 'নিয়ার-মিস অডিট', nearmiss),
            ]},
        ],
        'geo': {'en': 'Death reviews by district', 'bn': 'জেলাভিত্তিক পর্যালোচনা',
                'rows': geo_rows,
                'coverage': f'{districts}/{MPDSR_DISTRICTS} MPDSR districts reporting'
                            if districts else None},
        'indicators': _indicator_rows('CIPRB', ps, pe),
        'trend': trend, 'mom_pct': _mom(trend),
        'action_completion_pct': act_pct,
    }


# ─── Overall — the three partners side by side ────────────────────────────────

def collect_overall(ps: date, pe: date) -> dict:
    phd, bnd, cip = collect_phd(ps, pe), collect_bandhu(ps, pe), collect_ciprb(ps, pe)
    total = phd['hero']['value'] + bnd['hero']['value'] + cip['hero']['value']
    trend = [p + b + c for p, b, c in
             zip(phd['trend'], bnd['trend'], cip['trend'])]
    return {
        'org': '', 'org_label': 'All Partners',
        'hero': {'value': total,
                 'en': 'headline results across the three partners',
                 'bn': 'তিন পার্টনারের মূল ফলাফল একত্রে',
                 'note': 'PHD + Bandhu + CIPRB'},
        'kpis': [
            _row(f"PHD: {phd['hero']['en'].split(' this month')[0]}",
                 'পিএইচডি', phd['hero']['value']),
            _row('Bandhu: service contacts', 'বন্ধু: সেবা যোগাযোগ', bnd['hero']['value']),
            _row('CIPRB: death reviews', 'সিআইপিআরবি: মৃত্যু পর্যালোচনা', cip['hero']['value']),
            _row('Fistula repairs completed', 'ফিস্টুলা মেরামত',
                 next((k['value'] for k in cip['kpis'] if k['en'] == 'Repairs completed'), 0)),
        ],
        'blocks': [],
        'geo': {'en': '', 'bn': '', 'rows': [], 'coverage': None},
        'indicators': [],
        'trend': trend, 'mom_pct': _mom(trend),
        'partners': [
            {'data': phd, 'accent': '#E8562B'},
            {'data': bnd, 'accent': '#C2481F'},
            {'data': cip, 'accent': '#8F3415'},
        ],
    }


def collect_content(org: str, ps: date, pe: date) -> dict:
    fn = {'PHD': collect_phd, 'Bandhu': collect_bandhu, 'CIPRB': collect_ciprb,
          '': collect_overall}[org]
    out = fn(ps, pe)
    en, bn = month_labels(ps, pe)
    out.update({'period_start': ps, 'period_end': pe,
                'period_label': en, 'period_label_bn': bn})
    return out
