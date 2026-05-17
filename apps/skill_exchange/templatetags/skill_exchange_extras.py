# apps/skill_exchange/templatetags/skill_exchange_extras.py
from django import template

register = template.Library()


@register.filter
def get_user_feedback(session, user):
    """Returns the feedback left by the given user for this session, or None."""
    if not user.is_authenticated:
        return None
    return session.feedbacks.filter(rated_by_user=user).first()
