from django.contrib import admin
from .models import Partner


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'name_bangla', 'color_hex', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    ordering = ('code',)
