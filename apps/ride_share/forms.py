# apps/ride_share/forms.py
from django import forms
from django.utils import timezone
from datetime import timedelta
from .models import RidePost, RideDirection


class RidePostForm(forms.ModelForm):
    """Form for creating/editing a ride post"""
    
    direction = forms.ChoiceField(
        choices=RideDirection.choices,
        widget=forms.RadioSelect,
        label="Direction",
        help_text="Are you going to university or home?"
    )
    
    class Meta:
        model = RidePost
        fields = [
            'starting_location',
            'destination_location',
            'direction',
            'transport_method',
            'departure_time',
            'notes',
        ]
        widgets = {
            'starting_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Badda AAMRA Gate',
            }),
            'destination_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Dhanmondi Lake Park',
            }),
            'transport_method': forms.Select(attrs={
                'class': 'form-control',
            }),
            'departure_time': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Any notes for potential riders...',
            }),
        }
        labels = {
            'starting_location': 'Starting Location',
            'destination_location': 'Destination Location',
            'transport_method': 'Transport Type',
            'departure_time': 'When do you leave?',
            'notes': 'Additional Notes',
        }

    def clean(self):
        cleaned_data = super().clean()
        departure_time = cleaned_data.get('departure_time')
        expires_at = cleaned_data.get('expires_at')
        
        if departure_time and expires_at:
            if expires_at < departure_time:
                raise forms.ValidationError(
                    "Post close time cannot be before departure time."
                )
            
            now = timezone.now()
            if departure_time < now:
                raise forms.ValidationError(
                    "Departure time must be in the future."
                )
            
            if expires_at < now:
                raise forms.ValidationError(
                    "Post close time must be in the future."
                )
        
        return cleaned_data


class ApproachRideForm(forms.Form):
    """Form for approaching a ride (without creating a post)"""
    
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Tell the rider why you\'d like to join...',
        }),
        label='Message',
        help_text='Optional message to the ride organizer'
    )
    
    party_size = forms.IntegerField(
        min_value=1,
        max_value=4,
        initial=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'type': 'number',
        }),
        label='Number of Passengers (including you)',
    )
