from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('cases', views.FistulaCampaignViewSet, basename='fistula')
router.register('corner-cases', views.FistulaCornerCaseViewSet, basename='fistula-corner')
router.register('campaign-visits', views.FistulaCampaignVisitViewSet, basename='fistula-campaign-visit')

urlpatterns = [
    path('aggregates/', views.fistula_aggregates, name='fistula-aggregates'),
    path('', include(router.urls)),
]
