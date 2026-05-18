from django.apps import AppConfig


class ThreadsConfig(AppConfig):
    name = "apps.threads"

    def ready(self):
        import apps.threads.signals  # noqa: F401
