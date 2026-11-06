"""
Programs app signals.

Keep the per-org clients CSV (phd_clients.csv / bandhu_clients.csv) attached to
the Kobo forms in sync with the live Client table. The Service Log / Mother List
forms use pulldata() against that CSV to auto-fill a client's identity when a
field worker types an ID — if the CSV is stale, every newly-registered client
looks "not in the list" until a manual export is run.

Strategy:
  * Hook post_save on Client; react for PHD and Bandhu (the orgs that use
    pulldata). CIPRB does not.
  * transaction.on_commit so we only push after the row is actually persisted.
  * Run the network call in a daemon thread so the webhook response is not
    blocked by Kobo's API. Idempotent — a second push just replaces the first.
  * Debounce bursts (a flood of registrations / re-seed) into one push, and
    coalesce per-org so a mixed PHD+Bandhu burst still pushes each once.
"""
import hashlib
import logging
import os
import threading
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Client

logger = logging.getLogger(__name__)

# org → export command module (each exposes build_csv / upload_to_kobo /
# redeploy_forms with the same signature).
_ORG_EXPORT = {
    'PHD':    'programs.management.commands.export_phd_clients',
    'Bandhu': 'programs.management.commands.export_bandhu_clients',
    # CIPRB fistula registry — sourced from CIPRBFistulaCase, not Client.
    # Pushed by the _fistula_case_changed receiver below (Client never carries
    # the 'Fistula' org), so it shares the same debounce / daemon machinery.
    'Fistula': 'programs.management.commands.export_fistula_clients',
    # CIPRB MPDSR Action Plan — sourced from MPDSRAction. Pushed by the
    # _mpdsr_action_changed receiver below so the 'update an action' dropdown
    # always lists the current open actions.
    'MPDSRAction': 'programs.management.commands.export_mpdsr_actions',
}

_DEBOUNCE_SECONDS = 2.0
_lock = threading.Lock()
_timer: Optional[threading.Timer] = None
_pending_orgs = set()

# org → sha256 of the CSV bytes Kobo last ACCEPTED from this process.
#
# Most Client saves do not touch an exported column: a service log stamping
# updated_at, an approval flag, a status change. Each one still scheduled a
# push, so byte-identical CSVs were re-uploaded and three forms redeployed all
# day (487 uploads / 484 redeploys in a measured 24h, the bulk of the egress
# bill). Skipping an unchanged push is invisible to the field: a real
# registration or edit changes the CSV, and build_csv exports identity columns
# only — no timestamps — so equal bytes mean nothing a worker would see moved.
#
# Deliberately in memory and per-process. gunicorn recycles the worker every
# 500 requests, so the cache empties often and the next push re-uploads. That
# makes the guard fail-open: it can only ever make the system less chatty, never
# more stale. Genuine Kobo-side drift is not this cache's problem either — the
# resync_client_csvs backstop compares against what is actually attached to the
# form every 10 minutes and heals it.
#
# Its own lock: the debounce machinery above serialises a different thing, and
# a push holds this one only across a dict read or write, never across the
# network calls.
_last_push_hash: dict = {}
_hash_lock = threading.Lock()


def reset_push_cache() -> None:
    """Forget which CSVs were last pushed, so the next push re-uploads."""
    with _hash_lock:
        _last_push_hash.clear()


def _load_export(org: str):
    """The export command module for an org. Seam for tests."""
    import importlib
    return importlib.import_module(_ORG_EXPORT[org])


def _push_org(org: str) -> None:
    """Build + upload + redeploy one org's clients CSV. Off the request thread.

    No-op when the CSV is byte-identical to the last one Kobo accepted."""
    try:
        mod = _load_export(org)
    except Exception:
        logger.exception('client-csv sync: failed to import export for %s', org)
        return
    if not (getattr(settings, 'KOBO_API_TOKEN', '') or os.environ.get('KOBO_TOKEN', '')):
        logger.info('client-csv sync: KOBO_TOKEN unset — skipping %s push', org)
        return

    class _SilentStdout:
        def write(self, msg):
            logger.info('client-csv sync[%s]: %s', org, str(msg).rstrip())

    try:
        csv_bytes, row_count = mod.build_csv()
        digest = hashlib.sha256(csv_bytes or b'').hexdigest()
        with _hash_lock:
            unchanged = _last_push_hash.get(org) == digest
        if unchanged:
            logger.debug('client-csv sync[%s]: unchanged (%d rows) — skipped',
                         org, row_count)
            return
        if mod.upload_to_kobo(csv_bytes, _SilentStdout()):
            # Redeploy so Enketo re-transforms with the fresh CSV — the media
            # swap alone is invisible to the field forms until then.
            redeployed = mod.redeploy_forms(_SilentStdout())
            # Only remember a push that fully landed. BOTH halves report failure
            # by returning False rather than raising: upload_to_kobo when any
            # form's media POST is rejected, redeploy_forms when a version fetch
            # or PATCH fails. Caching either partial result would suppress the
            # re-push on the next save — and a CSV that uploaded but never got
            # redeployed is exactly the "registered, but the form says not in
            # the list" failure this whole path exists to prevent.
            if redeployed:
                with _hash_lock:
                    _last_push_hash[org] = digest
        logger.info('client-csv sync[%s]: pushed %d rows', org, row_count)
    except Exception:
        logger.exception('client-csv sync[%s]: push failed', org)


def _do_push() -> None:
    with _lock:
        orgs = list(_pending_orgs)
        _pending_orgs.clear()
    for org in orgs:
        _push_org(org)


def _schedule_push(org: str) -> None:
    """Reset the debounce timer; the actual push fires in a daemon thread."""
    global _timer
    with _lock:
        _pending_orgs.add(org)
        if _timer is not None:
            _timer.cancel()

        def _fire() -> None:
            t = threading.Thread(target=_do_push, daemon=True, name='client-csv-sync')
            t.start()

        _timer = threading.Timer(_DEBOUNCE_SECONDS, _fire)
        _timer.daemon = True
        _timer.start()


@receiver(post_save, sender=Client)
def _client_changed(sender, instance: Client, created: bool, **kwargs):
    """Refresh the org's clients CSV on any PHD / Bandhu Client insert or update.

    build_csv drops stubs (empty / 'Unknown' name), so an incomplete service
    stub is silently ignored until a real registration sets a name."""
    org = instance.organisation
    if org not in _ORG_EXPORT:
        return
    transaction.on_commit(lambda: _schedule_push(org))


# The CIPRB fistula registry lives in a different model (CIPRBFistulaCase), so
# it needs its own receiver. Any insert/update — a Suspected-stage registration
# adding a new patient_code, or a later stage touching the row — refreshes the
# fistula_clients.csv so the form's dropdown / pulldata stay current. build_csv
# drops rows without a patient_code + name, so partial rows are ignored.
from fistula.ciprb_models import CIPRBFistulaCase  # noqa: E402


@receiver(post_save, sender=CIPRBFistulaCase)
def _fistula_case_changed(sender, instance: CIPRBFistulaCase, created: bool, **kwargs):
    transaction.on_commit(lambda: _schedule_push('Fistula'))


# CIPRB MPDSR actions live in MPDSRAction; refresh mpdsr_actions.csv on any
# insert/update (a new plan adding actions, or an 'update' moving one forward)
# so the 'update an action' dropdown + pulldata stay current. build_csv drops
# dropped actions, so a cancelled action falls off the list.
from mpdsr.models import MPDSRAction  # noqa: E402


@receiver(post_save, sender=MPDSRAction)
def _mpdsr_action_changed(sender, instance, created: bool, **kwargs):
    transaction.on_commit(lambda: _schedule_push('MPDSRAction'))
