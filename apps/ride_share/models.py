# apps/ride_share/models.py
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce

from apps.common.choices import (
    TransportMethod, TRANSPORT_CAPACITY, RidePostStatus,
    RideGroupStatus, RideGroupMemberStatus
)

UIU_LOCATION = "United International University, Madani Ave, Dhaka"

class RideDirection(models.TextChoices):
    TO_UNIVERSITY = "to_university", "Going to University"
    TO_HOME = "to_home", "Going Home"

# ─────────────────────────────────────────────
# Ride Post
# ─────────────────────────────────────────────
class RidePost(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ride_posts')
    starting_location = models.CharField(max_length=255, help_text="Your pickup area or landmark")
    destination_location = models.CharField(max_length=255, blank=True, default=UIU_LOCATION)
    direction = models.CharField(max_length=20, choices=RideDirection.choices, default=RideDirection.TO_UNIVERSITY)
    departure_time = models.DateTimeField()
    expires_at = models.DateTimeField()
    transport_method = models.CharField(max_length=20, choices=TransportMethod.choices)
    max_capacity = models.PositiveIntegerField(editable=False)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=RidePostStatus.choices, default=RidePostStatus.OPEN)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def save(self, *args, **kwargs):
        if not self.pk:
            self.max_capacity = TRANSPORT_CAPACITY.get(self.transport_method, 1)
            if self.departure_time and not self.expires_at:
                self.expires_at = self.departure_time + timezone.timedelta(hours=2)
        
        if self.expires_at and self.departure_time and self.expires_at < self.departure_time:
            raise ValueError("expires_at cannot be before departure_time.")
        super().save(*args, **kwargs)

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.status = RidePostStatus.CANCELLED
        self.save(update_fields=['deleted_at', 'status', 'updated_at'])

# ─────────────────────────────────────────────
# Ride Group
# ─────────────────────────────────────────────
class RideGroup(models.Model):
    ride_post = models.OneToOneField(RidePost, on_delete=models.CASCADE, related_name='ride_group')
    thread = models.OneToOneField('threads.Thread', on_delete=models.PROTECT, null=True, blank=True, related_name='ride_group')
    status = models.CharField(max_length=20, choices=RideGroupStatus.choices, default=RideGroupStatus.FORMING)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def max_capacity(self):
        return self.ride_post.max_capacity

    @property
    def current_occupancy(self):
        # Flattened calculation based directly on members
        result = self.members.filter(
            status=RideGroupMemberStatus.CONFIRMED
        ).aggregate(total=Sum(Coalesce('party_size', Value(1))))
        return result['total'] or 0

    @property
    def is_full(self):
        return self.current_occupancy >= self.max_capacity

# ─────────────────────────────────────────────
# Ride Group Member
# ─────────────────────────────────────────────
class RideGroupMember(models.Model):
    group = models.ForeignKey(RideGroup, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ride_group_memberships')
    
    party_size = models.PositiveIntegerField(
        default=1, 
        validators=[MinValueValidator(1)],
        help_text="How many people including the requester"
    )
    is_initiator = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=RideGroupMemberStatus.choices, default=RideGroupMemberStatus.CONFIRMED)
    
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('group', 'user')
