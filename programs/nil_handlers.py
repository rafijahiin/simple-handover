"""
Webhook handler for the shared "No Reporting Today" Kobo form (no_report_v1).

A field worker (any centre, any partner) submits a zero-day return on a day the
centre had no activity. It records a NilReport at PENDING, so it flows through
the SAME review as any submission (PHD/CIPRB manager; Bandhu manager → UNFPA),
and it already counts toward the centre's daily reporting the moment it lands
(see tracker.programs_query.daily_reporting_activity, which counts NilReports of
any status) — so the centre stops being flagged "silent" immediately.

The partner is derived from the chosen centre, never trusted from the wire, so
one shared form serves PHD, Bandhu and CIPRB without any cross-org confusion.
"""
import logging

from django.http import HttpResponse
from django.utils import timezone

from .webhook import _str, _date, _base_kwargs
from .models import ServiceCenter, NilReport

logger = logging.getLogger(__name__)

_REASON_LABELS = {
    'centre_closed': 'Centre closed',
    'holiday':       'Holiday',
    'no_clients':    'No clients / no activity',
    'staff_absent':  'Staff absent',
    'other':         'Other',
}


def handle_no_report(payload, lat, lng):
    code = _str(payload.get('center_code')) or _str(payload.get('centre_id'))
    center = (ServiceCenter.objects.filter(code=code, is_active=True).first()
              if code else None)
    if center is None:
        return HttpResponse('center not found', status=400)

    org = center.organisation
    rdate = _date(payload.get('report_date')) or timezone.localdate()

    reason = _REASON_LABELS.get(_str(payload.get('nr_reason')),
                                _str(payload.get('nr_reason')) or 'No reporting today')
    note = _str(payload.get('nr_note'))
    if note:
        reason = f'{reason} — {note}'

    # One nil-report per centre per day (unique constraint on
    # organisation+center+report_date). If a manager — or an earlier field
    # submission — already logged this centre/day, don't duplicate it.
    obj, created = NilReport.objects.get_or_create(
        organisation=org, center=center, report_date=rdate,
        defaults={'reason': reason, **_base_kwargs(payload, lat, lng)},
    )
    if not created:
        return HttpResponse('OK', status=200)
    return HttpResponse('Created', status=201)
