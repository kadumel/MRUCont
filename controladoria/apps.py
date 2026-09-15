from django.apps import AppConfig


class ControladoriaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'controladoria'
    verbose_name = 'Controladoria BI'

    def ready(self):
        import controladoria.signals  # noqa: F401
