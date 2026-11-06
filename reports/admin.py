from django.contrib import admin
from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'report_type', 'format', 'partner', 'year', 'month', 'created_at']
    list_filter = ['report_type', 'format', 'partner']
    readonly_fields = ['id', 'created_at', 'generated_by']
