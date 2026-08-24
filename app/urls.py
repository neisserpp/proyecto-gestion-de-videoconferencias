from django.urls import path , include
from django.contrib import admin
from django.views.generic import TemplateView
from rest_framework import routers
from rest_framework.documentation import include_docs_urls
from app import views
from .views import set_theme
from .views import mis_reservas
from .views import (calendario_reservaciones, update_calendar_event_ajax, get_pending_count,check_connection,
    listar_reservaciones, exportar_reservaciones_csv,
    listar_locales, exportar_locales_csv,
    listar_moderadores, exportar_moderadores_csv
)
 
                   

urlpatterns = [
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('login/', views.login_view, name="login"),
    path('docs/', include_docs_urls(title = "Reserva Api")), 
    path('calendario/', views.calendario_reservaciones, name='calendario_reservaciones'),
    path('api/update-event/', update_calendar_event_ajax, name='update_calendar_event'),
    path('api/pending-count/', get_pending_count, name='get_pending_count'),
    path('api/check-connection/', check_connection, name='check_connection'),
    path('api/check-events-update', views.check_events_update, name='check_events_update'),
    path('api/pending-count/', get_pending_count, name='get_pending_count'),
    path('api/check-connection/', check_connection, name='check_connection'),
    path('set-theme/<str:theme_name>/', set_theme, name='set_theme'),
    path('notificaciones/', views.notifications_view, name='notificaciones'),
    path('notificaciones/marcar-leida/<int:pk>/', views.mark_as_read, name='mark_as_read'),
    path('check-notifications/', views.check_notifications, name='check_notifications'),
    path('notifications/delete/<int:notification_id>/', views.delete_notification, name='delete_notification'),
    path('notificaciones/marcar-leida/<int:notification_id>/', views.mark_as_read, name='mark_as_read'),
    path('check-connection/', views.check_connection_view, name='check_connection'),
    path('get-pending-count/', views.get_pending_count, name='get_pending_count'),
#Locales  
    path('locales/', views.listar_locales, name='listar_locales'),
    path('locales/agregar/', views.agregar_local, name='agregar_local'),
    path('locales/editar/<int:pk>/', views.editar_local, name='editar_local'),
    path('locales/eliminar/<int:pk>/', views.eliminar_local, name='eliminar_local'),
    path('exportar-locales-csv/', exportar_locales_csv, name='exportar_locales_csv'),
#Moderadores
    path('moderadores/', views.listar_moderadores, name='listar_moderadores'),
    path('moderadores/agregar/', views.agregar_moderador, name='agregar_moderador'),
    path('moderadores/editar/<int:pk>/', views.editar_moderador, name='editar_moderador'),
    path('moderadores/eliminar/<int:pk>/', views.eliminar_moderador, name='eliminar_moderador'),
    path('exportar-moderadores-csv/', exportar_moderadores_csv, name='exportar_moderadores_csv'),
#Reservaciones
    path('reservaciones/', views.listar_reservaciones, name='listar_reservaciones'),
    path('reservaciones/agregar/', views.agregar_reserva, name='agregar_reserva'),
    path('reservaciones/editar/<int:pk>/', views.editar_reserva, name='editar_reserva'),
    path('reservaciones/eliminar/<int:pk>/', views.eliminar_reserva, name='eliminar_reserva'),
    path('exportar-reservaciones-csv/', exportar_reservaciones_csv, name='exportar_reservaciones_csv'),
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),
    path('reservaciones/aprobar/<int:pk>/', views.approve_reservation, name='aprobar_reserva'),

#Documentación y Cerrar Sesión   
    path('documentacion/', views.documentacion, name='documentacion'),
    path('cerrar_sesion/', views.cerrar_sesion, name='cerrar_sesion'),
]