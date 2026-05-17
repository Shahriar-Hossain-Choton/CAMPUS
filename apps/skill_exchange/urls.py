from django.urls import path

from . import views

app_name = "skill_exchange"

urlpatterns = [
    path("posts/", views.post_list, name="post_list"),
    path("posts/new/", views.post_create, name="post_create"),
    path(
        "posts/<int:post_id>/delete/", views.post_delete, name="post_delete"
    ),  # Updated
    path("matches/", views.match_list, name="match_list"),
    path("sessions/", views.session_list, name="session_list"),
    path(
        "matches/<int:match_id>/confirm/",
        views.match_confirm_decision,
        name="match_confirm_decision",
    ),
    path(
        "sessions/<int:session_id>/complete/",
        views.session_complete_decision,
        name="session_complete_decision",
    ),
    path(
        "sessions/<int:session_id>/feedback/",
        views.submit_session_feedback,
        name="submit_session_feedback",
    ),
    # path("sessions/<int:session_id>/", views.session_detail, name="session_detail"),
    # path(
    #     "sessions/<int:session_id>/end-request/",
    #     views.session_end_request,
    #     name="session_end_request",
    # ),
    # path(
    #     "sessions/<int:session_id>/end-decision/",
    #     views.session_end_decision,
    #     name="session_end_decision",
    # ),
]
