"""Authoritative key-population resolution for D5 baseline submissions.

A submission's population MUST come from the FORM it was submitted on. Never
default it.

THE BUG THIS FIXES (2026-07-10): Kobo stamps `_xform_id_string`, which on this
deployment carries the ASSET UID ('aVsJ7VJ35k8GshpQpnXygC'), not the readable
id_string ('ciprb_baseline_fsw_v1'). Several call sites did

    population = 'fsw' if 'fsw' in _xform_id_string else 'hijra'

The UID contains no 'fsw', so EVERY FSW interview was silently stored and counted
as Hijra — the dashboard read "Hijra 37 / FSW 0" while 20 of the 37 were FSW.
That corrupts every indicator, because each form asks different questions under
different field names.

Resolution order (first hit wins):
  1. the form's own `population` calculate ('hijra' / 'fsw')
  2. the asset UID / id_string, matched EXACTLY against the known forms
  3. None — caller decides. Do not guess.
"""
import logging

logger = logging.getLogger(__name__)

HIJRA_ASSET = 'aBT7aCL9p4FGcW4WwXZcr6'
FSW_ASSET = 'aVsJ7VJ35k8GshpQpnXygC'

# Both the asset UID (what Kobo actually sends) and the human id_string.
FORM_POPULATION = {
    HIJRA_ASSET.lower(): 'hijra',
    FSW_ASSET.lower(): 'fsw',
    'ciprb_baseline_hijra_v1': 'hijra',
    'ciprb_baseline_fsw_v1': 'fsw',
}

# Keys a Kobo payload may carry that identify the source form.
_FORM_KEYS = ('_xform_id_string', '_userform_id', 'formhub/uuid')


def resolve_population(raw, default=None):
    """raw_data -> 'hijra' | 'fsw' | default. Never guesses from a bare default."""
    raw = raw or {}

    pop = str(raw.get('population') or '').strip().lower()
    if pop in ('hijra', 'fsw'):
        return pop

    for key in _FORM_KEYS:
        val = str(raw.get(key) or '').strip().lower()
        if not val:
            continue
        if val in FORM_POPULATION:
            return FORM_POPULATION[val]
        # `_userform_id` looks like 'account_ciprb_baseline_fsw_v1'
        for token, resolved in FORM_POPULATION.items():
            if token in val:
                return resolved

    logger.error('Baseline population unresolved — form keys: %s',
                 {k: raw.get(k) for k in _FORM_KEYS if raw.get(k)})
    return default
