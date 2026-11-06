"""
Data migration — seed KoboFormMapping rows and wire IndicatorTarget.source_form.

Two passes:

  1. Create one KoboFormMapping row per Kobo form definition declared in
     `programs/management/commands/generate_kobo_forms.py`. Plus one new
     entry for `spondon_iec_material_v1` so the IECMaterial-backed
     indicators (PHD 3.1a-d, Bandhu 4.1, 4.3) have a form to point at
     even though the XLSForm itself will be hand-built at the workshop.

  2. For every IndicatorTarget whose activity_code has a known primary
     source form, set the FK. Indicators backed by a reference table
     (ServiceCenter, StockEntry) keep source_form=NULL — that's the
     correct state for "computed from registry / stock, not from a Kobo
     submission".

`kobo_asset_uid` is left blank on every row. Operators fill that in
after the forms are uploaded to KoboToolbox; the `KOBO_ASSET_UID_*`
env vars in settings/base.py mirror the same identity.

Idempotent: re-running this migration won't duplicate rows because
both passes use update_or_create on stable keys.
"""
from django.db import migrations


# ─── Pass 1 — form catalogue (slug → label, partner_code or None) ─────────────
# partner=None means cross-partner (used by both PHD and Bandhu, or by the
# Mother List which all three partners touch).

FORMS: list[tuple[str, str, str | None]] = [
    ('spondon_client_reg_v1',     'KF-01 — Client Registration (Mother List)', None),
    ('spondon_clinic_visit_v1',   'KF-02 — Clinic Visit (Patient Record Register)', None),
    ('spondon_hiv_sti_test_v1',   'KF-03 — HIV/STI Test Result', None),
    ('spondon_htc_counsel_v1',    'KF-04 — HTC Counselling', None),
    ('spondon_mh_screening_v1',   'KF-05/06 — Mental Health Screening', None),
    ('spondon_outreach_v1',       'KF-08 — Outreach Session', None),
    ('spondon_counselling_v1',    'KF-09 — Individual Counselling Session', None),
    ('spondon_group_edu_v1',      'KF-10 — Group Education Session', None),
    ('spondon_hygiene_kit_v1',    'KF-12 — Safety & Hygiene Kit Distribution', 'Bandhu'),
    ('spondon_adr_record_v1',     'KF-13 — Adverse Drug Reaction Record', None),
    ('spondon_autoclave_log_v1',  'KF-16 — Autoclave / Incinerator Log', 'PHD'),
    ('spondon_mobile_camp_v1',    'KF-18 — Mobile Health Camp', None),
    ('spondon_coord_meeting_v1',  'KF-19 — Coordination Meeting', None),
    ('spondon_training_event_v1', 'KF-20 — Training / Orientation / Workshop', None),
    ('spondon_referral_v1',       'Referral Form', None),
    ('spondon_gbv_case_v1',       'GBV Case Report (CONFIDENTIAL)', None),
    ('spondon_antenatal_card_v1', 'Antenatal Card', 'PHD'),
    # New for the IEC pipeline. XLSForm body is still pending (workshop)
    # but the mapping exists so the four obj-3 indicators link cleanly.
    ('spondon_iec_material_v1',   'IEC / SBCC Material Distribution', None),
]


# ─── Pass 2 — primary source form per (partner_code, activity_code) ───────────
# Activities driven by a reference table (ServiceCenter, StockEntry) are
# deliberately absent — their source_form stays NULL.

SOURCE_FORM_MAP: dict[tuple[str, str], str] = {
    # PHD
    ('PHD', '1.1'):  'spondon_clinic_visit_v1',
    ('PHD', '1.2'):  'spondon_gbv_case_v1',
    ('PHD', '1.3'):  'spondon_counselling_v1',
    ('PHD', '1.4'):  'spondon_outreach_v1',
    ('PHD', '1.5a'): 'spondon_clinic_visit_v1',
    # PHD 1.5b–e (screening kits) read StockEntry → NULL
    ('PHD', '1.6'):  'spondon_referral_v1',
    # PHD 1.7 reads ServiceCenter → NULL
    ('PHD', '1.8'):  'spondon_mobile_camp_v1',
    ('PHD', '2.1a'): 'spondon_training_event_v1',
    ('PHD', '2.1b'): 'spondon_training_event_v1',
    ('PHD', '2.2'):  'spondon_training_event_v1',
    ('PHD', '2.3'):  'spondon_training_event_v1',
    ('PHD', '2.4'):  'spondon_coord_meeting_v1',
    ('PHD', '3.1a'): 'spondon_iec_material_v1',
    ('PHD', '3.1b'): 'spondon_iec_material_v1',
    ('PHD', '3.1c'): 'spondon_iec_material_v1',
    ('PHD', '3.1d'): 'spondon_iec_material_v1',
    # PHD obj=0 OVERALL reads ServiceCenter → NULL

    # Bandhu
    ('Bandhu', '1.1'):  'spondon_clinic_visit_v1',
    ('Bandhu', '1.2'):  'spondon_gbv_case_v1',
    ('Bandhu', '1.3'):  'spondon_counselling_v1',
    ('Bandhu', '1.4a'): 'spondon_group_edu_v1',
    ('Bandhu', '1.4b'): 'spondon_outreach_v1',
    # Bandhu 1.5a (centres) → NULL
    ('Bandhu', '1.5b'): 'spondon_hiv_sti_test_v1',
    # Bandhu 1.6 (Dhaka clinic) → NULL
    ('Bandhu', '1.7'):  'spondon_referral_v1',
    # Bandhu 1.8 (DICs) → NULL
    ('Bandhu', '1.9'):  'spondon_mobile_camp_v1',
    ('Bandhu', '2.1'):  'spondon_training_event_v1',
    ('Bandhu', '2.2'):  'spondon_training_event_v1',
    ('Bandhu', '2.3'):  'spondon_coord_meeting_v1',
    ('Bandhu', '2.4'):  'spondon_coord_meeting_v1',
    ('Bandhu', '2.5'):  'spondon_training_event_v1',
    ('Bandhu', '2.6'):  'spondon_coord_meeting_v1',
    ('Bandhu', '4.1'):  'spondon_iec_material_v1',
    ('Bandhu', '4.3'):  'spondon_iec_material_v1',

    # CIPRB — Fistula Corner / Fistula Campaign / Baseline.
    # XLSForms TBD at the validation workshop; mappings left NULL
    # for now and surfaced as workshop-pending on the Target Config
    # screen. Once the supervisor confirms the register variables we'll
    # add three more rows to FORMS and update SOURCE_FORM_MAP.
}


def _forward(apps, schema_editor):
    Partner = apps.get_model('partners', 'Partner')
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')

    partners_by_code = {p.code: p for p in Partner.objects.all()}

    # Pass 1 — form catalogue
    forms_by_slug: dict = {}
    for slug, label, partner_code in FORMS:
        partner_obj = partners_by_code.get(partner_code) if partner_code else None
        mapping, _ = KoboFormMapping.objects.update_or_create(
            form_slug=slug,
            defaults={
                'form_label': label,
                'partner':    partner_obj,
                'is_active':  True,
            },
        )
        forms_by_slug[slug] = mapping

    # Pass 2 — wire IndicatorTarget.source_form
    updated = 0
    for target in IndicatorTarget.objects.select_related('partner').all():
        key = (target.partner.code, target.activity_code)
        slug = SOURCE_FORM_MAP.get(key)
        if slug is None:
            continue  # leave source_form NULL — reference-table or workshop-pending
        new_fk = forms_by_slug.get(slug)
        if new_fk is None:
            continue
        if target.source_form_id != new_fk.id:
            target.source_form = new_fk
            target.save(update_fields=['source_form', 'updated_at'])
            updated += 1


def _reverse(apps, schema_editor):
    """Best-effort reverse — clear source_form FKs and delete the rows we seeded.
    Other rows added manually post-migration are preserved."""
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')

    slugs = [slug for slug, _, _ in FORMS]

    # Clear source_form on any IndicatorTarget pointing at one of our seeded rows.
    IndicatorTarget.objects.filter(
        source_form__form_slug__in=slugs,
    ).update(source_form=None)

    # Delete only the seeded mappings.
    KoboFormMapping.objects.filter(form_slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0005_alter_indicatortarget_partner_and_more'),
        ('partners',   '0001_initial'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
