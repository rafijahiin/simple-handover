from django.contrib import admin
from .models import IndicatorTarget, KoboFormMapping


@admin.register(IndicatorTarget)
class IndicatorTargetAdmin(admin.ModelAdmin):
    list_display = (
        'partner', 'objective_number', 'activity_code',
        'indicator_label', 'target_value', 'unit', 'is_active',
    )
    list_filter = ('partner', 'objective_number', 'is_active')
    search_fields = ('activity_code', 'activity_label', 'indicator_label')
    ordering = ('partner__code', 'objective_number', 'activity_code')
    list_editable = ('target_value', 'is_active')
    autocomplete_fields = ('partner', 'source_form')
    raw_id_fields = ('updated_by',)


@admin.register(KoboFormMapping)
class KoboFormMappingAdmin(admin.ModelAdmin):
    list_display = ('form_slug', 'form_label', 'partner', 'kobo_asset_uid', 'is_active')
    list_filter = ('partner', 'is_active')
    search_fields = ('form_slug', 'form_label', 'kobo_asset_uid')
    ordering = ('form_slug',)
