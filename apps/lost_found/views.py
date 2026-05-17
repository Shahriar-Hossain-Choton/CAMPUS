from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import Http404

from .models import (
    LostAndFoundPost,
    LostAndFoundPhoto,
    LostAndFoundTag,
    ClaimRequest,
    ClaimThread,
    SuggestedMatch,
)
from .forms import LostAndFoundPostForm, ClaimRequestForm
from .matching import run_auto_match

from apps.common.choices import (
    LostAndFoundPostType,
    LostAndFoundStatus,
    ClaimRequestStatus,
    LFSuggestedMatchStatus,
)
from apps.media.models import Photo

from apps.threads.models import Thread, ThreadParticipant
from apps.common.choices import ThreadVisibility, ThreadParticipantRole

# ---------------------------------------------------------------------------
# Post listing & detail
# ---------------------------------------------------------------------------


def post_list(request):
    """All active (active, not deleted) posts, newest first."""
    posts = (
        LostAndFoundPost.objects.filter(
            status=LostAndFoundStatus.ACTIVE,
            deleted_at__isnull=True,
        )
        .select_related("category", "user")
        .order_by("-created_at")
    )

    return render(request, "lost_found/post_list.html", {"posts": posts})


@login_required
def my_posts(request):
    """
    Shows the current user's active lost and found posts.
    Template: lost_found/my_posts.html
    """
    posts = (
        LostAndFoundPost.objects.filter(user=request.user)
        .select_related("category")
        .order_by("-created_at")
    )

    return render(
        request,
        "lost_found/my_posts.html",
        {
            "posts": posts,
            "LostAndFoundStatus": LostAndFoundStatus,
        },
    )


@login_required
def my_claims(request):
    """
    Shows the current user's claim history across all their lost posts.
    Template: lost_found/my_claims.html
    """
    claims = (
        ClaimRequest.objects.filter(claimer=request.user)
        .select_related("found_post", "found_post__category")
        .order_by("-created_at")
    )

    return render(
        request,
        "lost_found/my_claims.html",
        {
            "claims": claims,
            "ClaimRequestStatus": ClaimRequestStatus,
        },
    )


def post_detail(request, post_id):
    """
    Public post detail page.
    Renders the ClaimRequestForm for authenticated users who don't own the post.
    Template: lost_found/post_detail.html
    """
    post = get_object_or_404(
        LostAndFoundPost,
        pk=post_id,
        deleted_at__isnull=True,
    )

    claim_form = None
    existing_claim = None

    if (
        request.user.is_authenticated
        and post.user != request.user
        and post.type == LostAndFoundPostType.FOUND
    ):
        existing_claim = ClaimRequest.objects.filter(
            claimer=request.user, found_post=post
        ).first()

        if not existing_claim:
            claim_form = ClaimRequestForm(user=request.user, found_post=post)

    context = {
        "post": post,
        "claim_form": claim_form,
        "existing_claim": existing_claim,
    }
    return render(request, "lost_found/post_detail.html", context)


# ---------------------------------------------------------------------------
# Post creation
# ---------------------------------------------------------------------------


@login_required
def post_create(request):
    """
    Create a new lost-or-found post with optional photo uploads.
    Template: lost_found/post_form.html
    """
    if request.method == "POST":
        form = LostAndFoundPostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.status = (
                LostAndFoundStatus.ACTIVE
            )  # Auto-approve for simplicity; add moderation workflow as needed
            post.save()

            # Must call save_m2m() explicitly because we used commit=False.
            # Tags must be committed before run_auto_match() reads them.
            form.save_m2m()

            for order, file in enumerate(form.cleaned_data.get("uploaded_photos", [])):
                photo = Photo.objects.create(file=file, uploaded_by=request.user)
                LostAndFoundPhoto.objects.create(post=post, photo=photo, order=order)

            # Run auto-matching now that tags are persisted.
            suggestions = run_auto_match(post)

            # TODO — Notification hook:
            # for suggestion in suggestions:
            #     notify_user(
            #         recipient=suggestion.lost_post.user,
            #         verb="suggested_match",
            #         target=suggestion,
            #     )

            messages.success(
                request,
                f"Your {post.get_type_display().lower()} post has been created.",
            )
            return redirect("lost_found:post_detail", post_id=post.pk)
    else:
        form = LostAndFoundPostForm()

    all_tags = LostAndFoundTag.objects.order_by("name")
    selected_tag_ids = form["tags"].value() or []
    if isinstance(selected_tag_ids, str):
        selected_tag_ids = [selected_tag_ids]
    selected_tags = LostAndFoundTag.objects.filter(pk__in=selected_tag_ids).order_by(
        "name"
    )

    return render(
        request,
        "lost_found/post_form.html",
        {
            "form": form,
            "all_tags": all_tags,
            "selected_tag_ids": selected_tag_ids,
            "selected_tags": selected_tags,
        },
    )


# ---------------------------------------------------------------------------
# Manual claim — submission
# ---------------------------------------------------------------------------


@login_required
def submit_claim(request, post_id):
    """
    Submit a claim against a found post.

    Guards:
      - Must be authenticated (decorator)
      - Cannot claim your own post
      - Cannot submit a duplicate claim (unique_together enforced + guard here)
      - Post must be ACTIVE and active

    Template: Reuses lost_found/post_detail.html with form errors inline.
    """
    post = get_object_or_404(
        LostAndFoundPost,
        pk=post_id,
        status=LostAndFoundStatus.ACTIVE,
        deleted_at__isnull=True,
    )

    if post.user == request.user:
        messages.error(request, "You cannot claim your own post.")
        return redirect("lost_found:post_detail", post_id=post_id)

    already_claimed = ClaimRequest.objects.filter(
        claimer=request.user, found_post=post
    ).exists()
    if already_claimed:
        messages.info(request, "You have already submitted a claim for this post.")
        return redirect("lost_found:post_detail", post_id=post_id)

    if request.method == "POST":
        form = ClaimRequestForm(request.POST, user=request.user, found_post=post)
        if form.is_valid():
            claim = form.save(commit=False)
            claim.claimer = request.user
            claim.found_post = post
            claim.save()

            # TODO — Notification hook:
            # notify_user(
            #     recipient=post.user,
            #     verb="new_claim",
            #     target=claim,
            # )

            messages.success(
                request,
                "Your claim has been submitted. The finder will review it shortly.",
            )
            return redirect("lost_found:post_detail", post_id=post_id)
    else:
        # Shouldn't be reached via GET under normal navigation,
        # but redirect gracefully rather than 405.
        return redirect("lost_found:post_detail", post_id=post_id)

    # Re-render detail page with form errors inline
    context = {
        "post": post,
        "claim_form": form,
        "existing_claim": None,
    }
    return render(request, "lost_found/post_detail.html", context)


# ---------------------------------------------------------------------------
# Manual claim — review & approval (found-post owner only)
# ---------------------------------------------------------------------------


@login_required
def review_claims(request, post_id):
    """
    Found-post owner reviews all pending (and past) claims on their post.
    Template: lost_found/review_claims.html
    """
    post = get_object_or_404(
        LostAndFoundPost,
        pk=post_id,
        user=request.user,  # 404 if the viewer doesn't own it
        deleted_at__isnull=True,
    )

    claims = (
        ClaimRequest.objects.filter(found_post=post)
        .select_related("claimer", "lost_post")
        .order_by("-created_at")
    )

    context = {
        "post": post,
        "claims": claims,
        "ClaimRequestStatus": ClaimRequestStatus,
    }
    return render(request, "lost_found/review_claims.html", context)


@login_required
def approve_claim(request, post_id, claim_id):
    """
    Approve one claim for a found post.

    Side effects (all atomic):
      1. Mark this claim APPROVED.
      2. Bulk-reject all other PENDING claims on the same found_post.
      3. Mark found_post RESOLVED.
      4. Mark claim.lost_post RESOLVED (if linked).
      5. Create a private Thread + ClaimThread for handover communication.
      6. Add both parties as ThreadParticipants.

    Only the found-post owner can call this.
    Only works when the post is still ACTIVE (not already resolved).
    """
    post = get_object_or_404(
        LostAndFoundPost,
        pk=post_id,
        user=request.user,
        deleted_at__isnull=True,
    )

    if post.status == LostAndFoundStatus.RESOLVED:
        messages.error(request, "This post has already been resolved.")
        return redirect("lost_found:review_claims", post_id=post_id)

    claim = get_object_or_404(
        ClaimRequest,
        pk=claim_id,
        found_post=post,
        status=ClaimRequestStatus.PENDING,
    )

    if request.method == "POST":
        with transaction.atomic():
            # 1. Approve this claim
            claim.status = ClaimRequestStatus.APPROVED
            claim.save(update_fields=["status", "updated_at"])

            # 2. Reject all other pending claims on this post
            ClaimRequest.objects.filter(
                found_post=post,
                status=ClaimRequestStatus.PENDING,
            ).exclude(pk=claim.pk).update(status=ClaimRequestStatus.REJECTED)

            # 3. Mark found post resolved
            post.status = LostAndFoundStatus.RESOLVED
            post.save(update_fields=["status", "updated_at"])

            # 4. Mark claimer's lost post resolved (if they linked one)
            if claim.lost_post_id:
                LostAndFoundPost.objects.filter(pk=claim.lost_post_id).update(
                    status=LostAndFoundStatus.RESOLVED
                )

            # 5. Promote any SuggestedMatch between these posts to CONVERTED
            if claim.lost_post_id:
                SuggestedMatch.objects.filter(
                    lost_post=claim.lost_post,
                    found_post=post,
                ).update(status=LFSuggestedMatchStatus.CONVERTED)

            # 6. Create the private communication thread
            thread = Thread.objects.create(
                title=f"Claim handover: {post.title}",
                description=(
                    f"Private thread for claim #{claim.pk}. "
                    f"Use this to arrange the return of the item."
                ),
                visibility=ThreadVisibility.PRIVATE,
            )
            ThreadParticipant.objects.create(
                thread=thread,
                user=request.user,  # found-post owner
                role=ThreadParticipantRole.AUTHOR,
            )
            ThreadParticipant.objects.create(
                thread=thread,
                user=claim.claimer,
                role=ThreadParticipantRole.MEMBER,
            )
            ClaimThread.objects.create(claim_request=claim, thread=thread)

            # TODO — Notification hooks:
            # notify_user(
            #     recipient=claim.claimer,
            #     verb="claim_approved",
            #     target=claim,
            # )
            # bulk_notify_rejected(found_post=post, exclude_claim=claim)
            # The thread URL: reverse("threads:thread_detail", kwargs={"thread_id": thread.pk})

        messages.success(
            request,
            "Claim approved. A private thread has been created for handover coordination.",
        )
        return redirect("lost_found:review_claims", post_id=post_id)

    # GET — confirmation page
    return render(
        request,
        "lost_found/approve_claim_confirm.html",
        {
            "post": post,
            "claim": claim,
        },
    )


# ---------------------------------------------------------------------------
# Auto-match suggestions (lost-post owner's inbox)
# ---------------------------------------------------------------------------


@login_required
def my_suggested_matches(request):
    """
    Shows the current user's pending auto-match suggestions for their
    active LOST posts.
    Template: lost_found/my_suggested_matches.html
    """
    suggestions = (
        SuggestedMatch.objects.filter(
            lost_post__user=request.user,
            lost_post__deleted_at__isnull=True,
            status=LFSuggestedMatchStatus.PENDING,
        )
        .select_related("lost_post", "found_post", "found_post__category")
        .prefetch_related("found_post__tags", "found_post__post_photos__photo")
        .order_by("-score", "-created_at")
    )

    return render(
        request,
        "lost_found/my_suggested_matches.html",
        {
            "suggestions": suggestions,
        },
    )


@login_required
def dismiss_suggested_match(request, suggestion_id):
    """
    Lost-post owner dismisses a suggestion they're not interested in.
    POST only — use a small form/button in the template.
    """
    suggestion = get_object_or_404(
        SuggestedMatch,
        pk=suggestion_id,
        lost_post__user=request.user,  # must own the lost post
        status=LFSuggestedMatchStatus.PENDING,
    )

    if request.method == "POST":
        suggestion.status = LFSuggestedMatchStatus.DISMISSED
        suggestion.save(update_fields=["status"])
        messages.info(request, "Suggestion dismissed.")

    return redirect("lost_found:my_suggested_matches")
