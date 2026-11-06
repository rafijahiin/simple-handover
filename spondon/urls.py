from django.contrib import admin
from django.conf.urls.static import static
from django.urls import path, include, re_path
from django.conf import settings
from django.http import HttpResponse, Http404
from rest_framework.routers import DefaultRouter
from accounts.views import UserViewSet
from reports.views import web_report_by_token


def react_app(request, *args, **kwargs):
    index = settings.BASE_DIR / 'frontend' / 'dist' / 'index.html'
    if not index.exists():
        raise Http404('Frontend not built. Run: cd frontend && npm run build')
    return HttpResponse(index.read_text(encoding='utf-8'), content_type='text/html')


def health(request):
    return HttpResponse('ok', content_type='text/plain')


_admin_router = DefaultRouter()
_admin_router.register('users', UserViewSet, basename='admin-user')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health),
    path('api/accounts/', include('accounts.urls')),
    path('api/admin/', include(_admin_router.urls)),
    path('api/submissions/', include('submissions.urls')),
    path('api/dashboard/', include('dashboard.urls')),
    path('api/fistula/', include('fistula.urls')),
    path('api/mpdsr/', include('mpdsr.urls')),
    path('api/tracker/', include('tracker.urls')),
    path('api/reports/', include('reports.urls')),
    path('api/baseline/', include('baseline.urls')),
    path('api/training/', include('training.urls')),
    path('api/programs/', include('programs.urls')),
    path('api/indicators/', include('indicators.urls')),
    path('api/partners/',   include('partners.urls')),
    path('api/pharmacy/',   include('pharmacy.urls')),
    path('webhook/kobo/', include('submissions.webhook_urls')),
    path('webhook/programs/', include('programs.webhook_urls')),
    # Public shareable web report — token is the access control. Must precede the SPA catch-all.
    path('r/<str:token>/', web_report_by_token, name='web-report'),
    re_path(r'^.*$', react_app),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
