from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'sessions', views.TrainingSessionViewSet, basename='training-sessions')

urlpatterns = router.urls + [
    path('summary-pdf/', views.TrainingSummaryPDFView.as_view(), name='training-summary-pdf'),
]
