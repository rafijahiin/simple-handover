from django.urls import path
from . import views

urlpatterns = [
    path('kpis/', views.KPIView.as_view(), name='dashboard-kpis'),
    path('monthly/', views.MonthlyBreakdownView.as_view(), name='dashboard-monthly'),
    path('activity-breakdown/', views.ActivityBreakdownView.as_view(), name='dashboard-activity-breakdown'),
    path('activity/', views.ActivityFeedView.as_view(), name='dashboard-activity'),
    path('activity-feed/', views.ActivityFeedView.as_view(), name='dashboard-activity-feed'),
    path('centres/', views.CentresView.as_view(), name='dashboard-centres'),
    path('partner-summary/', views.PartnerSummaryView.as_view(), name='dashboard-partner-summary'),
    path('partner-kpis/', views.PartnerKPIsView.as_view(), name='dashboard-partner-kpis'),
    path('alerts/', views.DashboardAlertsView.as_view(), name='dashboard-alerts'),
    path('health-flags/', views.ProgrammeHealthFlagView.as_view(), name='dashboard-health-flags'),
    path('org-summary/', views.OrgSummaryView.as_view(), name='dashboard-org-summary'),
    path('programme-summary/', views.ProgrammeSummaryView.as_view(), name='dashboard-programme-summary'),
    path('map-data/', views.MapDataView.as_view(), name='dashboard-map-data'),
    path('programs-summary/', views.ProgramsSummaryView.as_view(), name='dashboard-programs-summary'),
    path('chat/', views.ChatView.as_view(), name='dashboard-chat'),
]
