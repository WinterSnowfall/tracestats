from django.urls import path
from . import views

urlpatterns = [
    path('', views.tracestats, name='tracestats'),
    path('titles-list/', views.generate_titles_list, name='titles_list'),
    path('api-stats/', views.generate_stats, name='generate_stats'),
    path('file-upload/', views.generate_file_upload, name='generate_file_upload')
]

