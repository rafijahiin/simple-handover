"""Run the Kobo deletion sweep on a schedule, inside the web process.

Why in-process and not a cron service
-------------------------------------
The programme runs on one Railway service with a hard ceiling of five dollars a
month. A second service purely to run one command a day would be a large share
of that budget. A daemon thread inside the existing worker costs effectively
nothing: one pass is about two dozen HTTPS reads and a primary-key scan.

The worker recycles every 500 requests, so the thread dies and is recreated
often. That is why the schedule lives in the database (KoboSyncRun) rather than
in memory: on start the thread asks when the last pass finished, not how long
it has personally been alive. Without that, a busy day would run the sweep
dozens of times.

Safety
------
An unattended pass deletes with a much tighter cap than a person would use. A
human running the command can look at what they are about to remove and pass
--force; a thread cannot, so anything larger than AUTO_MAX_DELETE is recorded
and left for a person. Every other guard in kobo_withdrawals applies unchanged,
including the refusal to act on a partial read of KoboToolbox.

Disabled unless KOBO_DELETION_SYNC names the organisations to sweep, so it can
never start acting on a deployment nobody meant to enable it on.
"""
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# A person can review a large removal before confirming it. A background thread
# cannot, so it stops well short of the manual cap and asks for one.
AUTO_MAX_DELETE = 25

DEFAULT_INTERVAL_HOURS = 6
# How often the thread wakes to ask whether a pass is due. Short enough that a
# recycled worker picks the schedule up quickly, long enough to cost nothing.
TICK_SECONDS = 900


def _orgs():
    """Organisations to sweep, from KOBO_DELETION_SYNC.

    'Bandhu,PHD' sweeps those two. 'all' sweeps everything, including records
    that carry no organisation. Unset means the sweep never runs.
    """
    raw = (os.environ.get('KOBO_DELETION_SYNC') or '').strip()
    if not raw:
        return []
    if raw.lower() == 'all':
        return [None]
    return [o.strip() for o in raw.split(',') if o.strip()]


def _interval():
    try:
        return max(1.0, float(os.environ.get('KOBO_DELETION_SYNC_HOURS',
                                             DEFAULT_INTERVAL_HOURS)))
    except ValueError:
        return DEFAULT_INTERVAL_HOURS


def _due(org, hours):
    from django.utils import timezone
    from datetime import timedelta
    from programs.models import KoboSyncRun

    last = KoboSyncRun.objects.filter(org=org or '').first()
    if last is None:
        return True
    return timezone.now() - last.created_at >= timedelta(hours=hours)


def run_once(org):
    """One pass for one organisation. Never raises; records what happened."""
    from programs.kobo_withdrawals import FetchIncomplete, reconcile
    from programs.models import KoboSyncRun

    row = KoboSyncRun(org=org or '', applied=True)
    try:
        r = reconcile(apply=True, actor='auto-sync',
                      max_delete=AUTO_MAX_DELETE, force=False, org=org)
        row.candidates = len(r['candidates'])
        row.candidate_ids = r['candidate_keys']
        row.deleted = len(r['deleted'])
        row.blocked = len(r['blocked'])
        row.live_ids = r['live_ids']
        if r['deleted'] or r['blocked']:
            logger.info('kobo sync %s: removed %d, blocked %d',
                        org or 'all', row.deleted, row.blocked)
    except FetchIncomplete as exc:
        # Includes both a partial read of Kobo and a removal too large to do
        # unattended. Either way nothing was changed.
        row.error = str(exc)[:900]
        logger.warning('kobo sync %s aborted: %s', org or 'all', exc)
    except Exception as exc:                       # pragma: no cover - defensive
        row.error = '%s: %s' % (type(exc).__name__, exc)
        logger.exception('kobo sync %s failed', org or 'all')
    row.save()
    return row


def _loop():
    hours = _interval()
    while True:
        try:
            for org in _orgs():
                if _due(org, hours):
                    run_once(org)
        except Exception:                          # pragma: no cover - defensive
            # The thread must outlive any single failure, including the
            # database being briefly unreachable during a deploy.
            logger.exception('kobo sync loop error')
        time.sleep(TICK_SECONDS)


def start():
    """Start the sweep thread if it is switched on. Safe to call twice."""
    if not _orgs():
        return False
    if any(t.name == 'kobo-deletion-sync' for t in threading.enumerate()):
        return False
    threading.Thread(target=_loop, name='kobo-deletion-sync',
                     daemon=True).start()
    logger.info('kobo deletion sync started for %s every %.0fh',
                _orgs(), _interval())
    return True
