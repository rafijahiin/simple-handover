"""Group-key flattening for KoboToolbox payloads.

Kobo serialises grouped questions as 'group/field' (and nested groups as
'a/b/field'). Every analytic in this codebase reads flat leaf names —
`b108_worked`, `q2_1_a`, `c3`, `dc_code`, `population`, `submission_id` — so a
raw payload matches nothing.

THE BUG THIS FIXES (2026-07-10): the D5 baseline webhook stored `raw_data=payload`
unflattened. Real interviews arrived with 258–354 fields, ~339 of them nested
(`grp_fsw_a2/a201`, `grp_module9/c3`, …). The demo seed wrote FLAT keys, so the
dashboard looked healthy right up until real data landed — then every SRHR
indicator read n=0, every submission fell back to 'Unknown' collector and 'hijra'
population, and completion read 0%. The answers were always there; nothing could
see them.

This ADDS a leaf alias and KEEPS the original key, so it can never remove data or
break a handler that reads the prefixed path. Meta keys (_id, _xform_id_string,
_geolocation, _submitted_by) contain no '/', so they pass through untouched.
"""
import logging

logger = logging.getLogger(__name__)


def flatten_group_keys(payload):
    """Add a group-stripped alias for every nested Kobo field. Originals kept."""
    if not isinstance(payload, dict):
        return payload
    flat = dict(payload)
    for key, val in payload.items():
        if '/' not in key:
            continue
        leaf = key.rsplit('/', 1)[-1]
        if not leaf:
            continue
        if leaf in flat:
            # Never let a scalar shadow a repeat LIST (Kobo can emit an
            # empty-string placeholder for a 0-instance repeat).
            if isinstance(val, list) and not isinstance(flat[leaf], list):
                flat[leaf] = val
            elif flat[leaf] != val:
                logger.debug('flatten: leaf %r collision (%r kept)', leaf, leaf)
            continue
        flat[leaf] = val
    return flat
