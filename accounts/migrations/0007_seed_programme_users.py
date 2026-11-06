"""
One-shot data migration — create programme user accounts for all named
contacts provided by CIPRB / UNFPA (June 2026 onboarding batch).

Safety rules (same as seed_users):
  - Idempotent: if the email already exists the row is NEVER touched.
  - Password gating: each account requires its own env var (see NEW_USERS).
    If the env var is absent the account is silently skipped.
  - sayeed@ciprb.org is already seeded (org_lead) — excluded here.

Role assignments
----------------
  @bandhu-bd.org  → Bandhu  / manager
  @phd-bd.com     → PHD     / manager
  @unfpa.org      → UNFPA   / supervisor  (is_staff=True, Django admin access)
  tarique.ksm@gmail.com  → CIPRB / manager   (programme-side coordinator)
  halim.ogsb@gmail.com   → CIPRB / focal     (OGSB clinical collaborator)

Env var naming convention: USER_<IDENTIFIER>_PASSWORD  (all uppercase)
The placeholder values below are the ones to set in Railway Variables.
"""
import os

from django.contrib.auth.hashers import make_password
from django.db import migrations

ADMIN_ROLES = {'developer', 'supervisor', 'org_lead'}

NEW_USERS = [
    # ── PHD ────────────────────────────────────────────────────────────
    {
        'email':        'tarique.ksm@gmail.com',
        'full_name':    'Tarique',
        'organisation': 'PHD',
        'role':         'focal',
        'password_env': 'USER_TARIQUE_PASSWORD',
    },
    {
        'email':        'halim.ogsb@gmail.com',
        'full_name':    'Abdul Halim',
        'organisation': 'CIPRB',
        'role':         'focal',
        'password_env': 'USER_HALIM_PASSWORD',
    },
    # ── UNFPA ──────────────────────────────────────────────────────────
    {
        'email':        'ryasmin@unfpa.org',
        'full_name':    'Rokhsana Yasmin',
        'organisation': 'UNFPA',
        'role':         'supervisor',
        'password_env': 'USER_RYASMIN_PASSWORD',
    },
    {
        'email':        'ahasan@unfpa.org',
        'full_name':    'Abu Sayed Hasan',
        'organisation': 'UNFPA',
        'role':         'supervisor',
        'password_env': 'USER_AHASAN_PASSWORD',
    },
    {
        'email':        'raghuyamshi@unfpa.org',
        'full_name':    'Vibhavendra Raghuyamshi',
        'organisation': 'UNFPA',
        'role':         'supervisor',
        'password_env': 'USER_RAGHUYAMSHI_PASSWORD',
    },
    # ── Bandhu ─────────────────────────────────────────────────────────
    {
        'email':        'tanvir@bandhu-bd.org',
        'full_name':    'AKM Mahabubul Islam Tanvir',
        'organisation': 'Bandhu',
        'role':         'focal',
        'password_env': 'USER_TANVIR_PASSWORD',
    },
    {
        'email':        'shahid@bandhu-bd.org',
        'full_name':    'Md. Shahidul Alam',
        'organisation': 'Bandhu',
        'role':         'focal',
        'password_env': 'USER_SHAHID_PASSWORD',
    },
    {
        'email':        'shale@bandhu-bd.org',
        'full_name':    'Shale Ahmed',
        'organisation': 'Bandhu',
        'role':         'focal',
        'password_env': 'USER_SHALE_PASSWORD',
    },
    # ── PHD ────────────────────────────────────────────────────────────
    {
        'email':        'a-salam@phd-bd.com',
        'full_name':    'Abdul Salam',
        'organisation': 'PHD',
        'role':         'focal',
        'password_env': 'USER_SALAM_PASSWORD',
    },
]


def _apply(apps, schema_editor):
    User = apps.get_model('accounts', 'User')

    for u in NEW_USERS:
        # Idempotency — skip if already present.
        if User.objects.filter(email__iexact=u['email']).exists():
            continue

        password_plain = os.environ.get(u['password_env'], '').strip()
        if not password_plain:
            # Env var not set — skip silently (same policy as seed_users).
            continue

        is_staff     = u['role'] in ADMIN_ROLES
        is_superuser = u['role'] in ADMIN_ROLES

        User.objects.create(
            email=u['email'],
            full_name=u['full_name'],
            organisation=u['organisation'],
            role=u['role'],
            password=make_password(password_plain),
            is_active=True,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )


def _reverse(apps, schema_editor):
    # Never delete real user accounts on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0006_fix_animesh_role'),
    ]
    operations = [migrations.RunPython(_apply, _reverse)]
