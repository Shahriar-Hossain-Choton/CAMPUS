"""
Lost & Found — Auto-matching logic
===================================
Kept as a plain module (not a signal handler) so it can be called *after*
M2M tags are committed to the database.  Signals fire inside Model.save(),
before form.save_m2m() has run, which means tag data isn't available yet.

Call sites:
  - views.post_create  → after form.save_m2m() and photo upload
  - views.post_edit    → same

Future: if you add a management command to re-score existing suggestions,
just import and call run_auto_match() in a loop there too.
"""

from .models import LostAndFoundPost, SuggestedMatch
from apps.common.choices import (
    LostAndFoundPostType,
    LostAndFoundStatus,
    LFSuggestedMatchStatus,
)


def _active_posts():
    """Base queryset: active, not soft-deleted."""
    return LostAndFoundPost.objects.filter(
        status=LostAndFoundStatus.ACTIVE,
        deleted_at__isnull=True,
    )


def run_auto_match(post: LostAndFoundPost) -> list[SuggestedMatch]:
    """
    Given a newly saved/updated post, find candidate counterparts,
    score by tag overlap, and persist SuggestedMatch rows.

    Returns the list of created-or-updated SuggestedMatch objects
    so the caller can fan out notifications if desired.

    Only creates a match if score > 0 — same-category with zero shared
    tags is too weak a signal.  Raise this threshold or make it a setting
    if you want stricter suggestions.
    """

    if post.type == LostAndFoundPostType.LOST:
        lost_post = post
        candidates = (
            _active_posts()
            .filter(
                type=LostAndFoundPostType.FOUND,
                category=post.category,
            )
            .exclude(pk=post.pk)
        )
    else:
        found_post = post
        candidates = (
            _active_posts()
            .filter(
                type=LostAndFoundPostType.LOST,
                category=post.category,
            )
            .exclude(pk=post.pk)
        )

    post_tag_ids = set(post.tags.values_list("id", flat=True))
    results = []

    for candidate in candidates:
        candidate_tag_ids = set(candidate.tags.values_list("id", flat=True))
        score = len(post_tag_ids & candidate_tag_ids)

        if score == 0:
            continue  # not enough signal — skip

        if post.type == LostAndFoundPostType.LOST:
            kwargs = {"lost_post": lost_post, "found_post": candidate}
        else:
            kwargs = {"lost_post": candidate, "found_post": found_post}

        suggestion, created = SuggestedMatch.objects.get_or_create(
            **kwargs,
            defaults={"score": score, "status": LFSuggestedMatchStatus.PENDING},
        )

        if not created and suggestion.score != score:
            # Score may drift as tags are edited — keep it fresh.
            suggestion.score = score
            suggestion.save(update_fields=["score"])

        results.append(suggestion)

        # ------------------------------------------------------------------
        # TODO — Notification hook
        # Notify the lost-post owner that a potential match was found.
        # Replace this comment with a call to your notification service, e.g.:
        #
        #   notify_user(
        #       recipient=suggestion.lost_post.user,
        #       verb="suggested_match",
        #       target=suggestion,
        #   )
        #
        # The notification system should link back to:
        #   reverse("lost_found:my_suggested_matches")
        # ------------------------------------------------------------------

    return results
