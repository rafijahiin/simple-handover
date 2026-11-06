from .base import *  # noqa: F403  -- split-settings pattern

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

# Vite dev server runs on :5173 and proxies /api + /admin through to
# Django on :8000. Django's CSRF middleware checks the Origin header
# against CSRF_TRUSTED_ORIGINS for unsafe methods; without :5173 here
# every PATCH / POST from the SPA fails with 'Origin checking failed'.
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
