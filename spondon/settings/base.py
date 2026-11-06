from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'unsafe-default-for-dev-only-change-in-production')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    # Local
    'accounts',
    'submissions',
    'dashboard',
    'fistula',
    'mpdsr',
    'tracker',
    'reports',
    'baseline',
    'training',
    'programs',
    'indicators',
    'partners',
    'pharmacy',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'accounts.middleware.OrganisationMiddleware',
]

ROOT_URLCONF = 'spondon.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'spondon.wsgi.application'

# --- Database resolution ---------------------------------------------------
# Production (DJANGO_SETTINGS_MODULE=spondon.settings.production) MUST receive
# a real DATABASE_URL pointing at the attached Postgres plugin. If the env var
# is missing, empty, or unparseable, we fail loudly at startup naming the
# missing variable — never silently fall back to SQLite, which would let the
# app boot against an ephemeral in-container DB and silently lose every write
# on the next redeploy.
#
# Local dev (DJANGO_SETTINGS_MODULE=spondon.settings.development) is allowed
# to fall back to a SQLite file so contributors can run the project without
# Postgres installed locally.
_db_url = os.environ.get('DATABASE_URL', '').strip()
_settings_module = os.environ.get('DJANGO_SETTINGS_MODULE', '')
_is_production = _settings_module.endswith('.production')

if _db_url:
    try:
        _parsed = dj_database_url.parse(_db_url, conn_max_age=600)
    except (ValueError, Exception) as exc:
        raise RuntimeError(
            f"DATABASE_URL is set but dj_database_url could not parse it "
            f"(value length={len(_db_url)}, parse error: {exc}). "
            f"On Railway this usually means the ${{{{...}}}} reference does "
            f"not resolve to a real Postgres service. Verify the Postgres "
            f"plugin is provisioned in this project and the reference is "
            f"${{{{ Postgres.DATABASE_URL }}}} (case-sensitive service name)."
        ) from exc
    # Belt-and-braces — if parse() ever returns a dict without ENGINE
    # (older dj_database_url versions did this on malformed input), still
    # fail loudly instead of letting Django produce the cryptic
    # ImproperlyConfigured("Please supply the ENGINE value") later.
    if not _parsed.get('ENGINE'):
        raise RuntimeError(
            f"DATABASE_URL is set but produced a database config with no "
            f"ENGINE (length={len(_db_url)}). Likely an unresolved Railway "
            f"reference. Verify the Postgres plugin and the reference name."
        )
    DATABASES = {'default': _parsed}
elif _is_production:
    raise RuntimeError(
        'DATABASE_URL is not set in production settings. '
        'Set it on the Railway web service Variables to '
        '${{ Postgres.DATABASE_URL }} (or another valid postgres:// URL). '
        'Refusing to boot with the SQLite fallback because every '
        'container restart would wipe the database.'
    )
else:
    # Dev/local fallback — SQLite file next to manage.py.
    DATABASES = {
        'default': dj_database_url.parse(
            f'sqlite:///{BASE_DIR / "db.sqlite3"}',
            conn_max_age=600,
        )
    }

# ── Cache ─────────────────────────────────────────────────────────────────────
# A SHARED Redis cache (set REDIS_URL — e.g. add a Railway Redis service and
# reference its connection URL) lets an approval invalidate the indicator cache
# for EVERY worker at once (indicators.service.bump_partner_version), so the
# dashboard totals update instantly. Without REDIS_URL we fall back to per-worker
# in-memory caching, where the short CACHE_TTL is the cross-worker backstop.
_redis_url = (os.environ.get('REDIS_URL', '') or os.environ.get('REDIS_PRIVATE_URL', '')).strip()
if _redis_url:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _redis_url,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'simple-indicators',
        }
    }

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'frontend' / 'dist']  # React build output
# WhiteNoise serves the React build at the root URL (not under /static/)
WHITENOISE_ROOT = BASE_DIR / 'frontend' / 'dist'
WHITENOISE_INDEX_FILE = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # Brute-force protection (audit AUTH-01): the login endpoint is the only
    # anonymous credential-checking surface. ScopedRateThrottle('login') on
    # LoginView reads this rate. Uses the `default` cache (Redis if configured,
    # else per-process LocMem — adequate for the single gunicorn worker).
    'DEFAULT_THROTTLE_RATES': {
        'login': '10/min',
    },
}

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# App-level config pulled from env — consumed by individual apps
FERNET_KEY = os.environ.get('FERNET_KEY', '')
# Old keys kept ONLY for decryption during a key rotation (comma-separated).
# Set this to the previous FERNET_KEY when rotating, run
# `manage.py rotate_fernet_key --commit`, then clear it. See fistula/encryption.py.
FERNET_KEY_FALLBACKS = [
    k.strip() for k in os.environ.get('FERNET_KEY_FALLBACKS', '').split(',')
    if k.strip()
]
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_IDS = os.environ.get('TELEGRAM_CHAT_IDS', '{}')

# ─── Email notifications (replacement for Telegram per Animesh spec) ──────────
# Used by submissions/email_notify.py to send approval / rejection /
# submission-received messages to focal persons. Set EMAIL_* env vars on
# Railway to enable; without them, Django falls back to the console backend
# so dev runs just print to stdout.
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'true').lower() == 'true'
DEFAULT_FROM_EMAIL = os.environ.get(
    'DEFAULT_FROM_EMAIL', 'SIMPLE <noreply@simple.unfpa.org.bd>'
)
# The real Railway web domain. The old default 'simple.up.railway.app' is now
# a DIFFERENT app (a third party's govuk-prototype-kit) — every email link
# (approval review, submission-received) that fell back to it pointed managers
# at a stranger's site. Always set SIMPLE_PUBLIC_URL on Railway; this default is
# the current working domain so a missing env var degrades safely, not to a
# foreign app.
SIMPLE_PUBLIC_URL = os.environ.get(
    'SIMPLE_PUBLIC_URL', 'https://web-production-091fa.up.railway.app'
)
KOBO_WEBHOOK_SECRET = os.environ.get('KOBO_WEBHOOK_SECRET', '')
KOBO_ASSET_UID_MPDSR = os.environ.get('KOBO_ASSET_UID_MPDSR', 'placeholder')
KOBO_ASSET_UID_FISTULA = os.environ.get('KOBO_ASSET_UID_FISTULA', 'placeholder')
KOBO_ASSET_UID_ACTIVITY = os.environ.get('KOBO_ASSET_UID_ACTIVITY', 'placeholder')
KOBO_ASSET_UID_BASELINE = os.environ.get('KOBO_ASSET_UID_BASELINE', 'placeholder')
KOBO_ASSET_UID_CLIENT_REG = os.environ.get('KOBO_ASSET_UID_CLIENT_REG', '')
KOBO_SERVER_URL = os.environ.get('KOBO_SERVER_URL', 'https://kobo.humanitarianresponse.info')

# KOBO_API_TOKEN: reserved for future pull-based sync. The current
# IDMS architecture uses webhook-push via KOBO_ASSET_UID_* vars — see
# submissions/views.py and programs/webhook.py for the ingestion path.
# This setting is read so deployments can stage the token before any
# pull-sync feature lands, but nothing in the current codebase invokes
# it. Audit FIX 16.3.
KOBO_API_TOKEN = os.environ.get('KOBO_API_TOKEN', '')

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles'
