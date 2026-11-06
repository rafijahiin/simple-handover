from django.apps import AppConfig


class MpdsrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mpdsr'

    def ready(self):
        # Keep the CIPRB data-integrity snapshot fresh so the dashboard health
        # strip reflects reality. No-op unless ENABLE_RECON_LOOP=1. Heavy tick,
        # long interval; the equivalent Railway cron is a cleaner alternative.
        from .recon_loop import start_recon_loop
        start_recon_loop()
