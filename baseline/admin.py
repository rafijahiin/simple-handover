from django.contrib import admin
from .models import BaselineSurvey


@admin.register(BaselineSurvey)
class BaselineSurveyAdmin(admin.ModelAdmin):
    list_display = ['partner', 'survey_type', 'district', 'survey_date', 'is_duplicate', 'created_at']
    list_filter = ['partner', 'survey_type', 'is_duplicate']
    search_fields = ['district', 'participant_code']
    readonly_fields = ['id', 'created_at', 'updated_at']
