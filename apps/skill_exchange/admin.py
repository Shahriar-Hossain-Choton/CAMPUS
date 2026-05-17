from django.contrib import admin
from .models import (
    ExchangeMatch,
    ExchangePost,
    ExchangeSession,
    # MatchDecision,
    SessionFeedback,
    # SessionEndRequest,
    Skill,
    UserSkill,
)

admin.site.register(Skill)
admin.site.register(ExchangePost)
admin.site.register(UserSkill)
admin.site.register(ExchangeMatch)
admin.site.register(ExchangeSession)
admin.site.register(SessionFeedback)
# admin.site.register(MatchDecision)
# admin.site.register(SessionEndRequest)
