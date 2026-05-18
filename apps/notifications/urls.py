from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    path("unread_count/", views.unread_count, name="unread_count"),
    path("list/", views.list_notifications, name="list"),
    path("mark_read/", views.mark_read, name="mark_read"),
]
