import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'spondon.settings.production')
application = get_wsgi_application()

# Started here rather than in AppConfig.ready() so it only ever runs in the web
# process. ready() also fires for migrate, seed commands and the test runner,
# and a deletion sweep has no business starting during any of those.
# No-op unless KOBO_DELETION_SYNC names the organisations to sweep.
from programs.kobo_sync_daemon import start as _start_kobo_sync  # noqa: E402

_start_kobo_sync()
