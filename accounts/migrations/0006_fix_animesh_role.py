"""
One-shot data migration — promote Dr Animesh Biswas to supervisor + UNFPA.

The seed_users command deliberately never modifies existing rows, so if
Dr Animesh was created before the seed ran (with wrong role/org), the
seed couldn't fix him. This migration corrects the record idempotently:
re-running it has no effect.

Match strategy: lookup by exact email `animesh@unfpa.org`. If the row
doesn't exist (e.g. fresh DB), the migration silently no-ops. If the
row exists with the canonical config already, nothing changes.

Once the canonical seed has been applied + verified on every environment
this migration can be safely deleted; keeping it costs nothing.
"""
from django.db import migrations


CANONICAL = {
    'animesh@unfpa.org': {
        'role':         'supervisor',
        'organisation': 'UNFPA',
        'is_staff':     True,  # supervisor is an ADMIN_ROLE per seed_users
    },
}


def _apply(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for email, expected in CANONICAL.items():
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            continue
        changed = False
        for field, value in expected.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed = True
        if changed:
            user.save(update_fields=list(expected.keys()))


def _reverse(apps, schema_editor):
    # No-op — we don't want to "unfix" a corrected record on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0005_alter_user_role'),
    ]
    operations = [migrations.RunPython(_apply, _reverse)]
