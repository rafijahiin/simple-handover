"""Replay live CIPRB Kobo payloads through the real handlers.

This is the recovery harness made permanent. It fetches every submission each
CIPRB form holds in Kobo and runs it through the exact handler the webhook would
call (after the same _flatten_group_keys + _geolocation the dispatch does), so a
handler that would 500 on data that ACTUALLY EXISTS is caught — the class behind
the case_hash collision that stranded 90 death records.

Each payload runs in its OWN savepoint: a failure is isolated and recorded, while
a successful write stays visible to later payloads in the same run — so a
cross-payload collision (two case serials colliding on a global unique key)
reproduces exactly as it did in production.

The CALLER owns the outer transaction and MUST roll it back — nothing here is
meant to persist. `replay_ciprb()` never commits.
"""
import requests
from django.db import transaction

from programs.webhook import FORM_HANDLERS, _flatten_group_keys, _geolocation
from programs.kobo_uids import DEFAULT_CIPRB_SLUG_TO_UID, uid_for

KOBO_BASE = 'https://kf.kobotoolbox.org/api/v2'

# slug -> asset UID for the account this system was first deployed against.
# Kept as the DEFAULT only. Use ciprb_slug_to_uid() so an installation that has
# deployed the forms in its own KoboToolbox account resolves its own UIDs.
CIPRB_SLUG_TO_UID = dict(DEFAULT_CIPRB_SLUG_TO_UID)


def ciprb_slug_to_uid() -> dict:
    """The CIPRB slug -> UID map for THIS installation.

    Each slug is resolved through programs.kobo_uids: environment override
    first, then the KoboFormMapping registry, then the default above. Slugs
    that resolve to nothing are left out.
    """
    out = {}
    for slug, fallback in CIPRB_SLUG_TO_UID.items():
        uid = uid_for(slug, fallback)
        if uid:
            out[slug] = uid
    return out


def _fetch(uid, token, limit=None):
    """All submissions for an asset, following pagination.

    Kobo caps a page at 1,000 regardless of the limit asked for. The old
    single-request version silently returned only the first page, which never
    mattered for the CIPRB forms (all under 300) but capped the big partner
    forms at exactly 1,000, so their newest submissions escaped the
    reconciliation. `limit` now means "at most this many, total", for the
    smoke-test path only.
    """
    out = []
    url = '%s/assets/%s/data/?format=json&limit=%d' % (
        KOBO_BASE, uid, min(limit, 1000) if limit else 1000)
    headers = {'Authorization': 'Token ' + token}
    while url:
        r = requests.get(url, headers=headers, timeout=180)
        r.raise_for_status()
        j = r.json()
        out.extend(j.get('results', []))
        if limit and len(out) >= limit:
            return out[:limit]
        url = j.get('next')
    return out


def replay_ciprb(token, slugs=None, limit=None):
    """Replay live payloads for the given CIPRB slugs (default: all). Returns a
    per-slug summary. MUST be called inside a transaction the caller rolls back.

    -> { slug: {'n': int, 'ok': int, 'http4xx': int, 'errors': [ {id, error} ]} }
    """
    resolved = ciprb_slug_to_uid()
    slugs = slugs or list(resolved)
    out = {}
    for slug in slugs:
        uid = resolved.get(slug)
        handler = FORM_HANDLERS.get(slug)
        if not uid or handler is None:
            out[slug] = {'n': 0, 'ok': 0, 'http4xx': 0,
                         'errors': [{'id': None, 'error': 'no uid/handler for slug'}]}
            continue
        subs = _fetch(uid, token, limit)
        rec = {'n': len(subs), 'ok': 0, 'http4xx': 0, 'errors': []}
        for s in subs:
            payload = _flatten_group_keys(s)
            lat, lng = _geolocation(payload)
            try:
                with transaction.atomic():   # savepoint: isolates this payload
                    resp = handler(payload, lat, lng)
                code = getattr(resp, 'status_code', 200)
                if code >= 500:
                    rec['errors'].append({'id': s.get('_id'),
                                          'error': 'HTTP %s' % code})
                elif code >= 400:
                    rec['http4xx'] += 1
                else:
                    rec['ok'] += 1
            except Exception as exc:  # noqa: BLE001 — any handler crash is a failure
                rec['errors'].append({'id': s.get('_id'),
                                      'error': '%s: %s' % (type(exc).__name__, exc)})
        out[slug] = rec
    return out
