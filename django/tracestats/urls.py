from django.urls import path
from . import views

urlpatterns = [
    path('', views.tracestats, name='tracestats'),
    path('file-upload/', views.generate_file_upload, name='generate_file_upload'),
]

