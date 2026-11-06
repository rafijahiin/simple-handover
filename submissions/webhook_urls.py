from django.urls import path
from . import views

urlpatterns = [
    path('', views.kobo_webhook, name='kobo-webhook'),
]
