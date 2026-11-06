"""
Data migration: remap existing `super_admin` users to the new 7-role taxonomy.

Rules (per Step 1.5 of the role-refactor plan):

  super_admin + organisation=UNFPA  → supervisor
  super_admin + organisation=CIPRB  → org_lead
  super_admin + (other / unknown)   → leave unchanged (operator review)

The remap is reversible — going backwards sets every `supervisor` and
`org_lead` user back to `super_admin` (best effort; org_lead's CIPRB
context cannot be re-derived without inspecting `organisation`, which is
fine because the reverse path is intended only as an emergency rollback).
"""
from django.db import migrations


def _forward(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for u in User.objects.filter(role='super_admin'):
        if u.organisation == 'UNFPA':
            u.role = 'supervisor'
            u.save(update_fields=['role'])
        elif u.organisation == 'CIPRB':
            u.role = 'org_lead'
            u.save(update_fields=['role'])
        # Any other organisation: leave unchanged so an operator can decide
        # explicitly. The deprecated 'super_admin' value remains valid in
        # the choices for this commit, so no constraint violation.


def _reverse(apps, schema_editor):
    """Rollback. Sets every 'supervisor' or 'org_lead' user back to
    'super_admin'. Intended for emergency revert only — not idempotent
    against accounts created with the new roles AFTER this migration ran."""
    User = apps.get_model('accounts', 'User')
    User.objects.filter(role__in=('supervisor', 'org_lead')).update(role='super_admin')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_user_role'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
