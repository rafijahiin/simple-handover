from django.contrib import admin
from .models import FistulaCampaign


@admin.register(FistulaCampaign)
class FistulaCampaignAdmin(admin.ModelAdmin):
    list_display = [
        'case_hash', 'partner', 'district', 'campaign_date',
        'women_screened', 'confirmed_fistula_cases', 'cases_surgery_completed',
    ]
    list_filter = ['partner', 'campaign_date']
    search_fields = ['case_hash', 'district', 'facility_name']
    readonly_fields = ['id', 'case_hash', 'submission', 'created_at', 'updated_at']
    ordering = ['-campaign_date']
