"""Shared helper: which configured service centres are actually FUNCTIONAL.

The "operational/established/functional centres" indicators (Bandhu 1.6, 1.8;
PHD SL8) used to count ServiceCenter CONFIG rows directly. That meant a freshly
seeded system — every centre pre-loaded but zero field activity — reported those
indicators at 100% and flagged them "on track", which is wrong: a programme that
has delivered nothing yet has no functional centres.

A centre is FUNCTIONAL in a period when the programme has actually delivered a
service through it — i.e. there is at least one APPROVED programme record
referencing that centre in the period. A configured-but-idle centre reads 0
until real activity arrives, and the count then climbs as centres come online.
"""
from django.apps import apps

_APPROVED = 'APPROVED'

# A nil/zero report at a centre means NO service was delivered that day, so it
# must NOT mark the centre functional.
_EXCLUDE_MODELS = {'NilReport'}


def active_center_ids(period_start, period_end, base_qs):
    """Return the subset of `base_qs` ServiceCenter ids that have >=1 approved
    programme service record referencing them within [period_start, period_end].

    base_qs is a ServiceCenter queryset already filtered to the indicator's
    config criteria (org, type, district). Returns a set of ids.
    """
    config_ids = set(base_qs.values_list('id', flat=True))
    if not config_ids:
        return set()

    active = set()
    for model in apps.get_app_config('programs').get_models():
        if model.__name__ in _EXCLUDE_MODELS:
            continue
        field_names = {f.name for f in model._meta.get_fields()}
        if not {'center', 'approval_status', 'created_at'} <= field_names:
            continue
        ids = (
            model.objects.filter(
                approval_status=_APPROVED,
                center_id__in=config_ids,
                created_at__date__range=(period_start, period_end),
            )
            .values_list('center_id', flat=True)
            .distinct()
        )
        active.update(ids)
        if len(active) == len(config_ids):
            break  # every candidate centre already proven active
    return active
