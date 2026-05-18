from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "verb", "created_at", "read_at")
    search_fields = ("recipient__email", "verb")
    list_filter = ("read_at", "created_at")
    readonly_fields = ("created_at",)
