from django.contrib import admin
from django.urls import path, include
from app import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('app.urls')),
    path('login/', views.login_view, name='login'),
    path('', views.login_view, name='login'),  # Establece el inicio de sesión como la URL principal
  
]

