# apps/ride_share/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import RidePost, RideGroup, RideGroupMember, RideDirection
from apps.common.choices import RidePostStatus, RideGroupMemberStatus


@receiver(post_save, sender=RidePost)
def auto_match_ride_posts(sender, instance, created, **kwargs):
    """
    Auto-match ride posts when a new post is created.
    
    Matching logic:
    - If direction is TO_UNIVERSITY: match posts with same starting_location
    - If direction is TO_HOME: match posts with same destination_location
    """
    if not created or instance.deleted_at:
        return
    
    # Find matching posts from other users
    if instance.direction == RideDirection.TO_UNIVERSITY:
        # Match by starting location
        matching_posts = RidePost.objects.filter(
            starting_location=instance.starting_location,
            direction=RideDirection.TO_UNIVERSITY,
            status=RidePostStatus.OPEN,
            deleted_at__isnull=True,
        ).exclude(
            pk=instance.pk,
            user=instance.user
        )
    else:  # TO_HOME
        # Match by destination location
        matching_posts = RidePost.objects.filter(
            destination_location=instance.destination_location,
            direction=RideDirection.TO_HOME,
            status=RidePostStatus.OPEN,
            deleted_at__isnull=True,
        ).exclude(
            pk=instance.pk,
            user=instance.user
        )
    
    # Create pending requests for matching ride groups; organizer must approve
    for matching_post in matching_posts:
        # Check if group exists and is not full
        if not hasattr(matching_post, 'ride_group') or not matching_post.ride_group:
            continue
        
        # Check if user is not already in the group
        if RideGroupMember.objects.filter(
            group=matching_post.ride_group,
            user=instance.user
        ).exists():
            continue
        
        RideGroupMember.objects.create(
        group=ride_group,
            user=instance.user,
            is_initiator=False,
            status=RideGroupMemberStatus.PENDING,
    )
