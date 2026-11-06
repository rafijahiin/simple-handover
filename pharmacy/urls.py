from rest_framework.routers import DefaultRouter

from .views import PrescriptionRecordViewSet

router = DefaultRouter()
router.register('prescriptions', PrescriptionRecordViewSet, basename='prescription')

urlpatterns = router.urls
