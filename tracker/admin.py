from django.contrib import admin
from .models import Alert, MonthlyTarget


@admin.register(MonthlyTarget)
class MonthlyTargetAdmin(admin.ModelAdmin):
    list_display = ['partner', 'form_type', 'year', 'month', 'target']
    list_filter = ['partner', 'form_type', 'year']
    ordering = ['-year', '-month', 'partner']


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['title', 'partner', 'severity', 'alert_type', 'acknowledged', 'created_at']
    list_filter = ['severity', 'alert_type', 'acknowledged', 'partner']
    search_fields = ['title', 'message']
    readonly_fields = ['id', 'created_at']
