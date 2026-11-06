"""Resolve a Kobo asset UID for one of our form ids, safely.

Why this exists
---------------
Every build command used to look the asset up with

    GET /assets/?q=settings__id_string:<form_id>
    ... and then a.get('settings', {}).get('id_string') == form_id

Both halves are wrong: Kobo keeps the form id in **content.settings.id_string**,
while the asset's top-level `settings` holds only sector/country/description. The
query therefore returns 0 hits and the filter never matches, so the lookup ALWAYS
failed. build_ciprb_forms then silently fell through to "create a new asset",
which is how CIPRB 10 and the Fistula Question Bank each grew a stray duplicate
that had to be archived by hand (2026-08-20). build_bandhu_forms and
build_phd_forms survived only because they had a second, title-based fallback.

The rule here: resolve by evidence, and if we cannot identify the asset with
certainty, STOP. Creating a live-looking duplicate is worse than failing.
"""
import requests

KOBO_BASE = 'https://kf.kobotoolbox.org'
API = KOBO_BASE + '/api/v2'
TIMEOUT = 60


class AssetNotFound(Exception):
    """No asset could be identified for this form id."""


def _headers(token):
    return {'Authorization': 'Token ' + token}


def _survey_assets(token):
    """Every survey asset on the account: [{uid, name, has_deployment}]."""
    out, url = [], (API + '/assets/?limit=200'
                    '&fields=["uid","name","asset_type","has_deployment"]')
    while url:
        r = requests.get(url, headers=_headers(token), timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        out.extend(a for a in data.get('results', [])
                   if a.get('asset_type') == 'survey')
        url = data.get('next')
    return out


def _id_string(uid, token):
    """The form id as Kobo actually stores it: content.settings.id_string."""
    r = requests.get(API + '/assets/' + uid + '/', headers=_headers(token),
                     timeout=TIMEOUT)
    if not r.ok:
        return None
    return (r.json().get('content', {}) or {}).get('settings', {}).get('id_string')


def resolve_asset_uid(form_id, title, token, *, allow_create=False, stdout=None):
    """Return the UID of the asset that holds `form_id`.

    Resolution order, most reliable first:
      1. id_string match  (authoritative: content.settings.id_string == form_id)
      2. exact title match, but only when it is UNAMBIGUOUS (one asset)
      3. create a new asset, ONLY when the caller passed allow_create

    Raises AssetNotFound rather than inventing an asset, so a typo in a form id
    can never again produce a second live-looking copy of a real form.
    """
    def say(msg):
        if stdout is not None:
            stdout.write(msg)

    assets = _survey_assets(token)

    # 1. Authoritative match on the real id_string. Check title matches first so
    #    the common case costs one detail request, not nineteen.
    by_title = [a for a in assets if (a.get('name') or '') == title]
    ordered = by_title + [a for a in assets if a not in by_title]
    for a in ordered:
        if _id_string(a['uid'], token) == form_id:
            say('     matched by id_string: %s' % a['uid'])
            return a['uid']

    # 2. Title match without a usable id_string (older assets Kobo imported
    #    before we started stamping the settings sheet).
    if len(by_title) == 1:
        say('     matched by title: %s' % by_title[0]['uid'])
        return by_title[0]['uid']
    if len(by_title) > 1:
        raise AssetNotFound(
            '%s: %d assets are named %r and none carries id_string %r. Rename or '
            'archive the duplicates in Kobo, then run again.'
            % (form_id, len(by_title), title, form_id))

    # 3. Nothing matched.
    if not allow_create:
        raise AssetNotFound(
            '%s: no Kobo asset carries this id_string and none is named %r. '
            'Refusing to create one, because a silent create is what produces '
            'stray duplicate forms. If this form genuinely does not exist yet, '
            're-run with --allow-create.' % (form_id, title))

    r = requests.post(API + '/assets/', headers=_headers(token),
                      json={'name': title, 'asset_type': 'survey',
                            'settings': {'description': 'CIPRB form ' + form_id}},
                      timeout=TIMEOUT)
    r.raise_for_status()
    uid = r.json()['uid']
    say('     CREATED new asset (--allow-create): %s' % uid)
    return uid
