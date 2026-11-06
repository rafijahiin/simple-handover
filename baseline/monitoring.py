"""Baseline fieldwork + data-quality monitoring.

Unlike insights.py (which summarises the SUBSTANTIVE answers of VERIFIED
interviews), this reads EVERY collected baseline submission — pending and
approved — because monitoring is about the data collection itself: pace against
target, per-site and per-enumerator throughput, interview duration and outcome,
and the quality flags that decide whether the dataset can be trusted.

Signals come from the fields the forms now capture: interview_start /
interview_end (device timestamps → duration), dc_code (data collector),
c3 (interview outcome), submission_id (dedup), GPS, and submitted_at.
"""
from collections import Counter, defaultdict
from datetime import datetime

from submissions.flatten import flatten_group_keys

from .collectors import collector_name
from .populations import resolve_population

# Sample-size targets per key population. UNKNOWN until the protocol sets them —
# leave blank so the dashboard shows collected COUNTS, not a fake % of target.
# Fill in (e.g. {'hijra': 250, 'fsw': 250}) once CIPRB confirms the sample size.
TARGETS: dict = {}

OUTCOME_LABEL = {'1': 'Completed', '2': 'Partial', '3': 'Refused', '4': 'Interrupted'}
DURATION_BANDS = [(0, 10, '<10m'), (10, 20, '10–20m'), (20, 30, '20–30m'),
                  (30, 40, '30–40m'), (40, 50, '40–50m'), (50, 60, '50–60m'),
                  (60, 10 ** 6, '60m+')]
# The baseline is a ~50-minute CAPI interview. Anything materially shorter was
# not administered in full, so CIPRB treats under 40 minutes as rushed.
SHORT_MINUTES = 40
# Duration is measured from CONSENT to SUBMIT. If the enumerator consents, then
# leaves the form open and submits hours later, that span is their working
# session, not the interview. Anything over this is flagged as "form left open"
# and excluded from the TYPICAL length, so it can't quietly inflate the average.
LONG_MINUTES = 120


def _parse_dt(v):
    if not v:
        return None
    s = str(v).strip().replace('Z', '')
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%dT%H:%M'):
        try:
            return datetime.strptime(s[:26], fmt)
        except (ValueError, TypeError):
            continue
    # tolerate a trailing timezone offset like +06:00
    try:
        return datetime.fromisoformat(s.split('+')[0])
    except (ValueError, TypeError):
        return None


def _duration_min(raw):
    # End of the INTERVIEW, not of the submission. interview_end_actual freezes
    # at the outcome question (c3), so it excludes any time the form then spent in
    # draft / an open tab / the offline outbox before Submit. interview_end (the
    # XForm `end` meta = finalize time) is the fallback for rows collected before
    # this field existed.
    a = _parse_dt(raw.get('interview_start'))
    b = _parse_dt(raw.get('interview_end_actual')) or _parse_dt(raw.get('interview_end'))
    if not a or not b:
        return None
    m = (b - a).total_seconds() / 60.0
    return round(m, 1) if 0 < m < 600 else None


def _has_true_end(raw):
    """True when this row carries the in-interview end stamp (interview_end_actual),
    so its duration is a real interview length rather than a submit-lag estimate."""
    return bool(_parse_dt(raw.get('interview_end_actual')))


def _band(v, bands):
    for lo, hi, lab in bands:
        if lo <= v < hi:
            return lab
    return None


def _median(xs):
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return round((s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2), 1)


def _quartiles(xs):
    """(q1, q3) by linear interpolation; None when under 4 values."""
    if len(xs) < 4:
        return None, None
    s = sorted(xs)

    def q(p):
        k = (len(s) - 1) * p
        f = int(k)
        c = min(f + 1, len(s) - 1)
        return round(s[f] + (s[c] - s[f]) * (k - f), 1)
    return q(0.25), q(0.75)


def compute_monitoring(subs, filters=None):
    """`subs`: iterable of baseline KoboSubmission (all statuses). Returns a
    chart-ready fieldwork + quality dict.

    `filters` (all optional, all ANDed): population ('fsw'/'hijra'), enumerator
    (resolved collector name), site (site_code), version (__version__),
    date_from / date_to (ISO date, matched on interview_start's date falling
    back to submitted_at). Filtering happens here — where population and
    collector are already resolved — so the API can't drift from the roster."""
    f = filters or {}
    versions = Counter()      # __version__ -> count, for the form-version filter
    total = 0
    by_pop = Counter()
    by_status = Counter()
    district = Counter()
    site = Counter()
    outcomes = Counter()
    daily = defaultdict(Counter)          # date -> {hijra, fsw}
    hourly = defaultdict(Counter)         # 'HH:00' -> {hijra, fsw} (single-day views)
    day_flags = defaultdict(lambda: {'hijra': 0, 'fsw': 0, 'total': 0,
                                     'completed': 0, 'partial': 0, 'refused': 0,
                                     'interrupted': 0, 'rushed': 0, 'gps_missing': 0})
    dur_band = Counter()
    durations = []          # every timed row, raw
    real_durations = []     # only rows whose duration is a trustworthy interview length
    # Valid timing = usable start AND in-form end (interview_end_actual). Rows
    # missing the end stamp stay in the DENOMINATOR (total) but are never turned
    # into a duration. The headline median additionally excludes extreme
    # (> LONG_MINUTES) spans, per the anomaly rules.
    valid_timing_n = 0
    valid_median_set = []
    true_end_n = 0          # rows carrying the in-interview end stamp
    gps_ok = gps_missing = 0
    coll = defaultdict(lambda: {'n': 0, 'dur': [], 'valid': 0, 'med': [],
                                'complete': 0, 'short': 0, 'long': 0, 'pop': Counter()})
    id_rows = defaultdict(list)   # submission_id -> the records sharing it
    short_rows = []
    long_rows = []
    points = []

    for s in subs:
        # Kobo stores grouped answers as 'group/field' — flatten so dc_code,
        # population, c3, submission_id and every field below actually resolve.
        raw = flatten_group_keys(s.raw_data or {})
        # Resolved from the source form, not defaulted (see baseline/populations.py).
        pop = resolve_population(raw, default='hijra')

        # Collector identity comes from INSIDE the form, never the Kobo account
        # username — resolved BEFORE filtering so the enumerator filter uses the
        # same name the roster displays.
        dc = str(raw.get('dc_name') or raw.get('interviewer_name_code') or '').strip()
        if not dc:
            code = raw.get('dc_code')
            dc = collector_name(pop, code) or (f'Collector {code}' if code not in (None, '') else '')
        dc = dc or 'Unknown'

        ver = str(raw.get('__version__') or '')
        fdate_dt = _parse_dt(raw.get('interview_start')) or s.submitted_at
        fdate = fdate_dt.strftime('%Y-%m-%d') if fdate_dt else ''

        if f.get('population') and pop != f['population']:
            continue
        if f.get('enumerator') and dc != f['enumerator']:
            continue
        if f.get('site') and str(raw.get('site_code') or '') != str(f['site']):
            continue
        if f.get('version') and ver != f['version']:
            continue
        if f.get('date_from') and (not fdate or fdate < f['date_from']):
            continue
        if f.get('date_to') and (not fdate or fdate > f['date_to']):
            continue

        total += 1
        by_pop[pop] += 1
        by_status[(s.status or 'PENDING')] += 1
        if ver:
            versions[ver] += 1
        dist = (raw.get('district') or s.district or '').strip().title()
        if dist:
            district[dist] += 1
        sc = raw.get('site_code')
        if sc:
            site[str(sc)] += 1

        oc = str(raw.get('c3') or '')
        if oc:
            outcomes[OUTCOME_LABEL.get(oc, oc)] += 1

        if fdate_dt:
            hourly[fdate_dt.strftime('%H:00')][pop] += 1

        when = _parse_dt(raw.get('interview_end')) or s.submitted_at
        dkey = when.strftime('%Y-%m-%d') if when else None
        if dkey:
            daily[dkey][pop] += 1
            df = day_flags[dkey]
            df[pop] += 1
            df['total'] += 1
            ok = {'1': 'completed', '2': 'partial', '3': 'refused', '4': 'interrupted'}.get(oc)
            if ok:
                df[ok] += 1

        dm = _duration_min(raw)
        # A row's duration is trustworthy when it carries the in-interview end
        # stamp (interview_end_actual) — then it is a real interview length, long
        # or short. Rows without it fall back to submit time; those are treated as
        # "left open" only when the submit-lag estimate exceeds LONG_MINUTES.
        true_end = _has_true_end(raw)
        trustworthy = true_end or (dm is not None and dm <= LONG_MINUTES)
        left_open = dm is not None and not true_end and dm > LONG_MINUTES
        if true_end:
            true_end_n += 1
            if dm is not None:
                valid_timing_n += 1                 # usable start AND in-form end
                if dm <= LONG_MINUTES:
                    valid_median_set.append(dm)     # extremes stay out of the median
        if dm is not None:
            durations.append(dm)
            if trustworthy:
                real_durations.append(dm)
            b = _band(dm, DURATION_BANDS)
            if b:
                dur_band[b] += 1

        lat, lng = s.latitude, s.longitude
        if lat is not None and lng is not None:
            gps_ok += 1
            points.append({'lat': float(lat), 'lng': float(lng), 'pop': pop,
                           'district': dist, 'outcome': OUTCOME_LABEL.get(oc, '')})
        else:
            gps_missing += 1
            if dkey:
                day_flags[dkey]['gps_missing'] += 1

        c = coll[dc]
        c['n'] += 1
        c['pop'][pop] += 1
        # Only trustworthy durations feed an enumerator's average. A form left open
        # for nine hours (no in-interview end stamp, submit hours later) measures
        # their working day, not how long they sat with a respondent — averaging it
        # in made careful enumerators look like outliers.
        if dm is not None and trustworthy:
            c['dur'].append(dm)
        if true_end and dm is not None:
            c['valid'] += 1                          # usable start+end timing
            if dm <= LONG_MINUTES:
                c['med'].append(dm)                  # median over valid, non-extreme
        if oc == '1':
            c['complete'] += 1
        if dm is not None and dm < SHORT_MINUTES:
            c['short'] += 1
            short_rows.append({'collector': dc, 'district': dist, 'minutes': dm,
                               'population': pop, 'date': dkey or ''})
            if dkey:
                day_flags[dkey]['rushed'] += 1
        if left_open:
            c['long'] += 1
            long_rows.append({'collector': dc, 'district': dist, 'minutes': dm,
                              'population': pop, 'date': dkey or ''})

        # A duplicate is the SAME interview uploaded more than once: submission_id
        # is a per-form-instance id (collector + area + the moment the interview
        # was opened), so a repeat means the same questionnaire was submitted twice
        # — a double-tap on Submit, or a saved draft re-sent. Keep the offending
        # records so the dashboard can SHOW which ones to go and fix in Kobo.
        sid = raw.get('submission_id')
        if sid:
            id_rows[str(sid)].append({
                'collector': dc, 'district': dist, 'population': pop,
                'date': dkey or '', 'minutes': dm,
            })

    # ── shape outputs ──
    def buckets(counter, top=None):
        items = counter.most_common(top)
        return [{'name': k, 'value': v} for k, v in items]

    collectors = []
    for dc, c in sorted(coll.items(), key=lambda kv: -kv[1]['n']):
        collectors.append({
            'code': dc, 'n': c['n'],
            'avg_min': round(sum(c['dur']) / len(c['dur']), 1) if c['dur'] else None,
            # Valid timing = usable start + in-form end; median over valid,
            # non-extreme records only (never a submit-lag estimate).
            'valid_timing': c['valid'],
            'valid_timing_pct': round(100 * c['valid'] / c['n']) if c['n'] else 0,
            'median_min': _median(c['med']),
            'completion_pct': round(100 * c['complete'] / c['n']) if c['n'] else 0,
            'short': c['short'], 'long': c['long'],
            'hijra': c['pop'].get('hijra', 0), 'fsw': c['pop'].get('fsw', 0),
        })

    # `duplicates` counts the EXTRA copies (3 uploads of one interview = 2 extras),
    # and duplicate_rows names them so the team can act instead of guessing.
    dup_groups = {sid: rows for sid, rows in id_rows.items() if len(rows) > 1}
    duplicates = sum(len(rows) - 1 for rows in dup_groups.values())
    duplicate_rows = sorted(
        ({'submission_id': sid, 'count': len(rows), 'records': rows}
         for sid, rows in dup_groups.items()),
        key=lambda g: -g['count'],
    )[:20]
    dup_ids = list(dup_groups)[:20]

    daily_series = [{'date': d, 'hijra': daily[d].get('hijra', 0),
                     'fsw': daily[d].get('fsw', 0),
                     'total': daily[d].get('hijra', 0) + daily[d].get('fsw', 0)}
                    for d in sorted(daily)]

    progress = []
    for pop in ('hijra', 'fsw'):
        tgt = TARGETS.get(pop) or 0
        got = by_pop.get(pop, 0)
        progress.append({'population': pop, 'collected': got,
                         'target': tgt or None,
                         'pct': round(100 * got / tgt) if tgt else None})

    days = [{'date': d, **day_flags[d]} for d in sorted(day_flags)]

    # THE headline duration: the mean length of an actual interview. A row counts
    # when it carries the in-interview end stamp (interview_end_actual, frozen at
    # the outcome question) OR — for older rows without it — when the submit-lag
    # estimate is still under LONG_MINUTES. Forms left open are excluded, because
    # they measure the enumerator's session, not the interview; including them put
    # the "average" at 307m for a ~50-minute questionnaire. `avg_min` below keeps
    # the raw, unfiltered mean so the exclusion stays visible rather than hidden.
    interview_avg = round(sum(real_durations) / len(real_durations), 1) if real_durations else None

    return {
        'total': total,
        'by_status': {k: by_status[k] for k in by_status},
        'progress': progress,
        'targets': TARGETS,
        'outcomes': buckets(outcomes),
        'districts': buckets(district),
        'sites': buckets(site, 15),
        'daily': daily_series,
        # By collection hour (interview_start) — the trend chart uses this when
        # the filtered range is a single day, where a daily series is one dot.
        'hourly': [{'hour': h, 'hijra': hourly[h].get('hijra', 0),
                    'fsw': hourly[h].get('fsw', 0),
                    'total': sum(hourly[h].values())} for h in sorted(hourly)],
        'days': days,
        'versions': buckets(versions),
        'duration': {
            'bands': [{'name': lab, 'value': dur_band.get(lab, 0)}
                      for _, _, lab in DURATION_BANDS],
            # Raw mean over EVERY timed record, forms-left-open included. Kept only
            # so the filtered figure can be compared against it; do not headline it.
            'avg_min': round(sum(durations) / len(durations), 1) if durations else None,
            'median_min': _median(durations),
            # The average length of an actual interview — headline this.
            'interview_avg_min': interview_avg,
            'interview_n': len(real_durations),
            # Median of the same set: resistant to a single stray long record.
            'typical_min': _median(real_durations),
            'measured': len(durations),
            # How many timed rows carry the in-interview end stamp. Once every row
            # has it, "left open" goes to 0 and the average needs no exclusions.
            'true_end_n': true_end_n,
            # Valid timing coverage: usable start AND in-form end ÷ ALL filtered
            # interviews. Missing end times stay in the denominator but never
            # become a duration.
            'valid_timing_n': valid_timing_n,
            'valid_timing_pct': round(100 * valid_timing_n / total, 1) if total else 0,
            # Headline median: valid records only, extremes (> LONG_MINUTES)
            # excluded per the anomaly rules. IQR for the small-print range.
            'valid_median_min': _median(valid_median_set),
            'valid_median_n': len(valid_median_set),
            'valid_iqr': list(_quartiles(valid_median_set)),
        },
        'collectors': collectors,
        'quality': {
            'gps_ok': gps_ok, 'gps_missing': gps_missing,
            'gps_pct': round(100 * gps_ok / total) if total else 0,
            'duplicates': duplicates, 'duplicate_ids': dup_ids,
            'duplicate_rows': duplicate_rows,
            'short_interviews': len(short_rows),
            'short_minutes': SHORT_MINUTES,
            'long_interviews': len(long_rows),
            'long_minutes': LONG_MINUTES,
            'long_rows': sorted(long_rows, key=lambda r: -r['minutes'])[:20],
            'short_rows': sorted(short_rows, key=lambda r: r['minutes'])[:20],
        },
        'map_points': points,
    }
