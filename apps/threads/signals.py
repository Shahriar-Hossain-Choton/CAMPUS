"""
Threads app signals: notify participants on new messages.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

from .models import ThreadMessage, ThreadParticipant
from apps.notifications.signals import notify


@receiver(post_save, sender=ThreadMessage)
def notify_participants_on_message(sender, instance, created, **kwargs):
    """Notify all thread participants (except sender) when a new message arrives."""
    if not created:
        return

    # Skip soft-deleted messages
    if instance.deleted_at:
        return

    thread = instance.thread
    sender_user = instance.sender

    # Skip forum threads; only notify participants of non-forum threads.
    if hasattr(thread, "forumthread"):
        return

    # Get all participants except the sender
    participants = (
        ThreadParticipant.objects.filter(thread=thread)
        .exclude(user=sender_user)
        .select_related("user")
    )

    for participant in participants:
        notify(
            recipient=participant.user,
            verb=f"New message from {sender_user.handle} in '{thread.title}'",
            target=instance,
            data={
                "url": reverse("threads:thread_detail", args=[thread.id]),
                "thread_id": thread.id,
                "message_id": instance.id,
                "sender": sender_user.handle,
            },
        )
