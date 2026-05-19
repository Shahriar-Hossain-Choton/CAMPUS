from django.contrib import admin
from django.utils.html import format_html
from .models import (
    RidePost, RideGroup, RideGroupMember
)

@admin.register(RidePost)
class RidePostAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'starting_location', 'destination_location',
        'transport_method', 'departure_time', 'status', 'created_at'
    ]
    list_filter = ['status', 'transport_method', 'direction', 'created_at', 'deleted_at']
    search_fields = ['user__email', 'starting_location', 'destination_location']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at', 'max_capacity']
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('user', 'status')
        }),
        ('Location & Direction', {
            'fields': ('starting_location', 'destination_location', 'direction')
        }),
        ('Transport & Time', {
            'fields': (
                'transport_method', 'max_capacity', 'departure_time',
                'expires_at'
            )
        }),
        ('Options', {
            'fields': ('notes',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'deleted_at'),
            'classes': ('collapse',)
        }),
    )

class RideGroupMemberInline(admin.TabularInline):
    model = RideGroupMember
    extra = 0
    readonly_fields = ['joined_at', 'updated_at']
    fields = ['user', 'is_initiator', 'status', 'joined_at']


@admin.register(RideGroup)
class RideGroupAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'ride_post', 'status', 'current_occupancy_display',
        'is_full_display', 'created_at'
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['ride_post__user__email']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [RideGroupMemberInline]
    
    fieldsets = (
        ('Ride Info', {
            'fields': ('ride_post', 'thread', 'status')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def current_occupancy_display(self, obj):
        return f"{obj.current_occupancy}/{obj.max_capacity}"
    current_occupancy_display.short_description = "Occupancy"
    
    def is_full_display(self, obj):
        status = "FULL" if obj.is_full else "AVAILABLE"
        color = "red" if obj.is_full else "green"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, status
        )
    is_full_display.short_description = "Status"


@admin.register(RideGroupMember)
class RideGroupMemberAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'group', 'is_initiator_display', 'status', 'joined_at'
    ]
    list_filter = ['status', 'is_initiator', 'joined_at']
    search_fields = ['user__email', 'group__ride_post__user__email']
    readonly_fields = ['joined_at', 'updated_at']
    
    fieldsets = (
        ('Member Info', {
            'fields': ('group', 'user')
        }),
        ('Role', {
            'fields': ('is_initiator', 'status')
        }),
        ('Metadata', {
            'fields': ('joined_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def is_initiator_display(self, obj):
        return "YES" if obj.is_initiator else "NO"
    is_initiator_display.short_description = "Initiator"




