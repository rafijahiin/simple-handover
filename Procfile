# NOTE: railway.json pins the DOCKERFILE builder, so this Procfile is NOT
# used on Railway today — the Dockerfile CMD is the source of truth. It is
# kept in sync with that CMD (migrate + self-gating seeds + gunicorn) only
# as a safety net so that if the builder ever falls back to Nixpacks, seeding
# does not silently stop (audit FIX M7). seed_users/seed_centers self-gate on
# the SEED_DB env var and are no-ops unless it is set.
web: python manage.py migrate --noinput && python manage.py seed_users && python manage.py seed_centers && python manage.py seed_demo_mpdsr && python manage.py seed_demo_phd_bandhu && python manage.py seed_demo_fistula && gunicorn spondon.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --max-requests 500 --max-requests-jitter 50
