import os
from .base import *  # noqa: F403  -- split-settings pattern

DEBUG = False

# --- Fail-closed secret checks (audit FIX: SECRET_KEY + FERNET_KEY) ---------
# Mirror the loud DATABASE_URL guard in base.py. Booting production with the
# dev SECRET_KEY default enables session/CSRF forgery; booting without
# FERNET_KEY would silently write GBV/fistula survivor PII to the DB in
# cleartext (the model _encrypt() passes through when the key is empty).
# Refuse to start in either case.
_INSECURE_SECRET_KEY_DEFAULT = 'unsafe-default-for-dev-only-change-in-production'
if not SECRET_KEY or SECRET_KEY == _INSECURE_SECRET_KEY_DEFAULT:  # noqa: F405
    raise RuntimeError(
        'SECRET_KEY is unset or still the insecure dev default in production. '
        'Set a strong unique SECRET_KEY on the Railway service Variables.'
    )

if not FERNET_KEY:  # noqa: F405
    raise RuntimeError(
        'FERNET_KEY is not set in production. Survivor/patient PII (GBV, '
        'fistula) would be written to the database in cleartext. Generate '
        'one with: python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())" and set it on Railway. '
        'NOTE: once data exists, rotating this key makes existing ciphertext '
        'undecryptable — keep it stable.'
    )

_hosts = os.environ.get('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(',') if h.strip()]
# Railway's internal healthcheck probes the container with the Host header
# 'healthcheck.railway.app'. Without this, Django raises DisallowedHost and
# returns 400 to every healthcheck → the deploy is marked unhealthy and the
# new release never goes live. Always allow it.
if 'healthcheck.railway.app' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('healthcheck.railway.app')

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Railway terminates TLS at the load balancer — do not redirect here
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'

CSRF_TRUSTED_ORIGINS = [f'https://{h}' for h in ALLOWED_HOSTS if h]

# Basic LOGGING configuration — Railway captures stdout
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django.security': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'submissions':     {'handlers': ['console'], 'level': 'INFO',    'propagate': False},
        'programs':        {'handlers': ['console'], 'level': 'INFO',    'propagate': False},
        'reports':         {'handlers': ['console'], 'level': 'INFO',    'propagate': False},
    },
}
