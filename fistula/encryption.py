import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models

logger = logging.getLogger('programs')


# ── Key handling: one ENCRYPTION key, many DECRYPTION keys ───────────────────
# Rotating FERNET_KEY used to be impossible without data loss: every existing
# ciphertext was encrypted with the old key, so a new key made all PII read
# back blank. MultiFernet fixes that — it ENCRYPTS with the first key and
# DECRYPTS by trying every key in order.
#
# So a rotation is now:
#   1. set FERNET_KEY_FALLBACKS = <old key>, FERNET_KEY = <new key>, deploy
#      (nothing breaks: new writes use the new key, old rows still decrypt)
#   2. run `manage.py rotate_fernet_key --commit` to re-encrypt everything
#   3. clear FERNET_KEY_FALLBACKS
#
# Keys are cached per key-tuple: building Fernet objects does key derivation,
# and these run on every PII field read.
_CACHE: dict = {}


def _key_tuple() -> tuple:
    primary = settings.FERNET_KEY
    if not primary:
        return ()
    fallbacks = getattr(settings, 'FERNET_KEY_FALLBACKS', []) or []
    return tuple([primary] + [k for k in fallbacks if k and k != primary])


def _multi(keys: tuple) -> MultiFernet:
    """MultiFernet for these keys — encrypts with keys[0], decrypts with any."""
    cached = _CACHE.get(keys)
    if cached is None:
        cached = MultiFernet([
            Fernet(k.encode() if isinstance(k, str) else k) for k in keys
        ])
        _CACHE[keys] = cached
    return cached


def _fernet() -> MultiFernet:
    keys = _key_tuple()
    if not keys:
        raise ValueError(
            'FERNET_KEY is not configured. '
            'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return _multi(keys)


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ''
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ''
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # Wrong/rotated key or corrupted ciphertext — never echo the raw
        # ciphertext back; blank + log (audit FIX H1). A missing FERNET_KEY
        # raises ValueError from _fernet() and is intentionally NOT caught
        # here so the misconfiguration surfaces loudly.
        logger.error('decrypt() failed (InvalidToken) — check FERNET_KEY')
        return ''


# ── Transparent encrypted model field for PII at rest ────────────────────────
# Shared by the CIPRB clinical models (fistula, MPDSR death notification, near
# miss) so they get the SAME encryption GBV already has, without a cross-app
# import (this module has no model deps). Dev/test WITHOUT a FERNET_KEY passes
# through in cleartext; production refuses to boot without the key
# (spondon/settings/production.py), so real data is ALWAYS encrypted at rest.

def _enc(value: str) -> str:
    if not value:
        return ''
    keys = _key_tuple()
    if not keys:                      # dev/test only — prod guards FERNET_KEY
        return value
    # MultiFernet encrypts with the PRIMARY key (keys[0]).
    return _multi(keys).encrypt(value.encode()).decode()


def _dec(value: str) -> str:
    if not value:
        return ''
    keys = _key_tuple()
    if not keys:
        return value
    try:
        # Tries the primary key first, then any rotation fallbacks.
        return _multi(keys).decrypt(value.encode()).decode()
    except InvalidToken:
        # Plaintext legacy rows / wrong key / corruption — never echo raw bytes.
        logger.error('EncryptedCharField decrypt failed (InvalidToken) — check '
                     'FERNET_KEY / FERNET_KEY_FALLBACKS')
        return ''


class EncryptedCharField(models.TextField):
    """Fernet-encrypt on save, decrypt on read. Stored as TextField because the
    ciphertext is longer than the plaintext. NEVER use on a field that is a DB
    filter / lookup / unique / order key — the column holds ciphertext."""

    def from_db_value(self, value, expression, connection):
        return _dec(value) if value else value

    def pre_save(self, model_instance, add):
        value = super().pre_save(model_instance, add)
        enc = _enc(value)
        setattr(model_instance, self.attname, enc)
        return enc
