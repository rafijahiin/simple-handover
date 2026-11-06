from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'surveys', views.BaselineSurveyViewSet, basename='baseline')
router.register(r'responses', views.BaselineResponseViewSet, basename='baseline-response')
router.register(r'verification', views.BaselineVerificationViewSet, basename='baseline-verification')
router.register(r'fsw-anomalies', views.FswAnomalyViewSet, basename='baseline-fsw-anomalies')

urlpatterns = router.urls
