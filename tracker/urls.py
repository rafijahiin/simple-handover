from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'targets', views.MonthlyTargetViewSet, basename='tracker-targets')
router.register(r'alerts', views.AlertViewSet, basename='tracker-alerts')

urlpatterns = router.urls + [
    path('forecast/',   views.ForecastView.as_view(),   name='tracker-forecast'),
    path('compliance/', views.ComplianceView.as_view(), name='tracker-compliance'),
    path('progress/',   views.ProgressView.as_view(),   name='tracker-progress'),
    path('anomalies/',  views.AnomaliesView.as_view(),  name='tracker-anomalies'),
]
