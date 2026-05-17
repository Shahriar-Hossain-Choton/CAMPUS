from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.academics.models import Course, Department
from apps.common.choices import ThreadVisibility, ThreadParticipantRole
from apps.forum.models import ForumThread
from apps.media.models import Photo
from apps.threads.models import Thread, ThreadMessage, MessageAttachment

User = get_user_model()


class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise forms.ValidationError(self.error_messages["required"])
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        return [super(MultipleFileField, self).clean(f, initial) for f in data]


class ForumThreadCreateForm(forms.Form):
    title = forms.CharField(max_length=255)
    description = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5}),
        required=True,
        help_text="Main body text for your thread.",
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(), required=True
    )
    course = forms.ModelChoiceField(queryset=Course.objects.all(), required=False)

    participants = forms.CharField(
        required=False,
        help_text="Enter comma-separated handles/student IDs, or type 'anyone' for a Public thread.",
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean_participants(self):
        data = self.cleaned_data.get("participants", "").strip()
        if not data or data.lower() == "anyone":
            return []  # Indicates public thread

        entries = [u.strip() for u in data.split(",") if u.strip()]
        users = list(
            User.objects.filter(
                Q(handle__in=entries) | Q(profile__student_id__in=entries)
            )
        )

        found_entries = {u.handle for u in users} | {
            u.profile.student_id for u in users if u.profile.student_id
        }
        missing = [entry for entry in entries if entry not in found_entries]
        if missing:
            raise ValidationError(f"Users not found: {', '.join(missing)}")

        return users

    @transaction.atomic
    def save(self, current_trimester):
        title = self.cleaned_data["title"]
        description = self.cleaned_data["description"]
        department = self.cleaned_data["department"]
        course = self.cleaned_data["course"]
        participants_list = self.cleaned_data["participants"]

        # Determine visibility based on participants input
        visibility = (
            ThreadVisibility.PUBLIC
            if not participants_list
            else ThreadVisibility.PRIVATE
        )

        # 1. Create the base Thread
        thread = Thread.objects.create(
            title=title, description=description, visibility=visibility
        )

        # 2. Add participants if private
        if visibility == ThreadVisibility.PRIVATE:
            # Add author as author/moderator
            thread.participants.create(
                user=self.user, role=ThreadParticipantRole.AUTHOR
            )
            # Add invited members
            for p_user in participants_list:
                if p_user != self.user:
                    thread.participants.create(
                        user=p_user, role=ThreadParticipantRole.MEMBER
                    )

        # 3. Create the linked ForumThread
        forum_thread = ForumThread.objects.create(
            author=self.user,
            course=course,
            department=department,
            trimester=current_trimester,
            thread=thread,
        )

        return forum_thread


class ThreadMessageForm(forms.ModelForm):
    uploaded_photos = MultipleFileField(required=False, label="Attach Photos")

    class Meta:
        model = ThreadMessage
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Add a reply..."}
            ),
        }

    def save(self, thread, sender, reply_to=None, commit=True):
        message = super().save(commit=False)
        message.thread = thread
        message.sender = sender
        message.reply_to = reply_to

        if commit:
            with transaction.atomic():
                message.save()
                photos = self.cleaned_data.get("uploaded_photos", [])
                for order, f in enumerate(photos):
                    photo_obj = Photo.objects.create(file=f, uploaded_by=sender)
                    MessageAttachment.objects.create(
                        message=message, photo=photo_obj, order=order
                    )
        return message
