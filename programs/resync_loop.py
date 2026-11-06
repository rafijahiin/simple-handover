"""In-process periodic backstop that runs `resync_client_csvs` on a timer.

Railway cron services can only be created from the dashboard (the CLI can't add
a cron schedule), so to guarantee the client-CSV self-heal actually runs in
production — without depending on a manual dashboard step that's easy to forget —
the web process starts a single daemon thread that calls the idempotent
`resync_client_csvs` command every CSV_RESYNC_INTERVAL_MIN minutes.

That command is QUIET when everything is in sync and only re-uploads/redeploys a
form on drift or a recent client change, so running it on a short timer is cheap
and safe. The whole point is self-healing: a signal push that got dropped on a
worker recycle (the failure behind "FSW registered but Service Log says not
registered") is reconciled within one tick instead of being permanent.

Enable with ENABLE_CSV_RESYNC_LOOP=1 on the web service. With gunicorn
--workers 1 exactly one loop runs. If the process is recycled the loop restarts
on the next boot and the next tick reconciles any drift.

A Railway cron service running `python manage.py resync_client_csvs` every
10-15 min is an equivalent (and isolation-wise cleaner) alternative — running
both is harmless because the command is idempotent.
"""
import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()

# Short-lived manage.py subcommands whose process also calls AppConfig.ready().
# They exit within seconds (before the loop's initial delay), so their threads
# die harmlessly — but starting them is pointless noise. Skip them; anything
# not in this set (gunicorn, runserver) is treated as a long-lived server and
# DOES start the loop, so we never accidentally disable the real path.
_ONE_SHOT_COMMANDS = {
    'migrate', 'makemigrations', 'seed_users', 'seed_centers',
    'backfill_f4_facility', 'backfill_worker_name', 'purge_phd_data',
    'prune_phd_centres', 'seed_demo_mpdsr', 'seed_demo_phd_bandhu',
    'seed_demo_fistula', 'seed_targets', 'collectstatic', 'check',
    'resync_client_csvs', 'shell', 'test', 'createsuperuser',
}

# Wait past the boot/migrate window before the first run, so a thread spawned in
# the short-lived `migrate` process (ready() runs there too) never fires before
# that process exits.
_INITIAL_DELAY_SEC = 150


def _truthy(v) -> bool:
    return str(v or '').strip().lower() in ('1', 'true', 'yes', 'on')


def start_resync_loop() -> None:
    """Start the periodic resync daemon once. No-op unless
    ENABLE_CSV_RESYNC_LOOP is set. Safe to call repeatedly (idempotent)."""
    global _started
    if not _truthy(os.environ.get('ENABLE_CSV_RESYNC_LOOP')):
        return
    argv = sys.argv or []
    if len(argv) > 1 and argv[1] in _ONE_SHOT_COMMANDS:
        return
    with _lock:
        if _started:
            return
        _started = True

    try:
        interval_min = max(2, int(os.environ.get('CSV_RESYNC_INTERVAL_MIN', '10')))
    except ValueError:
        interval_min = 10
    interval_sec = interval_min * 60

    def _loop():
        time.sleep(_INITIAL_DELAY_SEC)
        from django.core.management import call_command
        while True:
            try:
                call_command('resync_client_csvs')
            except Exception:
                logger.exception('resync_client_csvs loop tick failed')
            time.sleep(interval_sec)

    threading.Thread(target=_loop, name='csv-resync-loop', daemon=True).start()
    logger.info('Started csv-resync-loop (every %d min)', interval_min)
