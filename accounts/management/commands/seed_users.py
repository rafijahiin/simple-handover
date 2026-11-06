"""
Seed default user accounts from environment-supplied passwords.

Gating
------
This command no-ops unless the SEED_DB environment variable is truthy
(any value other than empty/0/false). This prevents accidental reseeding
of the production database on every container restart. To run a seed:

    1. Set SEED_DB=1 in the Railway web service Variables.
    2. Set the per-account password env vars (see USERS below).
    3. Trigger a redeploy. The seed runs once.
    4. UNSET SEED_DB=1 (or set to 0). Subsequent deploys no-op.

Idempotency
-----------
For each user, the row is created only if the email doesn't already
exist. Existing users are NEVER modified — passwords are not reset,
roles are not changed, organisations are not corrected.

Passwords
---------
Every account password is read from an environment variable. If the
env var is missing or blank, that single account is SKIPPED with a
warning — we never fall back to a hardcoded default. If you want a
specific account to be created, you must set its env var.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


# Per-account password env var mapping.
# Each tuple: (email, full_name, organisation, role, password_env_var_name)
# If the env var below doesn't match your Railway variables, rename it
# either here or in Railway.
USERS = [
    # Order matches the authoritative Admin Panel sequence.
    # ── Developer (system maintenance — Rafi) ─────────────────────────────
    {
        'email':        'rafijahiin@gmail.com',
        'full_name':    'Rafi Jahin',
        'organisation': 'CIPRB',
        'role':         'developer',
        'password_env': 'DEV_PASSWORD',
    },
    # ── CIPRB Org Lead (full CIPRB access incl. Fistula + MPDSR + Baseline,
    #    read-only on PHD/Bandhu, can set CIPRB targets) ──────────────────
    {
        'email':        'sayeed@ciprb.org',
        'full_name':    'Dr. Abu Sayeed Md. Abdullah',
        'organisation': 'CIPRB',
        'role':         'org_lead',
        'password_env': 'CIPRB_SAYEED_PASSWORD',
    },
    # ── CIPRB Manager — the CIPRB APPROVER (approves everything CIPRB incl.
    #    MPDSR + Fistula PII + Baseline). manager role → can_approve_submissions;
    #    org-bound can_access_mpdsr / can_access_fistula_cases grant the PII
    #    viewsets. Rafi's 2026-06-26 directive. Confirm her full display name. ──
    {
        'email':        'tanjina.ciprb@gmail.com',
        'full_name':    'Tanjina',
        'organisation': 'CIPRB',
        'role':         'manager',
        'password_env': 'TANJINA_PASSWORD',
    },
    # ── UNFPA Supervisors (full system, target config) ────────────────────
    {
        'email':        'animesh@unfpa.org',
        'full_name':    'Dr. Animesh Biswas',
        'organisation': 'UNFPA',
        'role':         'supervisor',
        'password_env': 'UNFPA_ANIMESH_PASSWORD',
    },
    {
        'email':        'rokhsana@unfpa.org',
        'full_name':    'Rokhsana',
        'organisation': 'UNFPA',
        'role':         'supervisor',
        'password_env': 'UNFPA_ROKHSANA_PASSWORD',
    },
    # ── Wellness Center Managers (own-org approval + Outreach entry) ──────
    {
        'email':        'manager@bandhu.org',
        'full_name':    'Bandhu Manager',
        'organisation': 'Bandhu',   # canonical spelling with 'a'
        'role':         'manager',
        'password_env': 'BANDHU_MANAGER_PASSWORD',
    },
    {
        'email':        'manager@phd.org',
        'full_name':    'PHD Manager',
        'organisation': 'PHD',
        'role':         'manager',
        'password_env': 'PHD_MANAGER_PASSWORD',
    },
    # ── Focal Persons (view-only on own org page, no entry, no approval) ──
    # Only seeded when their password env var is set in Railway.
    {
        'email':        'focal@phd.org',
        'full_name':    'PHD Focal Person',
        'organisation': 'PHD',
        'role':         'focal',
        'password_env': 'PHD_FOCAL_PASSWORD',
    },
    {
        'email':        'focal@bandhu.org',
        'full_name':    'Bandhu Focal Person',
        'organisation': 'Bandhu',
        'role':         'focal',
        'password_env': 'BANDHU_FOCAL_PASSWORD',
    },
    # ── CIPRB Baseline (Baseline Assessment tab only, self-approving) ────
    {
        'email':        'baseline@ciprb.org',
        'full_name':    'CIPRB Baseline Entry',
        'organisation': 'CIPRB',
        'role':         'ciprb_baseline',
        'password_env': 'CIPRB_BASELINE_PASSWORD',
    },
    # ── Workshop / partner participant accounts ──────────────────────────
    # Created only when SEED_DB=1 and the password env var is set in Railway.
    {
        'email':        'Habib.ahsan1992@gmail.com',
        'full_name':    'Habib Ahsan',
        'organisation': 'PHD',
        'role':         'manager',
        'password_env': 'HABIB_PASSWORD',
    },
    # ── Bandhu staff. Role is 'manager' (stage-1 approver): with UNFPA as the
    #    guaranteed 2nd layer, the focal/manager split is moot for Bandhu, so all
    #    Bandhu staff are managers and can approve at stage 1; UNFPA finalises. ─
    {
        'email':        'iqbal@bandhu-bd.org',
        'full_name':    'Mohammed Iqbal Hossain',
        'organisation': 'Bandhu',
        'role':         'manager',
        'password_env': 'BANDHU_IQBAL_PASSWORD',
    },
]


def _seed_db_enabled() -> bool:
    """Return True iff the SEED_DB env var is set to a truthy value."""
    raw = os.environ.get('SEED_DB', '').strip().lower()
    return raw not in ('', '0', 'false', 'no', 'off')


class Command(BaseCommand):
    help = 'Create default users from env-supplied passwords. Gated by SEED_DB.'

    def handle(self, *args, **options):
        if not _seed_db_enabled():
            self.stdout.write(
                'SEED_DB is not set — seed_users is a no-op. '
                'Set SEED_DB=1 in the environment to enable seeding.'
            )
            return

        User = get_user_model()
        created = 0
        skipped_exists = 0
        skipped_no_password = 0

        for u in USERS:
            email = u['email']
            password = os.environ.get(u['password_env'], '').strip()

            if User.objects.filter(email=email).exists():
                self.stdout.write(f'  exists      {email}')
                skipped_exists += 1
                continue

            if not password:
                self.stderr.write(
                    f'  SKIP        {email}  (env var {u["password_env"]} '
                    f'is not set — refusing to create account without password)'
                )
                skipped_no_password += 1
                continue

            # Only roles with system-wide responsibility get is_staff=True
            # (for Django /admin/ emergency maintenance):
            #   developer  — Rafi only
            #   supervisor — UNFPA (Animesh, Rokhsana)
            #   org_lead   — CIPRB (Sayeed)
            # All other roles (manager, field_staff, ciprb_baseline, focal)
            # get is_staff=False so they cannot reach /admin/, even though
            # their email/password remain valid via the React app login.
            ADMIN_ROLES = ('developer', 'supervisor', 'org_lead')
            create = (
                User.objects.create_superuser
                if u['role'] in ADMIN_ROLES
                else User.objects.create_user
            )
            create(
                email=email,
                password=password,
                full_name=u['full_name'],
                organisation=u['organisation'],
                role=u['role'],
            )
            self.stdout.write(self.style.SUCCESS(f'  created     {email}'))
            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\nseed_users done. created={created} '
                f'exists={skipped_exists} skipped_no_password={skipped_no_password}'
            )
        )
