"""In-process periodic reconciliation so the CIPRB health strip stays fresh.

Runs `reconcile_ciprb` on a timer and stores a snapshot, which the dashboard
reads via /api/mpdsr/reconciliation/. This is the same pattern as
programs/resync_loop.py (Railway can't add a cron schedule from the CLI), but it
is HEAVIER — each tick pulls every current CIPRB submission for all forms and
replays them through the handlers inside a rolled-back savepoint — so it runs on
a long interval and is OFF by default.

Nothing the tick writes to the domain tables persists: the replay is rolled back
inside a savepoint and only the snapshot row is committed (see
mpdsr.reconcile.run_and_store). It never sends an alert of any kind — the stored
snapshot, surfaced on the dashboard, is the whole point.

Enable with ENABLE_RECON_LOOP=1 on the web service. A Railway cron service
running `python manage.py reconcile_ciprb` on a schedule is an equivalent and
isolation-wise cleaner alternative; running both is harmless (each tick just
writes a fresh snapshot and the newest wins).
"""
import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()

# Long delay past the boot/migrate window before the first run.
_INITIAL_DELAY_SEC = 180


def _truthy(v) -> bool:
    return str(v or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _is_server_process() -> bool:
    """True only when we are the long-lived web server (gunicorn).

    ready() also runs inside every short-lived boot command (migrate, the
    backfills, the seeds), each of which would otherwise start its own thread.
    A reconciliation tick is heavy (a full Kobo pull + replay), so we use an
    ALLOWLIST — start under gunicorn only — instead of trying to enumerate
    every one-shot command. That guarantees exactly one loop under the
    Dockerfile's `gunicorn --workers 1`.
    """
    prog = os.path.basename((sys.argv or [''])[0] or '').lower()
    return 'gunicorn' in prog


def start_recon_loop() -> None:
    """Start the periodic CIPRB reconciliation daemon once. No-op unless
    ENABLE_RECON_LOOP is set and we are the gunicorn web process. Safe to call
    repeatedly (idempotent)."""
    global _started
    if not _truthy(os.environ.get('ENABLE_RECON_LOOP')):
        return
    if not os.environ.get('KOBO_TOKEN'):
        logger.info('recon-loop: KOBO_TOKEN unset - not starting.')
        return
    if not _is_server_process():
        return
    with _lock:
        if _started:
            return
        _started = True

    try:
        interval_min = max(15, int(os.environ.get('RECON_INTERVAL_MIN', '60')))
    except ValueError:
        interval_min = 60
    interval_sec = interval_min * 60

    def _loop():
        time.sleep(_INITIAL_DELAY_SEC)
        from mpdsr.reconcile import run_and_store
        while True:
            try:
                token = os.environ.get('KOBO_TOKEN', '')
                if token:
                    snap = run_and_store(token)
                    d = snap.data or {}
                    logger.info('recon-loop tick: stranded=%s crashes=%s',
                                d.get('total_stranded'), d.get('total_crashes'))
                    # On drift, log the per-form breakdown so the gap is
                    # actionable straight from the logs (which form, how many)
                    # without needing DB access.
                    for r in d.get('forms', []):
                        if r.get('stranded') or r.get('crashes') or r.get('error'):
                            logger.warning(
                                'recon-loop drift: %s stranded=%s crashes=%s '
                                'kobo=%s app=%s hook_active=%s%s',
                                r.get('slug'), r.get('stranded'), r.get('crashes'),
                                r.get('kobo_count'), r.get('app_rows'),
                                r.get('hook_active'),
                                (' error=%s' % r['error']) if r.get('error') else '')
            except Exception:
                logger.exception('recon-loop tick failed')
            time.sleep(interval_sec)

    threading.Thread(target=_loop, name='ciprb-recon-loop', daemon=True).start()
    logger.info('Started ciprb-recon-loop (every %d min)', interval_min)
