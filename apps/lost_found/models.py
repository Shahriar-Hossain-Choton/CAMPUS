from django.db import models
from django.conf import settings
from apps.common.choices import (
    LostAndFoundStatus,
    ClaimRequestStatus,
    LostAndFoundPostType,
    LFSuggestedMatchStatus,
)

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------


class LostAndFoundCategory(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class LostAndFoundTag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Core post
# ---------------------------------------------------------------------------


class LostAndFoundPost(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    lost_or_found_date = models.DateField()
    location = models.CharField(max_length=100)

    type = models.CharField(max_length=20, choices=LostAndFoundPostType.choices)
    status = models.CharField(
        max_length=20,
        choices=LostAndFoundStatus.choices,
        default=LostAndFoundStatus.PENDING,
    )

    category = models.ForeignKey(LostAndFoundCategory, on_delete=models.CASCADE)
    tags = models.ManyToManyField(LostAndFoundTag, blank=True)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lost_and_found_posts",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title

    @property
    def is_active(self):
        return self.deleted_at is None and self.status == LostAndFoundStatus.ACTIVE


class LostAndFoundPhoto(models.Model):
    post = models.ForeignKey(
        LostAndFoundPost,
        on_delete=models.CASCADE,
        related_name="post_photos",
    )
    photo = models.ForeignKey(
        "media.Photo",
        on_delete=models.CASCADE,
        related_name="lost_found_attachments",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]


# ---------------------------------------------------------------------------
# Manual claim flow
#
# Flow:
#   1. Any authenticated user sees a found post → submits ClaimRequest
#   2. Found-post owner reviews claims via review_claims view
#   3. Owner approves one → approve_claim view:
#        - sets this claim APPROVED
#        - bulk-rejects all other PENDING claims on the same found_post
#        - marks both posts RESOLVED
#        - creates a private Thread + ClaimThread for communication
#   4. Claimer and found-post owner continue via the thread (threads app)
# ---------------------------------------------------------------------------


class ClaimRequest(models.Model):
    """
    A user's request to claim a found item.

    - `claimer`   — the person asserting "this item is mine"
    - `found_post` — the FOUND post they are claiming against
    - `lost_post`  — (optional) the claimer's own LOST post for this item;
                     providing it gives the reviewer stronger context and
                     feeds into the matching score if auto-suggest hasn't
                     already paired these posts.
    """

    claimer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="claim_requests",
    )
    found_post = models.ForeignKey(
        LostAndFoundPost,
        on_delete=models.CASCADE,
        related_name="received_claims",
    )
    # Optional link to the claimer's own lost post.
    # SET_NULL so deleting the lost post doesn't cascade and kill the claim.
    lost_post = models.ForeignKey(
        LostAndFoundPost,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_claims",
    )

    message = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=ClaimRequestStatus.choices,
        default=ClaimRequestStatus.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # One active claim per user per found post — enforced at DB level.
        # If you want to allow re-claiming after rejection, move this to a
        # partial unique index or handle it in the view.
        unique_together = ("claimer", "found_post")

    def __str__(self):
        return f"Claim #{self.pk} by {self.claimer} on Found Post #{self.found_post_id}"


class ClaimThread(models.Model):
    """
    Created once a ClaimRequest is approved.
    Links the approved claim to a private Thread so the two parties
    can coordinate handover without exposing their contact details.

    The Thread's participants are added at creation time:
      - found_post.user  → role AUTHOR
      - claim.claimer    → role MEMBER
    """

    claim_request = models.OneToOneField(
        ClaimRequest,
        on_delete=models.CASCADE,
        related_name="claim_thread",
    )
    thread = models.OneToOneField(
        "threads.Thread",
        on_delete=models.CASCADE,
        related_name="claim_thread",
    )

    def __str__(self):
        return f"ClaimThread for Claim #{self.claim_request_id}"


# ---------------------------------------------------------------------------
# Auto-match suggestion
#
# Flow:
#   1. A post is saved (ACTIVE, not deleted) → matching.run_auto_match(post)
#      is called from the view after M2M tags are committed.
#   2. Candidates: opposite type, same category, also active + not deleted.
#   3. Score = number of shared tags. Skip if score == 0.
#   4. SuggestedMatch created (or score updated if it already exists).
#   5. TODO: notify lost_post.user — hook into notification system here.
#
# Lifecycle:  PENDING → DISMISSED (owner not interested)
#                    → CONVERTED  (a ClaimRequest was approved between these posts)
# ---------------------------------------------------------------------------


class SuggestedMatch(models.Model):
    """
    System-generated pairing between a LOST post and a FOUND post,
    based on same category + tag-overlap scoring.
    """

    lost_post = models.ForeignKey(
        LostAndFoundPost,
        on_delete=models.CASCADE,
        related_name="suggested_as_lost",
    )
    found_post = models.ForeignKey(
        LostAndFoundPost,
        on_delete=models.CASCADE,
        related_name="suggested_as_found",
    )

    # Number of shared tags between the two posts at the time of suggestion.
    score = models.PositiveIntegerField(
        default=0,
        help_text="Tag-overlap count used to rank suggestions.",
    )

    status = models.CharField(
        max_length=20,
        choices=LFSuggestedMatchStatus.choices,
        default=LFSuggestedMatchStatus.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("lost_post", "found_post")
        ordering = ["-score", "-created_at"]

    def __str__(self):
        return (
            f"SuggestedMatch (score={self.score}): "
            f"Lost#{self.lost_post_id} ↔ Found#{self.found_post_id} [{self.status}]"
        )
