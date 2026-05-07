from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.hub_finance, name='hub'),
]
