from typing import Optional
from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import now

from .models import Notification


def notify(
    recipient, verb: str, target: Optional[object] = None, data: Optional[dict] = None
):
    """Create a Notification for a recipient.

    recipient: User instance
    verb: short text describing the event
    target: model instance to link (optional)
    data: optional JSON-serializable dict for metadata (e.g., url)
    """
    ct = None
    obj_id = None
    if target is not None:
        ct = ContentType.objects.get_for_model(target)
        obj_id = str(getattr(target, "pk", None))

    notif = Notification.objects.create(
        recipient=recipient,
        verb=verb,
        target_content_type=ct,
        target_object_id=obj_id,
        data=data or {},
    )
    return notif
