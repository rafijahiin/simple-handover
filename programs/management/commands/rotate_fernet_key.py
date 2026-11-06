"""Re-encrypt every EncryptedCharField column onto the current FERNET_KEY.

Used when rotating the PII encryption key (e.g. after the Railway env-var
breach, Oct 2026). The field itself decrypts with FERNET_KEY *and* any
FERNET_KEY_FALLBACKS, so the app keeps working throughout — this command just
migrates the stored ciphertext onto the new primary key so the old one can be
retired.

Rotation procedure:
    1. FERNET_KEY_FALLBACKS=<old key>, FERNET_KEY=<new key>  -> deploy
       (nothing breaks; old rows still decrypt via the fallback)
    2. manage.py rotate_fernet_key            # dry run, reports what it'd do
    3. manage.py rotate_fernet_key --commit   # re-encrypt
    4. clear FERNET_KEY_FALLBACKS             -> deploy

Safety properties:
    * Dry run by default; writes only with --commit.
    * Idempotent — rows already on the primary key are detected and skipped,
      so it is safe to re-run.
    * A row that decrypts with NO available key is counted and LEFT UNTOUCHED.
      It is never blanked or overwritten.
    * Reads and writes raw ciphertext via SQL, bypassing the field's automatic
      encrypt/decrypt, so nothing is double-encrypted.
"""
from cryptography.fernet import Fernet, InvalidToken
from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


def _is_encrypted_field(f) -> bool:
    """True for any of the project's EncryptedCharField classes.

    There are THREE separate definitions of EncryptedCharField (fistula/
    encryption.py, fistula/models.py, programs/models/gbv.py — the last one
    also backs Client PII). An isinstance() check against only the canonical
    one silently skipped GBV, Client and fistula columns, which during a key
    rotation would have left that PII stranded on the retired key. Matching on
    the class NAME catches all three, and any future copy.
    """
    return type(f).__name__ == 'EncryptedCharField'


class Command(BaseCommand):
    help = 'Re-encrypt all EncryptedCharField data onto the current FERNET_KEY.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--commit', action='store_true',
            help='Actually write. Without it this is a dry run.')

    def handle(self, *args, **opts):
        commit = opts['commit']

        primary_key = settings.FERNET_KEY
        if not primary_key:
            raise CommandError('FERNET_KEY is not set — nothing to rotate onto.')
        primary = Fernet(primary_key.encode() if isinstance(primary_key, str)
                         else primary_key)
        fallbacks = [
            Fernet(k.encode() if isinstance(k, str) else k)
            for k in (getattr(settings, 'FERNET_KEY_FALLBACKS', []) or [])
            if k and k != primary_key
        ]

        if not fallbacks:
            self.stdout.write(self.style.WARNING(
                'No FERNET_KEY_FALLBACKS set. Rows already on the primary key '
                'will be skipped; anything encrypted with another key cannot '
                'be read and will be reported as unreadable.'))

        # Every EncryptedCharField in the project.
        targets = []
        for model in apps.get_models():
            for f in model._meta.get_fields():
                if _is_encrypted_field(f):
                    targets.append((model, f))
        if not targets:
            self.stdout.write('No EncryptedCharField columns found.')
            return

        self.stdout.write(
            f'{len(targets)} encrypted column(s) across '
            f'{len({m for m, _ in targets})} model(s). '
            f'{"COMMITTING" if commit else "DRY RUN"}.\n')

        q = connection.ops.quote_name
        totals = {'rows': 0, 'rotated': 0, 'current': 0, 'unreadable': 0}

        for model, field in targets:
            table = model._meta.db_table
            col = field.column
            pk = model._meta.pk.column
            rotated = current = unreadable = 0

            with connection.cursor() as cur:
                cur.execute(
                    f'SELECT {q(pk)}, {q(col)} FROM {q(table)} '
                    f'WHERE {q(col)} IS NOT NULL AND {q(col)} <> %s', [''])
                rows = cur.fetchall()

            pending = []
            for row_pk, token in rows:
                if not token:
                    continue
                raw = token.encode() if isinstance(token, str) else token
                # Already on the primary key? Then there is nothing to do.
                try:
                    primary.decrypt(raw)
                    current += 1
                    continue
                except InvalidToken:
                    pass
                # Try each retired key.
                plaintext = None
                for fk in fallbacks:
                    try:
                        plaintext = fk.decrypt(raw)
                        break
                    except InvalidToken:
                        continue
                if plaintext is None:
                    # Unknown key, or legacy cleartext. Leave it alone.
                    unreadable += 1
                    continue
                pending.append((primary.encrypt(plaintext).decode(), row_pk))
                rotated += 1

            if commit and pending:
                with transaction.atomic():
                    with connection.cursor() as cur:
                        cur.executemany(
                            f'UPDATE {q(table)} SET {q(col)} = %s '
                            f'WHERE {q(pk)} = %s', pending)

            totals['rows'] += len(rows)
            totals['rotated'] += rotated
            totals['current'] += current
            totals['unreadable'] += unreadable

            if rows:
                note = f'{table}.{col}: {len(rows)} row(s) — ' \
                       f'{rotated} to rotate, {current} already current'
                if unreadable:
                    note += f', {unreadable} UNREADABLE'
                style = self.style.WARNING if unreadable else self.style.SUCCESS
                self.stdout.write(style(note))

        self.stdout.write('')
        self.stdout.write(
            f"TOTAL: {totals['rows']} encrypted value(s) — "
            f"{totals['rotated']} rotated, {totals['current']} already current, "
            f"{totals['unreadable']} unreadable")
        if totals['unreadable']:
            self.stdout.write(self.style.ERROR(
                'Unreadable rows were NOT modified. They need the key they '
                'were encrypted with added to FERNET_KEY_FALLBACKS.'))
        if not commit:
            self.stdout.write(self.style.WARNING(
                '\nDry run — nothing written. Re-run with --commit to apply.'))
        elif totals['rotated']:
            self.stdout.write(self.style.SUCCESS(
                '\nDone. Once this reports 0 to rotate, clear '
                'FERNET_KEY_FALLBACKS and redeploy.'))
