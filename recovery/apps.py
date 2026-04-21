from django.apps import AppConfig


class RecoveryConfig(AppConfig):
    name = 'recovery'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from . import signals  # noqa: F401 — side-effect: connect signal handlers
