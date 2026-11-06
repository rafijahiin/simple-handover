from django.contrib import admin
from .models import TrainingAttendance, TrainingSession


class AttendanceInline(admin.TabularInline):
    model = TrainingAttendance
    extra = 0
    fields = ['participant_name', 'role', 'attended', 'notes']


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ['topic', 'partner', 'district', 'date', 'expected_participants', 'actual_participants']
    list_filter = ['partner', 'date']
    search_fields = ['topic', 'facilitator', 'district']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [AttendanceInline]
