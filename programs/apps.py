from django.apps import AppConfig


class ProgramsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'programs'
    verbose_name = 'SRHR Programmes'

    def ready(self):
        # Import once at app boot so the post_save receiver registers.
        # Module side-effects only; nothing else to call.
        from . import signals  # noqa: F401
        # Self-healing backstop: re-sync the client lookup CSVs to Kobo on a
        # timer so a dropped signal push (worker recycle) is reconciled within
        # one tick instead of permanently. No-op unless ENABLE_CSV_RESYNC_LOOP=1.
        from .resync_loop import start_resync_loop
        start_resync_loop()
