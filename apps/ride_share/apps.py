from django.apps import AppConfig


class RideShareConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ride_share'
    
    def ready(self):
        import apps.ride_share.signals
