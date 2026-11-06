"""
Wire the 3 CIPRB indicators (F.C, F.Camp, B) to their backing Kobo forms.

Builds on migration 0006 which left CIPRB rows with source_form=NULL
because the register variables were workshop-pending. The Bengali
Fistula Corner register photo + Sunamganj campaign xlsx confirmed the
shape — fistula.FistulaCornerCase + fistula.FistulaCampaignVisit
models landed in fistula.0003, and indicators.ciprb.ACTIVITY_REGISTRY
now defines the compute fns.

This migration:
  1. Adds two new KoboFormMapping rows for the fistula forms.
  2. Sets IndicatorTarget.source_form on F.C, F.Camp, and B.

Baseline reuses the existing spondon_baseline_v1 mapping (created in
0006). Idempotent: re-running uses update_or_create.
"""
from django.db import migrations


NEW_FORMS = [
    ('spondon_fistula_corner_v1',   'CIPRB Fistula Corner — District Hospital Register', 'CIPRB'),
    ('spondon_fistula_campaign_v1', 'CIPRB Fistula Campaign — House-Visit Screening',    'CIPRB'),
    # spondon_baseline_v1 wasn't in migration 0006 because the legacy
    # webhook routed baseline submissions via asset UID env var. Adding
    # the catalogue row so IndicatorTarget.source_form can point at it.
    ('spondon_baseline_v1',         'CIPRB Baseline & Endline Survey',                   'CIPRB'),
]

# Replace the spondon_baseline_v1 mapping created by 0006 (without a partner)
# with one pinned to CIPRB. The baseline registry is CIPRB-managed.
RETAG_FORMS = {
    'spondon_iec_material_v1': None,    # cross-partner, stay NULL
}

CIPRB_SOURCE_FORM_MAP = {
    'F.C':    'spondon_fistula_corner_v1',
    'F.Camp': 'spondon_fistula_campaign_v1',
    'B':      'spondon_baseline_v1',
}


def _forward(apps, schema_editor):
    Partner = apps.get_model('partners', 'Partner')
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')

    partners_by_code = {p.code: p for p in Partner.objects.all()}
    ciprb = partners_by_code.get('CIPRB')

    # 1) Create the two new fistula form mappings.
    for slug, label, partner_code in NEW_FORMS:
        partner_obj = partners_by_code.get(partner_code) if partner_code else None
        KoboFormMapping.objects.update_or_create(
            form_slug=slug,
            defaults={'form_label': label, 'partner': partner_obj, 'is_active': True},
        )

    # 2) Pin the baseline mapping to CIPRB so it's correctly scoped.
    if ciprb is not None:
        KoboFormMapping.objects.filter(form_slug='spondon_baseline_v1').update(
            partner=ciprb,
            form_label='CIPRB Baseline & Endline Survey',
        )

    # 3) Wire CIPRB IndicatorTarget rows to their source forms.
    slug_to_form = {f.form_slug: f for f in KoboFormMapping.objects.all()}
    for activity_code, slug in CIPRB_SOURCE_FORM_MAP.items():
        target = (
            IndicatorTarget.objects
            .filter(partner__code='CIPRB', activity_code=activity_code)
            .first()
        )
        if target is None:
            continue
        target.source_form = slug_to_form.get(slug)
        target.save(update_fields=['source_form', 'updated_at'])


def _reverse(apps, schema_editor):
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')

    # Unset source_form on CIPRB rows
    IndicatorTarget.objects.filter(partner__code='CIPRB').update(source_form=None)

    # Delete the two seeded fistula form mappings.
    KoboFormMapping.objects.filter(
        form_slug__in=[slug for slug, _, _ in NEW_FORMS],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0006_seed_kobo_form_mappings'),
        ('partners',   '0001_initial'),
        ('fistula',    '0003_corner_and_campaign_visit'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
