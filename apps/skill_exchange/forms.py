from django import forms
from .models import ExchangePost
from apps.common.choices import ExchangePostStatus


class SkillExchangePostForm(forms.ModelForm):
    class Meta:
        model = ExchangePost
        fields = ["description", "skills_offered", "skills_needed"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        # Pop the user from kwargs before initializing the superclass
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        offered_skills = cleaned_data.get("skills_offered")
        needed_skills = cleaned_data.get("skills_needed")

        if offered_skills and needed_skills:
            # Convert to sets of IDs for comparison
            offered_ids = set(s.id for s in offered_skills)
            needed_ids = set(s.id for s in needed_skills)

            # Check 1: Prevent offering and requesting the same skill
            overlap = offered_ids.intersection(needed_ids)
            if overlap:
                raise forms.ValidationError(
                    "You cannot offer a skill that you are also requesting."
                )

            # Check 2: Prevent duplicate active posts by this user
            if self.user:
                active_posts = ExchangePost.objects.filter(
                    author=self.user,
                    status=ExchangePostStatus.MATCHING,
                    deleted_at__isnull=True,
                ).prefetch_related("skills_offered", "skills_needed")

                for post in active_posts:
                    existing_offered = set(
                        post.skills_offered.values_list("id", flat=True)
                    )
                    existing_needed = set(
                        post.skills_needed.values_list("id", flat=True)
                    )

                    if (
                        offered_ids == existing_offered
                        and needed_ids == existing_needed
                    ):
                        raise forms.ValidationError(
                            "You already have an active post offering and requesting this exact combination of skills."
                        )

        return cleaned_data
