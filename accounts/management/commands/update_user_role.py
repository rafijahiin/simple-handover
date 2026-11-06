"""
One-shot fixer for users whose role / organisation got set incorrectly.

`seed_users` deliberately never modifies existing rows ("Existing users
are NEVER modified") to avoid accidental role escalation on every redeploy.
This command is the explicit, audit-loggable alternative when a specific
user genuinely needs their role or organisation updated.

Usage examples:

    # Promote Dr Animesh to UNFPA supervisor (the canonical config from
    # seed_users.USERS):
    python manage.py update_user_role animesh@unfpa.org \\
        --role supervisor --org UNFPA

    # Dry-run (show what would change, don't write):
    python manage.py update_user_role animesh@unfpa.org \\
        --role supervisor --org UNFPA --dry-run

    # Re-target an existing manager (rare):
    python manage.py update_user_role manager@phd.org --role manager --org PHD

The command refuses to run without both --role and --org so there's no
ambiguous half-update. Emits a clear before/after diff to stdout.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Organisation, Role


class Command(BaseCommand):
    help = (
        'Update a single user\'s role and organisation. Refuses to run '
        'without explicit --role and --org. Use --dry-run to preview.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'email',
            help='Email of the user to update (must already exist).',
        )
        parser.add_argument(
            '--role',
            required=True,
            choices=[r.value for r in Role],
            help='New role (developer, supervisor, org_lead, manager, '
                 'field_staff, ciprb_baseline, focal).',
        )
        parser.add_argument(
            '--org',
            required=True,
            choices=[o.value for o in Organisation],
            help='New organisation (CIPRB, UNFPA, PHD, Bandhu).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print the change but do not save.',
        )

    def handle(self, *args, **opts):
        User = get_user_model()
        email = opts['email'].strip().lower()
        new_role = opts['role']
        new_org = opts['org']
        dry = opts['dry_run']

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise CommandError(
                f'No user found with email {email!r}. '
                f'(Use seed_users to create new accounts, not this command.)'
            )

        # Compute is_staff per the same policy as seed_users:
        #   developer + supervisor + org_lead → is_staff=True
        #   everything else → is_staff=False
        ADMIN_ROLES = ('developer', 'supervisor', 'org_lead')
        new_is_staff = new_role in ADMIN_ROLES

        # Print before/after.
        self.stdout.write(self.style.MIGRATE_HEADING(f'\nUser: {email}'))
        for label, before, after in (
            ('role',        user.role,         new_role),
            ('organisation',user.organisation, new_org),
            ('is_staff',    user.is_staff,     new_is_staff),
        ):
            changed = before != after
            tag = self.style.WARNING('CHANGE') if changed else self.style.HTTP_INFO('=    ')
            self.stdout.write(f'  {tag}  {label:13s}  {before!r:24s} -> {after!r}')

        if dry:
            self.stdout.write(self.style.NOTICE('\n--dry-run set; no rows written.'))
            return

        user.role = new_role
        user.organisation = new_org
        user.is_staff = new_is_staff
        user.save(update_fields=['role', 'organisation', 'is_staff'])

        self.stdout.write(self.style.SUCCESS(
            f'\nUpdated {email}: role={new_role}, org={new_org}, '
            f'is_staff={new_is_staff}.'
        ))
