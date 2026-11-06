"""
One-shot command to create the June 2026 programme user accounts.

Usage (Railway console or local):
    python manage.py create_programme_users

Each user is created with a temporary password printed to stdout.
Users should change their password on first login via /admin/ or the
profile page. Existing accounts are silently skipped.

Run once. Safe to re-run — idempotent.
"""
import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

USERS = [
    # ── PHD ────────────────────────────────────────────────────────────
    {'email': 'tarique.ksm@gmail.com',   'full_name': 'Tarique',                       'organisation': 'PHD',    'role': 'focal'},
    {'email': 'a-salam@phd-bd.com',      'full_name': 'Abdul Salam',                   'organisation': 'PHD',    'role': 'focal'},
    # ── Bandhu ─────────────────────────────────────────────────────────
    {'email': 'tanvir@bandhu-bd.org',    'full_name': 'AKM Mahabubul Islam Tanvir',    'organisation': 'Bandhu', 'role': 'focal'},
    {'email': 'shahid@bandhu-bd.org',    'full_name': 'Md. Shahidul Alam',             'organisation': 'Bandhu', 'role': 'focal'},
    {'email': 'shale@bandhu-bd.org',     'full_name': 'Shale Ahmed',                   'organisation': 'Bandhu', 'role': 'focal'},
    # ── UNFPA ──────────────────────────────────────────────────────────
    {'email': 'ryasmin@unfpa.org',       'full_name': 'Rokhsana Yasmin',               'organisation': 'UNFPA',  'role': 'supervisor'},
    {'email': 'ahasan@unfpa.org',        'full_name': 'Abu Sayed Hasan',               'organisation': 'UNFPA',  'role': 'supervisor'},
    {'email': 'raghuyamshi@unfpa.org',   'full_name': 'Vibhavendra Raghuyamshi',       'organisation': 'UNFPA',  'role': 'supervisor'},
    # ── CIPRB ──────────────────────────────────────────────────────────
    {'email': 'halim.ogsb@gmail.com',    'full_name': 'Abdul Halim',                   'organisation': 'CIPRB',  'role': 'focal'},
]

ADMIN_ROLES = {'developer', 'supervisor', 'org_lead'}

def _gen_password(length=12):
    alphabet = string.ascii_letters + string.digits + '!@#$'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = 'Create June 2026 programme user accounts with auto-generated temp passwords.'

    def handle(self, *args, **options):
        User = get_user_model()
        created, skipped = [], []

        for u in USERS:
            if User.objects.filter(email__iexact=u['email']).exists():
                skipped.append(u['email'])
                continue

            pw = _gen_password()
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
            created.append((u['email'], u['full_name'], u['organisation'], u['role'], pw))

        # Print results
        self.stdout.write('\n' + '─' * 80)
        self.stdout.write(self.style.SUCCESS(f'  Created {len(created)} accounts'))
        if skipped:
            self.stdout.write(f'  Skipped (already exist): {", ".join(skipped)}')
        self.stdout.write('─' * 80)

        if created:
            self.stdout.write(
                f'\n  {"EMAIL":<35} {"ORG":<8} {"ROLE":<12} TEMP PASSWORD'
            )
            self.stdout.write('  ' + '─' * 76)
            for email, _, org, role, pw in created:
                self.stdout.write(f'  {email:<35} {org:<8} {role:<12} {pw}')
            self.stdout.write(
                '\n  ⚠  Share these passwords securely. Users must change on first login.\n'
            )
