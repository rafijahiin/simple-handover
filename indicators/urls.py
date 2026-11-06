from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    IndicatorProgressView,
    IndicatorRecordsView,
    IndicatorTargetViewSet,
    KoboFormMappingViewSet,
    PhdRegistryKpiView,
    SingleIndicatorProgressView,
)

router = DefaultRouter()
router.register('targets', IndicatorTargetViewSet, basename='indicator-target')
router.register('kobo-forms', KoboFormMappingViewSet, basename='kobo-form')

urlpatterns = [
    path('', include(router.urls)),
    path('phd-registry/', PhdRegistryKpiView.as_view(), name='indicator-phd-registry'),
    path('progress/', IndicatorProgressView.as_view(), name='indicator-progress'),
    path('progress/<str:code>/', SingleIndicatorProgressView.as_view(), name='indicator-progress-single'),
    path('records/', IndicatorRecordsView.as_view(), name='indicator-records'),
]
