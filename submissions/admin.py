from django.contrib import admin
from .models import KoboSubmission


@admin.register(KoboSubmission)
class KoboSubmissionAdmin(admin.ModelAdmin):
    list_display = ['kobo_id', 'form_type', 'partner', 'worker_name', 'district', 'status', 'submitted_at']
    list_filter = ['form_type', 'partner', 'status']
    search_fields = ['kobo_id', 'worker_name', 'district']
    readonly_fields = ['id', 'kobo_id', 'raw_data', 'received_at', 'reviewed_by', 'reviewed_at']
    ordering = ['-submitted_at']
