from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'cases', views.MPDSRCaseViewSet, basename='mpdsr')

urlpatterns = router.urls + [
    path('aggregates/', views.mpdsr_aggregates, name='mpdsr-aggregates'),
    path('action-aggregates/', views.mpdsr_action_aggregates, name='mpdsr-action-aggregates'),
    path('mnm/aggregates/', views.mnm_aggregates, name='mnm-aggregates'),
    path('safe-surgery/', views.safe_surgery, name='safe-surgery'),
    path('reconciliation/', views.ciprb_reconciliation, name='ciprb-reconciliation'),
]
