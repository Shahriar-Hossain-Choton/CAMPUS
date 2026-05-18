from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST, require_GET

from .models import Notification


@login_required
@require_GET
def unread_count(request):
    count = Notification.objects.filter(
        recipient=request.user, read_at__isnull=True
    ).count()
    return JsonResponse({"count": count})


@login_required
@require_GET
def list_notifications(request):
    limit = int(request.GET.get("limit", 20))
    notifs = Notification.objects.filter(recipient=request.user).order_by(
        "-created_at"
    )[:limit]
    items = []
    for n in notifs:
        items.append(
            {
                "id": n.id,
                "verb": n.verb,
                "created_at": n.created_at.isoformat(),
                "read": bool(n.read_at),
                "data": n.data or {},
            }
        )
    return JsonResponse({"notifications": items})


@login_required
@require_POST
def mark_read(request):
    # Accepts JSON: { "id": <id> } or { "all": true }
    import json

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return HttpResponseBadRequest("invalid json")

    if payload.get("all"):
        from django.utils.timezone import now

        Notification.objects.filter(
            recipient=request.user, read_at__isnull=True
        ).update(read_at=now())
        return JsonResponse({"ok": True})

    nid = payload.get("id")
    if nid is None:
        return HttpResponseBadRequest("missing id")

    try:
        n = Notification.objects.get(id=nid, recipient=request.user)
        n.mark_read()
        return JsonResponse({"ok": True})
    except Notification.DoesNotExist:
        return HttpResponseBadRequest("not found")
