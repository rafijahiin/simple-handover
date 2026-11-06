"""Remove records from Spondon after they are deleted in KoboToolbox.

Why this is a reconciliation and not a webhook
----------------------------------------------
KoboToolbox fires its REST Services hook when a submission is CREATED or
edited. There is no "submission deleted" event, so nothing can be pushed to us.
The only reliable signal is the absence of an id: we ask Kobo which submissions
it still holds and compare that with what we stored.

That inversion is dangerous by nature. "Kobo did not return this id" is the
same observation whether the record was genuinely deleted or the request simply
failed, and acting on a bad read would wipe live programme data. Every guard
below exists to make a partial read impossible to mistake for a deletion:

  * every deployed survey asset must be listed AND fully paged, or the run
    aborts before touching anything;
  * a run that sees zero live ids aborts, because an empty account is far more
    likely to be a broken token than a real mass deletion;
  * a run that would remove more than `max_delete` records aborts and asks for
    an explicit override, so one bad day cannot cascade;
  * nothing is removed without `--apply`; the default is a dry run;
  * and nothing is removed on the strength of a single read. A record has to
    be missing from TWO consecutive passes before it is touched, so a read
    that skips rows costs nothing but a delay.

Records that cannot be deleted because a service record still points at them
are reported as blocked, never force-cascaded. programs.Client carries
on_delete=PROTECT from every clinic, counselling, referral and supply row, so
the database refuses to orphan a woman's service history. That refusal is
correct and is surfaced rather than worked around.

Every removal is written to KoboWithdrawal first, with a snapshot of the row,
so a deletion can always be explained and, if it was a mistake, rebuilt.
"""
import logging
import os

import requests
from django.apps import apps
from django.db import transaction
from django.db.models import ProtectedError
from django.forms.models import model_to_dict
from django.utils import timezone

logger = logging.getLogger(__name__)

KOBO_BASE = 'https://kf.kobotoolbox.org/api/v2'
TIMEOUT = 90
PAGE = 30000

# A run may never remove more than this many records without an explicit
# override. Chosen to be larger than any plausible manual clean-up (the biggest
# so far was 97 duplicate IDs on 2026-08-06) and far smaller than any form's
# record count, so a bad read cannot empty a programme.
MAX_DELETE = 200


class FetchIncomplete(RuntimeError):
    """Kobo could not be read in full, so absence proves nothing."""


def _headers(token):
    return {'Authorization': 'Token ' + token}


def _token():
    tok = os.environ.get('KOBO_TOKEN') or os.environ.get('KOBO_API_TOKEN')
    if not tok:
        raise FetchIncomplete('KOBO_TOKEN is not set')
    return tok


def _get(url, token):
    try:
        r = requests.get(url, headers=_headers(token), timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise FetchIncomplete('%s: %s' % (url, exc))
    if not r.ok:
        raise FetchIncomplete('%s: HTTP %s' % (url, r.status_code))
    try:
        return r.json()
    except ValueError as exc:
        raise FetchIncomplete('%s: bad JSON (%s)' % (url, exc))


def deployed_assets(token):
    """Every deployed survey asset on the account."""
    out, url = [], (KOBO_BASE + '/assets/?limit=200'
                    '&fields=["uid","name","asset_type","has_deployment"]')
    while url:
        data = _get(url, token)
        out.extend(a for a in data.get('results', [])
                   if a.get('asset_type') == 'survey' and a.get('has_deployment'))
        url = data.get('next')
    if not out:
        raise FetchIncomplete('no deployed survey assets returned')
    return out


def live_submission_ids(token=None, stdout=None):
    """The set of submission ids KoboToolbox still holds, across every form.

    Raises FetchIncomplete rather than returning a partial set: a short read
    here would look exactly like a mass deletion to the caller.
    """
    token = token or _token()
    ids, per_asset = set(), {}
    for asset in deployed_assets(token):
        uid = asset['uid']
        # Sorted by _id. Kobo pages by offset, so without a deterministic
        # order a submission arriving mid-read shifts the window and rows are
        # skipped. That is not theoretical: a read on 2026-08-26 missed 26
        # live submissions, 22 of them CIPRB response plan actions, and would
        # have deleted every one of them as "no longer in Kobo".
        url = ('%s/assets/%s/data/?fields=["_id"]&sort={"_id":1}&limit=%d'
               % (KOBO_BASE, uid, PAGE))
        n = 0
        while url:
            data = _get(url, token)
            for row in data.get('results', []):
                sid = row.get('_id')
                if sid is not None:
                    ids.add(str(sid))
                    n += 1
            url = data.get('next')
        per_asset[asset.get('name') or uid] = n
        if stdout:
            stdout('  %-46s %6d' % ((asset.get('name') or uid)[:46], n))
    if not ids:
        raise FetchIncomplete(
            'every form reported zero submissions; refusing to treat that as '
            'a mass deletion')
    return ids, per_asset


# The audit table records a submission id so a withdrawal can be traced back,
# which means a naive field scan picks it up as a Kobo-sourced record and the
# trail would delete itself on the next run.
NEVER_SCAN = {'programs.KoboWithdrawal', 'programs.KoboSyncRun'}


def submission_models():
    """Every model that stores a KoboToolbox submission id."""
    out = []
    for model in apps.get_models():
        if model._meta.label in NEVER_SCAN:
            continue
        try:
            model._meta.get_field('kobo_submission_id')
        except Exception:
            continue
        out.append(model)
    return out


def find_withdrawn(live_ids, org=None):
    """Rows whose Kobo submission no longer exists.

    Records with no kobo_submission_id are never touched: they were entered in
    the dashboard by hand or seeded, and Kobo has no opinion about them.

    `org` scopes the sweep to one implementing partner. A deletion request
    always comes from one organisation, and acting on another partner's records
    on the back of it is how a Bandhu clean-up quietly removes CIPRB response
    plan actions. Models that carry no organisation are skipped entirely when a
    scope is given, rather than being swept in on a guess.
    """
    found = []
    for model in submission_models():
        if org:
            if 'organisation' not in {f.name for f in model._meta.get_fields()}:
                continue
        qs = (model.objects
              .exclude(kobo_submission_id__isnull=True)
              .exclude(kobo_submission_id=''))
        if org:
            qs = qs.filter(organisation=org)
        for obj in qs.only('id', 'kobo_submission_id').iterator():
            if str(obj.kobo_submission_id) not in live_ids:
                found.append((model, obj))
    return found


def _snapshot(obj):
    try:
        data = model_to_dict(obj)
    except Exception:
        data = {}
    return {k: (str(v) if v is not None else None) for k, v in data.items()}


def withdraw(rows, actor='', max_delete=MAX_DELETE, force=False):
    """Delete the given rows and record why. Returns (deleted, blocked)."""
    from programs.models import KoboWithdrawal

    if len(rows) > max_delete and not force:
        raise FetchIncomplete(
            '%d records look deleted in Kobo, above the limit of %d. Re-check '
            'the forms before re-running with --force.' % (len(rows), max_delete))

    deleted, blocked = [], []
    for model, ref in rows:
        label = model._meta.label
        obj = model.objects.filter(pk=ref.pk).first()
        if obj is None:
            continue
        entry = KoboWithdrawal(
            model_label=label,
            record_pk=str(obj.pk),
            kobo_submission_id=str(obj.kobo_submission_id or ''),
            organisation=str(getattr(obj, 'organisation', '') or ''),
            approval_status=str(getattr(obj, 'approval_status', '') or ''),
            snapshot=_snapshot(obj),
            actor=actor,
        )
        try:
            with transaction.atomic():
                entry.save()
                obj.delete()
        except ProtectedError as exc:
            # A service record still points at this row. The database is right
            # to refuse: deleting would orphan someone's service history.
            blocked.append((label, str(ref.pk), str(exc)[:160]))
            continue
        deleted.append((label, entry.kobo_submission_id))
        logger.info('withdrew %s %s (kobo %s)', label, ref.pk,
                    entry.kobo_submission_id)
    return deleted, blocked


def confirmed_missing(rows, org=None):
    """Keep only what the previous pass also found missing.

    One read is not evidence. Kobo pages by offset and a submission arriving
    mid-read can push rows out of the window, so a single pass can report a
    record as gone when it is sitting there. Requiring two passes to agree
    turns that from data loss into a delay.
    """
    from programs.models import KoboSyncRun

    prev = KoboSyncRun.objects.filter(org=org or '', error='').first()
    if prev is None:
        return [], set()
    seen = set(prev.candidate_ids or [])
    return [(m, o) for m, o in rows
            if '%s:%s' % (m._meta.label, o.pk) in seen], seen


def _key(model, obj):
    return '%s:%s' % (model._meta.label, obj.pk)


def reconcile(apply=False, actor='', max_delete=MAX_DELETE, force=False,
              org=None, stdout=None):
    """One full pass. Returns a plain dict so callers can report it."""
    say = stdout or (lambda _m: None)
    say('Reading KoboToolbox...')
    live, per_asset = live_submission_ids(stdout=say)
    say('  %d submissions live across %d forms' % (len(live), len(per_asset)))

    rows = find_withdrawn(live, org=org)
    repeat, _seen = confirmed_missing(rows, org=org)
    result = {
        'checked_at': timezone.now().isoformat(),
        'live_ids': len(live),
        'org': org or 'all',
        'assets': per_asset,
        'candidates': [(m._meta.label, str(o.pk), str(o.kobo_submission_id))
                       for m, o in rows],
        'candidate_keys': [_key(m, o) for m, o in rows],
        'confirmed': [(m._meta.label, str(o.pk), str(o.kobo_submission_id))
                      for m, o in repeat],
        'deleted': [],
        'blocked': [],
        'applied': bool(apply),
    }
    if not rows:
        say('Nothing to withdraw: every stored record still exists in Kobo.')
        return result
    say('%d record(s) are no longer in Kobo%s; %d of those were also missing '
        'last pass.' % (len(rows), ' for %s' % org if org else '', len(repeat)))
    if not apply:
        say('Dry run. Re-run with --apply to remove the confirmed ones.')
        return result
    if not repeat:
        say('Nothing confirmed by a second pass yet, so nothing removed.')
        return result
    deleted, blocked = withdraw(repeat, actor=actor, max_delete=max_delete,
                               force=force)
    result['deleted'] = deleted
    result['blocked'] = blocked
    say('Removed %d, blocked %d.' % (len(deleted), len(blocked)))
    return result
