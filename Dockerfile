# Stage 1: Build React frontend
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium — renders the HTML-first report kit (infographic / report /
# pptx / web) to PNG/PDF server-side. --with-deps installs the system libraries
# Chromium needs on Debian slim.
RUN python -m playwright install --with-deps chromium

# Copy Django project
COPY . .

# Copy built React frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create staticfiles directory and collect static
RUN mkdir -p staticfiles mediafiles && python manage.py collectstatic --noinput

EXPOSE 8080

# What happens on every container start:
#   1. migrate            idempotent, runs every time, safe to repeat.
#   2. seed_users         no-op unless SEED_DB is set, AND it only creates an
#                         account whose own password variable is set too. See
#                         .env.example and Step 7 of docs/SERVER_SETUP_GUIDE.md.
#   3. seed_centers       no-op unless SEED_DB is set.
#   4. a few backfills    non-fatal; a failure logs and boot continues.
#   5. gunicorn           the web server. ONE worker, four threads, on purpose:
#                         five background jobs run as threads inside this
#                         process, so a second worker would run each of them
#                         twice. Scale with threads, never with workers.
#
# Boot must stay fast or the health check times out, so nothing heavy runs
# here. The optional one-time jobs below are each gated on their own variable:
# set it, restart once, then unset it.
#   APPROVE_PENDING_BANDHU=1   approve Bandhu clients left pending
#   SEED_BASELINE_DEMO=1       seed demonstration baseline interviews
#   REFRESH_DEMO_SEED=1        rebuild the demonstration data set
#
# No destructive command runs from this entrypoint, deliberately, so a stale
# variable can never wipe live data on a routine restart. flush_practice_data,
# purge_phd_data and prune_phd_centres are run by hand, after a backup.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_users && python manage.py seed_centers && python manage.py backfill_f4_facility && (python manage.py backfill_wellness_logbook --commit || echo 'backfill_wellness_logbook failed (non-fatal, continuing boot)') && (python manage.py backfill_outreach_fields --commit || echo 'backfill_outreach_fields failed (non-fatal, continuing boot)') && (python manage.py approve_pending_bandhu_logbook || echo 'approve_pending_bandhu_logbook failed (non-fatal, continuing boot)') && if [ \"$APPROVE_PENDING_BANDHU\" = \"1\" ]; then python manage.py approve_pending_bandhu_clients; fi && if [ \"$SEED_BASELINE_DEMO\" = \"1\" ]; then python manage.py seed_baseline_demo --wipe || echo 'seed_baseline_demo failed (non-fatal, continuing boot)'; fi && if [ \"$PURGE_TEST_BASELINE\" = \"1\" ]; then python manage.py purge_test_baseline --commit || echo 'purge_test_baseline failed (non-fatal, continuing boot)'; fi && if [ -n \"$FLUSH_BASELINE_DATA\" ] && [ \"$FLUSH_BASELINE_DATA\" != \"0\" ]; then python manage.py flush_baseline_data --scope \"$FLUSH_BASELINE_DATA\" --commit || echo 'flush_baseline_data failed (non-fatal, continuing boot)'; fi && if [ \"$BACKFILL_BASELINE_POPULATION\" = \"1\" ]; then python manage.py backfill_baseline_population --commit || echo 'backfill_baseline_population failed (non-fatal, continuing boot)'; fi && if [ \"$REFRESH_DEMO_SEED\" = \"1\" ]; then python manage.py seed_demo_mpdsr --purge && python manage.py seed_demo_fistula --purge && python manage.py seed_demo_phd_bandhu --purge && python manage.py seed_demo_mpdsr && python manage.py seed_demo_phd_bandhu && python manage.py seed_demo_fistula && python manage.py backfill_worker_name && python manage.py backfill_f4_facility; fi && gunicorn spondon.wsgi --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 --max-requests 500 --max-requests-jitter 50"]
