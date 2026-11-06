from django.contrib import admin
from .models import MPDSRCase


@admin.register(MPDSRCase)
class MPDSRCaseAdmin(admin.ModelAdmin):
    list_display = ['case_hash', 'partner', 'death_type', 'district', 'status', 'date_of_death', 'created_at']
    list_filter = ['partner', 'death_type', 'status']
    search_fields = ['case_hash', 'district', 'facility_name', 'cause_of_death']
    readonly_fields = ['id', 'case_hash', 'created_at', 'updated_at']
    ordering = ['-date_of_death']
