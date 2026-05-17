from django.db import transaction
from .models import ExchangePost, ExchangeMatch
from apps.common.choices import ExchangePostStatus, ExchangeMatchStatus
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Avg, Count
from .models import SessionFeedback


def find_and_create_matches(instance):
    """
    Matching Engine:
    Finds all potential trades between the new post and existing posts.
    Creates a unique ExchangeMatch record for every valid skill-pair combination.
    """
    # 1. Validation: Only match active, non-deleted posts
    if instance.deleted_at or instance.status != ExchangePostStatus.MATCHING:
        return

    # 2. Find candidate posts (others looking for what I have AND having what I need)
    candidates = (
        ExchangePost.objects.filter(
            deleted_at__isnull=True,
            status=ExchangePostStatus.MATCHING,
        )
        .exclude(author=instance.author)
        .prefetch_related("skills_offered", "skills_needed")
    )

    # Convert my skills to sets for efficient intersection
    my_offered_ids = set(instance.skills_offered.values_list("id", flat=True))
    my_needed_ids = set(instance.skills_needed.values_list("id", flat=True))

    for cand in candidates:
        cand_offered_ids = set(cand.skills_offered.values_list("id", flat=True))
        cand_needed_ids = set(cand.skills_needed.values_list("id", flat=True))

        # Intersection: What I teach that they want, and what they teach that I want
        i_can_teach_them = my_offered_ids & cand_needed_ids
        they_can_teach_me = cand_offered_ids & my_needed_ids

        # If there's a mutual overlap, create matches for every specific skill pair
        if i_can_teach_them and they_can_teach_me:
            with transaction.atomic():
                for s_offered_id in i_can_teach_them:
                    for s_needed_id in they_can_teach_me:

                        # Maintain consistency (p_a < p_b) for database unique constraints
                        if instance.id < cand.id:
                            p_a, p_b = instance, cand
                            skill_a, skill_b = s_offered_id, s_needed_id
                        else:
                            p_a, p_b = cand, instance
                            skill_a, skill_b = s_needed_id, s_offered_id

                        # Create the match if it doesn't exist
                        ExchangeMatch.objects.get_or_create(
                            ex_p_a=p_a,
                            ex_p_b=p_b,
                            skill_a_offers_id=skill_a,
                            skill_b_offers_id=skill_b,
                            defaults={"status": ExchangeMatchStatus.PENDING},
                        )


@receiver([post_save, post_delete], sender=SessionFeedback)
def update_user_sx_rating_avg(sender, instance, **kwargs):
    """Update the user's profile rating using a Bayesian Average."""
    rated_user = instance.rated_user

    # 1. Get raw average AND the total count of reviews for this user
    stats = SessionFeedback.objects.filter(rated_user=rated_user).aggregate(
        avg_rating=Avg("rating"), review_count=Count("rating")
    )

    R = stats["avg_rating"] or 0.0
    v = stats["review_count"] or 0

    global_stats = SessionFeedback.objects.aggregate(global_avg=Avg("rating"))

    # 2. Define Bayesian Constants
    # C = Platform average. We can calculate this dynamically, but hardcoding a reasonable
    #     starting expectation saves database performance.
    # m = How many reviews it takes to overcome the "padding"
    C = global_stats["global_avg"] or 7.0
    m = 3.0

    # 3. Calculate Bayesian Average
    if v == 0:
        weighted_score = 0.0
    else:
        weighted_score = ((R * v) + (C * m)) / (v + m)

    rated_user.profile.sx_rating_avg = round(weighted_score, 1)
    rated_user.profile.save(update_fields=["sx_rating_avg"])
