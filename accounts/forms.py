from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm, UserChangeForm as BaseUserChangeForm
from .models import User


class UserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ('email', 'full_name', 'organisation', 'role')


class UserChangeForm(BaseUserChangeForm):
    class Meta(BaseUserChangeForm.Meta):
        model = User
        fields = (
            'email', 'full_name', 'organisation', 'role',
            'is_active', 'is_staff', 'is_superuser',
            'groups', 'user_permissions',
            'last_login', 'date_joined',
            'password',
        )
