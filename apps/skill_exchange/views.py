from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, render, redirect
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_POST

# from django.urls import reverse

from .forms import SkillExchangePostForm
from .signals import find_and_create_matches
from .models import (
    # MatchDecision,
    ExchangePost,
    ExchangeMatch,
    ExchangeSession,
    # SessionEndRequest,
    SessionFeedback,
)
from apps.threads.models import Thread, ThreadParticipant
from apps.common.choices import (
    ExchangeMatchStatus,
    ExchangePostStatus,
    ExchangeSessionStatus,
    # MatchDecisionStatus,
    ThreadVisibility,
    ThreadParticipantRole,
    # SessionEndRequestStatus,
    ThreadStatus,
)

# --- POST MANAGEMENT ---


@login_required
def post_list(request):
    """View your own posts and their status."""
    posts = ExchangePost.objects.filter(
        author=request.user, status=ExchangePostStatus.MATCHING
    ).order_by("-created_at")
    return render(request, "skill_exchange/post_list.html", {"posts": posts})


@login_required
def post_create(request):
    """Create a new post and trigger the matching engine."""
    if request.method == "POST":
        # Pass the user to the form so it can validate against duplicate posts
        form = SkillExchangePostForm(request.POST, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                post = form.save(commit=False)
                post.author = request.user
                post.save()
                form.save_m2m()  # Save many-to-many data for skills

            # Trigger matching engine
            find_and_create_matches(post)
            messages.success(request, "Exchange post created successfully!")
            return redirect("skill_exchange:post_list")
        else:
            # --- EXTRACT ERRORS INTO DJANGO MESSAGES ---
            for field, errors in form.errors.items():
                for error in errors:
                    if field == "__all__":
                        # Non-field errors (like the duplicate post check we just added)
                        messages.error(request, error)
                    # else:
                    #     # Field-specific errors
                    #     # Optional: format it to look nicer (e.g., "Description: This field is required.")
                    #     field_name = form.fields[field].label or field.capitalize()
                    #     messages.error(request, f"{field_name}: {error}")
    else:
        # Pass user here as well just to be consistent, though not strictly needed for GET
        form = SkillExchangePostForm(user=request.user)

    return render(request, "skill_exchange/post_create.html", {"form": form})


@login_required
@require_POST
def post_delete(request, post_id):
    """
    Rule 1: Posts are immutable. To change skills, user must delete and recreate.
    This also cleans up any pending matches.
    """
    post = get_object_or_404(ExchangePost, pk=post_id, author=request.user)

    with transaction.atomic():
        # Soft delete the post
        post.deleted_at = timezone.now()
        post.status = ExchangePostStatus.DELETED
        post.save()

        # Delete any matches that haven't become sessions yet
        ExchangeMatch.objects.filter(
            Q(ex_p_a=post) | Q(ex_p_b=post), status=ExchangeMatchStatus.PENDING
        ).delete()

    messages.info(request, "Post deleted and pending matches removed.")
    return redirect("skill_exchange:post_list")


# --- MATCHING & HANDSHAKE ---


@login_required
def match_list(request):
    pending_matches = ExchangeMatch.objects.filter(
        Q(ex_p_a__author=request.user) | Q(ex_p_b__author=request.user),
        status=ExchangeMatchStatus.PENDING,
    ).select_related(
        "ex_p_a__author", "ex_p_b__author", "skill_a_offers", "skill_b_offers"
    )

    # Attach the relative context to each match for the template
    for match in pending_matches:
        match.user_context = match.get_context_for_user(request.user)

    return render(
        request,
        "skill_exchange/match_list.html",
        {"pending_matches": pending_matches},
    )


@login_required
def session_list(request):
    active_sessions = ExchangeSession.objects.filter(
        Q(match__ex_p_a__author=request.user) | Q(match__ex_p_b__author=request.user),
        status=ExchangeSessionStatus.ACTIVE,
    )

    # Do the same for sessions if you want to use the helper there
    for session in active_sessions:
        session.user_context = session.match.get_context_for_user(request.user)

    return render(
        request,
        "skill_exchange/session_list.html",
        {"active_sessions": active_sessions},
    )


@login_required
@require_POST
def match_confirm_decision(request, match_id):
    """The Two-Way Handshake logic for accepting a match."""
    match = get_object_or_404(ExchangeMatch, pk=match_id)
    action = request.POST.get("action")  # 'accepted' or 'rejected'

    if action == "rejected":
        match.status = ExchangeMatchStatus.REJECTED
        match.save()
        messages.info(request, "Match declined.")
        return redirect("skill_exchange:match_list")

    # Identify which user is accepting and set their flag
    if match.ex_p_a.author == request.user:
        match.user_a_accepted = True
    elif match.ex_p_b.author == request.user:
        match.user_b_accepted = True

    match.save()

    if match.user_a_accepted and match.user_b_accepted:
        with transaction.atomic():
            match.status = ExchangeMatchStatus.CONFIRMED
            match.save()

            thread_title = f"Skill Exchange: {match.skill_a_offers.name} ↔ {match.skill_b_offers.name}"
            thread = Thread.objects.create(
                title=thread_title, visibility=ThreadVisibility.PRIVATE
            )

            # Add both authors as participants
            ThreadParticipant.objects.create(
                thread=thread,
                user=match.ex_p_a.author,
                role=ThreadParticipantRole.MEMBER,
            )
            ThreadParticipant.objects.create(
                thread=thread,
                user=match.ex_p_b.author,
                role=ThreadParticipantRole.MEMBER,
            )

            # Create the Session
            ExchangeSession.objects.create(
                match=match, thread=thread, status=ExchangeSessionStatus.ACTIVE
            )
            messages.success(request, "Match confirmed! A new session has started.")
            return redirect("threads:thread_detail", thread_id=thread.id)

    return redirect("skill_exchange:match_list")


# --- SESSION MANAGEMENT ---


@login_required
@require_POST
def session_complete_decision(request, session_id):
    session = get_object_or_404(
        ExchangeSession, pk=session_id, status=ExchangeSessionStatus.ACTIVE
    )

    # Set the flag for the current user
    if session.match.ex_p_a.author == request.user:
        session.user_a_completed = True
    elif session.match.ex_p_b.author == request.user:
        session.user_b_completed = True

    # Check if both are now done
    if session.user_a_completed and session.user_b_completed:
        with transaction.atomic():
            session.status = ExchangeSessionStatus.COMPLETED
            session.save()
            # Also close the associated thread
            session.thread.status = ThreadStatus.CLOSED
            session.thread.save()
        messages.success(request, "Exchange successfully completed!")
    else:
        session.save()
        messages.info(request, "Completion status recorded.")

    return redirect("threads:thread_detail", thread_id=session.thread.id)


# --- FEEDBACK MANAGEMENT ---


@login_required
@require_POST
def submit_session_feedback(request, session_id):
    session = get_object_or_404(ExchangeSession, pk=session_id)

    # Determine who the partner is
    if session.match.ex_p_a.author == request.user:
        partner = session.match.ex_p_b.author
    elif session.match.ex_p_b.author == request.user:
        partner = session.match.ex_p_a.author
    else:
        messages.error(request, "You are not a participant in this session.")
        return redirect("skill_exchange:session_list")

    # Get rating from form (HTML form)
    try:
        rating = int(request.POST.get("rating"))
        if rating < 1 or rating > 10:
            raise ValueError
    except (TypeError, ValueError):
        messages.error(
            request, "Invalid rating. Must be a whole number between 1 and 10."
        )
        return redirect("threads:thread_detail", thread_id=session.thread.id)

    notes = request.POST.get("notes", "")

    # Create or update the feedback
    SessionFeedback.objects.update_or_create(
        exchange_session=session,
        rated_by_user=request.user,
        defaults={
            "rated_user": partner,
            "rating": rating,
            "notes": notes,
        },
    )

    messages.success(request, "Your feedback has been saved securely!")
    return redirect("threads:thread_detail", thread_id=session.thread.id)


# @login_required
# def session_detail(request, session_id):
#     """Redirects the user to the thread view with the session context."""
#     session = get_object_or_404(ExchangeSession, pk=session_id)
#     # Ensure user is part of the session
#     if request.user not in [session.match.ex_p_a.author, session.match.ex_p_b.author]:
#         return redirect("skill_exchange:match_list")

#     # Redirect to the thread detail view in the threads app
#     return redirect("threads:thread_detail", thread_id=session.thread.id)


# @login_required
# @require_POST
# def session_end_request(request, session_id):
#     """Initiate the 'End Session' handshake."""
#     session = get_object_or_404(
#         ExchangeSession, pk=session_id, status=ExchangeSessionStatus.ACTIVE
#     )

#     # Create the request if it doesn't exist
#     SessionEndRequest.objects.get_or_create(
#         exchange_session=session,
#         requested_by=request.user,
#         status=SessionEndRequestStatus.PENDING,
#     )

#     return redirect("threads:thread_detail", thread_id=session.thread.id)


# @login_required
# @require_POST
# def session_end_decision(request, session_id):
#     """Respond to an 'End Session' request."""
#     session = get_object_or_404(ExchangeSession, pk=session_id)
#     end_request = get_object_or_404(
#         SessionEndRequest,
#         exchange_session=session,
#         status=SessionEndRequestStatus.PENDING,
#     )

#     action = request.POST.get("action")  # 'approve' or 'deny'

#     with transaction.atomic():
#         if action == "approve":
#             end_request.status = SessionEndRequestStatus.APPROVED
#             end_request.responded_at = timezone.now()
#             end_request.save()

#             session.status = ExchangeSessionStatus.COMPLETED
#             session.save()

#             # Close the thread to new messages
#             session.thread.status = ThreadStatus.CLOSED
#             session.thread.save()
#         else:
#             # If denied, delete the request so someone can request again later
#             end_request.delete()

#     return redirect("threads:thread_detail", thread_id=session.thread.id)
