"""Resolve a form slug to the KoboToolbox asset UID this installation uses.

Why this exists
---------------
The CIPRB asset UIDs used to be hardcoded in four places: the replay map, the
reconciliation loop, the two lookup-CSV exporters and the system_ref
write-back. That is correct for exactly one KoboToolbox account.

When the system is handed to another organisation, they deploy the same
XLSForms in their own account and every UID changes. With the UIDs hardcoded,
that installation would keep reading from, and trying to write into, forms it
does not own. The write-backs fail, the lookup CSVs never attach, and the
reconciliation loop reports every form as missing.

Resolution order
----------------
1. ``KOBO_ASSET_UID_<SLUG>`` in the environment, upper-cased, as an explicit
   override. ``ciprb_near_miss_v1`` becomes ``KOBO_ASSET_UID_CIPRB_NEAR_MISS_V1``.
2. ``indicators.KoboFormMapping.kobo_asset_uid`` for that slug. This is the
   normal route: the setup guide has the administrator fill this table in once,
   and everything else follows from it.
3. The built-in default below, which is the account the system was first
   deployed against.

Routing does not depend on any of this. Submissions are routed by the form id
inside the XLSForm, which survives being imported into another account. These
UIDs are only for the calls this system makes *out* to KoboToolbox.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# The account this system was first deployed against. Used only when nothing
# else supplies a UID, so an installation that has not been configured still
# behaves as it always did.
DEFAULT_CIPRB_SLUG_TO_UID: dict[str, str] = {
    'ciprb_fistula_questions_v1':        'aH86Euq2AeJ8S9VYdry4PC',
    'ciprb_fistula_campaign_v1':         'aso6xsUo8PMYRCzGQBc8Cm',
    'ciprb_mpdsr_community_maternal_v1': 'apvPk7qq94nry2aW3z7y4H',
    'ciprb_mpdsr_community_neonatal_v1': 'awQXeYhuLoLrM38fwSrF8y',
    'ciprb_mpdsr_facility_maternal_v1':  'aVQbxhGnDHNCe6AazSJByM',
    'ciprb_mpdsr_facility_neonatal_v1':  'a6pg47mTt8E56igHnK8SSD',
    'ciprb_social_autopsy_v1':           'a6vQiCJ3tz4MRxKqdMHCbA',
    'ciprb_notification_slip_01_v1':     'aSnEgQT6DUooVanZXubhAF',
    'ciprb_notification_slip_02_v1':     'aaCnfRHHgkukkhDgXwUnXX',
    'ciprb_near_miss_v1':                'aTzdRTvhZ8yUQCGhA8UG5R',
    'ciprb_mpdsr_response_plan_v1':      'auFCf7bfBDtrP6xeW5F2KJ',
    'ciprb_safe_surgery_v1':             'a7YYwChtSu7cdrMZQtxUKT',
}


def _from_env(slug: str) -> str:
    return os.environ.get('KOBO_ASSET_UID_%s' % slug.upper(), '').strip()


def _from_db(slug: str) -> str:
    """The registry row, if the table is reachable.

    Deliberately swallows everything. This is called from webhook handlers and
    from the boot path, where the table may not exist yet during a migrate, and
    a lookup failure must never take a submission down with it.
    """
    try:
        from indicators.models import KoboFormMapping
        return (KoboFormMapping.objects
                .filter(form_slug=slug)
                .values_list('kobo_asset_uid', flat=True)
                .first() or '').strip()
    except Exception:  # noqa: BLE001
        return ''


def uid_for(slug: str, default: str = '') -> str:
    """The asset UID this installation should use for ``slug``."""
    if not slug:
        return default
    return (_from_env(slug)
            or _from_db(slug)
            or DEFAULT_CIPRB_SLUG_TO_UID.get(slug, '')
            or default)
