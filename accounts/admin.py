from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .forms import UserCreationForm, UserChangeForm
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = ['email', 'full_name', 'organisation', 'role', 'is_active']
    list_filter = ['organisation', 'role', 'is_active']
    search_fields = ['email', 'full_name']
    ordering = ['organisation', 'full_name']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal', {'fields': ('full_name',)}),
        ('Organisation', {'fields': ('organisation', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('date_joined', 'last_login')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'organisation', 'role', 'password1', 'password2'),
        }),
    )
    readonly_fields = ['date_joined', 'last_login']
