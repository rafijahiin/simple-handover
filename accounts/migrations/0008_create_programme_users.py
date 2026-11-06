"""
Data migration — create all June 2026 programme user accounts.

Why this exists alongside 0007:
  0007 ran at deploy time BEFORE the Railway env vars were set, so it
  found no passwords and skipped every user. This migration runs on the
  next deploy (after vars are set) and fills the gap.

Same safety contract as 0007:
  - Idempotent: existing rows are never touched.
  - Password gated: each account requires its own env var; if absent the
    account is silently skipped.

Env vars to set in Railway before deploying:
    USER_TARIQUE_PASSWORD
    USER_HALIM_PASSWORD
    USER_RYASMIN_PASSWORD
    USER_AHASAN_PASSWORD
    USER_RAGHUYAMSHI_PASSWORD
    USER_TANVIR_PASSWORD
    USER_SHAHID_PASSWORD
    USER_SHALE_PASSWORD
    USER_SALAM_PASSWORD
"""
import os

from django.contrib.auth.hashers import make_password
from django.db import migrations

ADMIN_ROLES = {'developer', 'supervisor', 'org_lead'}

USERS = [
    # ── PHD (focal — full PHD dashboard, read-only) ────────────────────
    {'email': 'tarique.ksm@gmail.com',  'full_name': 'Tarique',                    'organisation': 'PHD',    'role': 'focal',      'env': 'USER_TARIQUE_PASSWORD'},
    {'email': 'a-salam@phd-bd.com',     'full_name': 'Abdul Salam',                'organisation': 'PHD',    'role': 'focal',      'env': 'USER_SALAM_PASSWORD'},
    # ── Bandhu (focal — full Bandhu dashboard, read-only) ──────────────
    {'email': 'tanvir@bandhu-bd.org',   'full_name': 'AKM Mahabubul Islam Tanvir', 'organisation': 'Bandhu', 'role': 'focal',      'env': 'USER_TANVIR_PASSWORD'},
    {'email': 'shahid@bandhu-bd.org',   'full_name': 'Md. Shahidul Alam',          'organisation': 'Bandhu', 'role': 'focal',      'env': 'USER_SHAHID_PASSWORD'},
    {'email': 'shale@bandhu-bd.org',    'full_name': 'Shale Ahmed',                'organisation': 'Bandhu', 'role': 'focal',      'env': 'USER_SHALE_PASSWORD'},
    # ── UNFPA (supervisor — full system access) ────────────────────────
    {'email': 'ryasmin@unfpa.org',      'full_name': 'Rokhsana Yasmin',            'organisation': 'UNFPA',  'role': 'supervisor', 'env': 'USER_RYASMIN_PASSWORD'},
    {'email': 'ahasan@unfpa.org',       'full_name': 'Abu Sayed Hasan',            'organisation': 'UNFPA',  'role': 'supervisor', 'env': 'USER_AHASAN_PASSWORD'},
    {'email': 'raghuyamshi@unfpa.org',  'full_name': 'Vibhavendra Raghuyamshi',    'organisation': 'UNFPA',  'role': 'supervisor', 'env': 'USER_RAGHUYAMSHI_PASSWORD'},
    # ── CIPRB (focal) ──────────────────────────────────────────────────
    {'email': 'halim.ogsb@gmail.com',   'full_name': 'Abdul Halim',                'organisation': 'CIPRB',  'role': 'focal',      'env': 'USER_HALIM_PASSWORD'},
]


def _apply(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for u in USERS:
        if User.objects.filter(email__iexact=u['email']).exists():
            continue
        pw = os.environ.get(u['env'], '').strip()
        if not pw:
            continue
        is_staff = u['role'] in ADMIN_ROLES
        User.objects.create(
            email=u['email'],
            full_name=u['full_name'],
            organisation=u['organisation'],
            role=u['role'],
            password=make_password(pw),
            is_active=True,
            is_staff=is_staff,
            is_superuser=is_staff,
        )


def _reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0007_seed_programme_users'),
    ]
    operations = [migrations.RunPython(_apply, _reverse)]
