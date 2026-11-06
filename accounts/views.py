from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from .models import User
from .permissions import IsDeveloperOnly
from .serializers import (
    AdminUserSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    UserCreateSerializer,
    UserSerializer,
)


class CSRFView(APIView):
    """Called by the frontend on mount to obtain the CSRF cookie."""
    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({'detail': 'CSRF cookie set.'})


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        login(request, user)
        # 2FA was removed — always return the user; the frontend no longer
        # branches on requires_2fa. The key is retained for one release of
        # backwards-compatibility with cached frontend builds.
        return Response({'requires_2fa': False, 'user': UserSerializer(user).data})


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response({'detail': 'Logged out.'})


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class PasswordChangeView(APIView):
    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        update_session_auth_hash(request, request.user)
        return Response({'detail': 'Password changed.'})


class UserViewSet(ModelViewSet):
    """User management — DEVELOPER only.

    Per IDMS handoff (audit FIX 1.4): supervisors retain all other access
    but cannot manage users. Only the developer (Rafi) can create / modify
    / deactivate user accounts."""
    queryset = User.objects.all().order_by('organisation', 'full_name')
    permission_classes = [IsDeveloperOnly]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return AdminUserSerializer

    def create(self, request, *args, **kwargs):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        data = request.data

        first = data.get('first_name', '')
        last = data.get('last_name', '')
        if first or last:
            instance.full_name = f'{first} {last}'.strip() or instance.full_name

        for field in ('email', 'organisation', 'role', 'is_active'):
            if field in data:
                setattr(instance, field, data[field])

        password = data.get('password', '')
        if password:
            try:
                validate_password(password, instance)
            except DjangoValidationError as e:
                return Response(
                    {'password': list(e.messages)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            instance.set_password(password)

        instance.save()
        return Response(AdminUserSerializer(instance).data)
