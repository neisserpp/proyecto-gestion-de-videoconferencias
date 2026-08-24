from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.views.generic import ListView
from rest_framework import viewsets
from .serializer import *
from django.db.models import Count, Q
from .forms import LocalForm, ModeratorForm, ReserveForm, LoginForm, ApproveReserveForm 
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout, get_user_model
from .models import Reserve, Local, Moderator, UserProfile, Notification, PendingOperation
from django.utils import timezone
from django.contrib import messages
from .filters import ModeratorFilter, LocalFilter, ReserveFilter
from django.core.mail import get_connection, EmailMultiAlternatives
import smtplib
import csv
from django.core.paginator import Paginator
from django.db.models.functions import ExtractMonth
from datetime import timedelta
from calendar import month_name
from django.core.serializers import serialize
import json
from .google_calendar import (
    get_google_calendar_service,
    check_internet_connection,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    sync_events,
    sync_pending_operations,
    apply_pending_operations,
    CACHE_TIMEOUT
)
from django.core.cache import cache
from django.conf import settings
import logging
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from time import sleep
import time 
logger = logging.getLogger(__name__)
User = get_user_model()

# Funciones de utilidad
def is_admin(user):
    return user.role == 'admin'

def is_user(user):
    return user.role == 'user'

def format_google_date(date_data):
    """Formatea fechas de Google Calendar."""
    from datetime import datetime
    try:
        if 'dateTime' in date_data:
            return datetime.fromisoformat(date_data['dateTime'].rstrip('Z')).strftime("%d/%m/%Y %H:%M")
        return datetime.fromisoformat(date_data['date']).strftime("%d/%m/%Y")
    except Exception as e:
        logger.error(f"Error formateando fecha: {str(e)}")
        return "Fecha inválida"

# Vistas
def dashboard_view(request):
    if request.user.role == 'admin':
        total_moderadores = Moderator.objects.filter(disponible=True).count()
        total_locales = Local.objects.filter(disponible=True).count()
        total_reservas = Reserve.objects.count()
        horas_reservadas = sum(reserva.duration for reserva in Reserve.objects.all())
        reservaciones_recientes = Reserve.objects.all().order_by('-dateTime')[:5]
        
        reservas_por_mes = Reserve.objects.annotate(month=ExtractMonth('dateTime')).values('month').annotate(total=Count('id')).order_by('month')
        meses = [month_name[reserva['month']] for reserva in reservas_por_mes]
        total_reservas_mes = [reserva['total'] for reserva in reservas_por_mes]

        reservas_por_plataforma = Reserve.objects.values('platafom').annotate(total=Count('id')).order_by('platafom')
        plataformas = [reserva['platafom'] for reserva in reservas_por_plataforma]
        total_reservas_plataforma = [reserva['total'] for reserva in reservas_por_plataforma]

        context = {
            'total_moderadores': total_moderadores,
            'total_locales': total_locales,
            'total_reservas': total_reservas,
            'horas_reservadas': horas_reservadas,
            'reservaciones_recientes': reservaciones_recientes,
            'meses': meses,
            'total_reservas_mes': total_reservas_mes,
            'plataformas': plataformas,
            'total_reservas_plataforma': total_reservas_plataforma,
            'is_admin': True,
            'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
        }
    else:
        total_reservas = Reserve.objects.filter(user=request.user).count()
        horas_reservadas = sum(reserva.duration for reserva in Reserve.objects.filter(user=request.user))
        reservaciones_recientes = Reserve.objects.filter(user=request.user).order_by('-dateTime')[:5]

        context = {
            'total_reservas': total_reservas,
            'horas_reservadas': horas_reservadas,
            'reservaciones_recientes': reservaciones_recientes,
            'is_admin': False,
            'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
        }

    return render(request, 'app/dashboard.html', context)

#Locales
def exportar_locales_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="locales.csv"'

    writer = csv.writer(response)
    writer.writerow(['Nombre', 'Sede', 'Capacidad', 'Disponible'])

    locales = Local.objects.all()
    for local in locales:
        writer.writerow([
            local.nombre,
            local.get_sede_display(),
            local.capacidad,
            local.disponible
        ])

    return response
# Moderadores
def exportar_moderadores_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="moderadores.csv"'

    writer = csv.writer(response)
    writer.writerow(['Nombre', 'Email', 'Disponible'])

    moderadores = Moderator.objects.all()
    for moderador in moderadores:
        writer.writerow([
            moderador.nombre,
            moderador.email,
            moderador.disponible
        ])

    return response
    pass
#Reservaciones
def exportar_reservaciones_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="reservaciones.csv"'

    writer = csv.writer(response)
    writer.writerow(['Nombre', 'Motivo', 'Plataforma', 'Fecha y Hora', 'Moderador', 'Localización'])

    reservaciones = Reserve.objects.all()
    for reserva in reservaciones:
        writer.writerow([
            reserva.vcName,
            reserva.get_vcMotive_display(),
            reserva.get_platafom_display(),
            reserva.dateTime,
            reserva.idofModerator,
            reserva.local
        ])
    pass
    return response
    
def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Bienvenido, {username}!')
                return redirect('dashboard')
            else:
                messages.error(request, 'Credenciales inválidas. Inténtalo de nuevo.')
        else:
            messages.error(request, 'Por favor, corrige los errores en el formulario.')
    else:
        form = LoginForm()
    return render(request, 'app/login.html', {'form': form})

@login_required
@user_passes_test(is_admin)
def listar_locales(request):
    query = request.GET.get('q')
    locales = Local.objects.all()

    if query:
        locales = locales.filter(nombre__icontains=query)

    paginator = Paginator(locales, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'Local/listar_locales.html', {
        'page_obj': page_obj, 
        'query': query,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
@user_passes_test(is_admin)
def agregar_local(request):
    if request.method == 'POST':
        form = LocalForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Local creado exitosamente!')
            return redirect('listar_locales')
        else:
            messages.error(request, 'Por favor corrige los errores a continuación.')
    else:
        form = LocalForm()
    
    return render(request, 'Local/agregar_local.html', {
        'form': form, 
        'form_title': 'Agregar Local',
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
@user_passes_test(is_admin)
def editar_local(request, pk):
    local = get_object_or_404(Local, pk=pk)
    if request.method == 'POST':
        form = LocalForm(request.POST, instance=local)
        if form.is_valid():
            form.save()
            return redirect('listar_locales')
    else:
        form = LocalForm(instance=local)
    return render(request, 'Local/editar_local.html', {
        'form': form, 
        'local': local,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
@user_passes_test(is_admin)
def eliminar_local(request, pk):
    local = get_object_or_404(Local, pk=pk)
    if request.method == 'POST':
        local.delete()
        return redirect('listar_locales')
    return render(request, 'Local/eliminar_local.html', {
        'local': local,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
@user_passes_test(is_admin)
def listar_moderadores(request):
    query = request.GET.get('q')
    moderadores = Moderator.objects.all()

    if query:
        moderadores = moderadores.filter(nombre__icontains=query)

    paginator = Paginator(moderadores, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'Moderador/listar_moderadores.html', {
        'page_obj': page_obj, 
        'query': query,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
@user_passes_test(is_admin)
def agregar_moderador(request):
    if request.method == 'POST':
        form = ModeratorForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('listar_moderadores')
    else:
        form = ModeratorForm()
    return render(request, 'Moderador/agregar_moderador.html', {
        'form': form,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
@user_passes_test(is_admin)
def editar_moderador(request, pk):
    moderador = get_object_or_404(Moderator, pk=pk)
    if request.method == 'POST':
        form = ModeratorForm(request.POST, instance=moderador)
        if form.is_valid():
            form.save()
            return redirect('listar_moderadores')
    else:
        form = ModeratorForm(instance=moderador)
    return render(request, 'Moderador/editar_moderador.html', {
        'form': form, 
        'moderador': moderador,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
@user_passes_test(is_admin)
def eliminar_moderador(request, pk):
    moderador = get_object_or_404(Moderator, pk=pk)
    if request.method == 'POST':
        moderador.delete()
        return redirect('listar_moderadores')
    return render(request, 'Moderador/eliminar_moderador.html', {
        'moderador': moderador,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
@user_passes_test(is_admin)
def listar_reservaciones(request):
    query = request.GET.get('q')
    
    # Sincronizar eventos si hay conexión
    try:
        if check_internet_connection():
            events = sync_events(request.user)
            # Guardar en caché específica del usuario
            cache.set(f'user_{request.user.id}_events', events, CACHE_TIMEOUT)
            # Guardar también en caché global para que todos los usuarios puedan ver
            cache.set('all_synced_events', events, CACHE_TIMEOUT)
        else:
            # Obtener eventos de caché
            events = cache.get(f'user_{request.user.id}_events', [])
            if not events:
                events = cache.get('all_synced_events', [])
            
            # Aplicar operaciones pendientes a los eventos en caché
            events = apply_pending_operations(request.user, events)
    except Exception as e:
        logger.error(f"Error sincronizando eventos: {str(e)}")
        events = cache.get(f'user_{request.user.id}_events', [])
        if not events:
            events = cache.get('all_synced_events', [])
        events = apply_pending_operations(request.user, events)

    # Obtener reservas de la base de datos
    reservas_list = Reserve.objects.all().order_by('-dateTime')
    
    # Aplicar filtro de búsqueda si existe
    if query:
        reservas_list = reservas_list.filter(vcName__icontains=query)
    
    # Paginación
    paginator = Paginator(reservas_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Obtener operaciones pendientes para el contexto
    pending_creates = cache.get(f'user_{request.user.id}_pending_creates', [])
    pending_updates = cache.get(f'user_{request.user.id}_pending_updates', [])
    pending_deletes = cache.get(f'user_{request.user.id}_pending_deletes', [])
    
    return render(request, 'Reservación/listar_reservaciones.html', {
        'events': events,
        'page_obj': page_obj,
        'pending_creates': pending_creates,
        'pending_updates': pending_updates,
        'pending_deletes': pending_deletes,
        'online': check_internet_connection(),
        'query': query,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
def agregar_reserva(request):
    if request.method == 'POST':
        form = ReserveForm(request.POST, user=request.user)
        if form.is_valid():
            reserva = form.save(commit=False)
            reserva.user = request.user
            reserva.status = 'pending' if not request.user.is_superuser else 'approved'
            
            # Validación de conflicto
            conflictos = Reserve.objects.filter(
                local=reserva.local,
                dateTime__lt=reserva.dateTime + timedelta(hours=reserva.duration),
                dateTime__gte=reserva.dateTime - timedelta(hours=reserva.duration),
                status='approved'
            )
            
            if conflictos.exists():
                messages.error(request, '❌ El local ya está reservado en este horario')
                return render(request, 'Reservación/agregar_reserva.html', {'form': form})
            
            reserva.save()
            
            # Crear notificación para el administrador
            if not request.user.is_superuser:
                try:
                    # Buscar usuarios administradores
                    admins = User.objects.filter(role='admin')
                    for admin in admins:
                        Notification.objects.create(
                            user=admin,
                            reserve=reserva,
                            notification_type='system',
                            message=f"Nueva reserva creada por {request.user.username}: {reserva.vcName}"
                        )
                except Exception as e:
                    logger.error(f"Error creando notificación para admin: {str(e)}")
            
            if request.user.is_superuser and reserva.status == 'approved':
                result = create_calendar_event(reserva, request.user)
                if result['status'] == 'success':
                    reserva.google_calendar_event_id = result.get('event_id')
                    reserva.save()
                    messages.success(request, '✅ Reserva creada y sincronizada con Google Calendar')
                elif result['status'] == 'offline':
                    messages.warning(request, '⚠️ Reserva guardada localmente. Se sincronizará con conexión')
                else:
                    messages.error(request, f'❌ Error técnico: {result.get("message", "Error desconocido")}')
            else:
                messages.success(request, '✅ Reserva creada. Está pendiente de aprobación por el administrador')
            
            return redirect('mis_reservas' if not request.user.is_superuser else 'listar_reservaciones')
        
        else:
            messages.error(request, '❌ Corrige los errores en el formulario')
    else:
        form = ReserveForm(user=request.user)
    
    return render(request, 'Reservación/agregar_reserva.html', {
        'form': form,
        'online': check_internet_connection(),
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

# CORRECCIÓN: Función editar_reserva para manejar correctamente el estado de las reservas
@login_required
def editar_reserva(request, pk):
    reserva = get_object_or_404(Reserve, pk=pk)
    estado_original = reserva.status  # Guardar estado original
    
    if request.method == 'POST':
        form = ReserveForm(request.POST, instance=reserva, user=request.user)
        if form.is_valid():
            nueva_reserva = form.save(commit=False)
            
            # Solo verificar conflictos para estados aprobatorios
            if nueva_reserva.status in ['approved', 'pending']:
                conflictos = Reserve.objects.filter(
                    local=nueva_reserva.local,
                    dateTime__lt=nueva_reserva.dateTime + timedelta(hours=nueva_reserva.duration),
                    dateTime__gte=nueva_reserva.dateTime - timedelta(hours=nueva_reserva.duration),
                    status__in=['approved', 'pending']
                ).exclude(pk=reserva.pk)
                
                if conflictos.exists():
                    messages.error(request, '❌ Conflicto de horario con otra reserva aprobada')
                    return render(request, 'Reservación/editar_reserva.html', {'form': form, 'reserva': reserva})

            # Lógica para usuarios normales
            if not request.user.is_superuser:
                # CORRECCIÓN: Siempre cambiar a estado pendiente cuando un usuario edita
                if estado_original == 'approved':
                    nueva_reserva.status = 'pending'  # Cambiar a pendiente para revisión
                    nueva_reserva.status_anterior = 'approved'  # Guardar estado anterior
                    
                    # Crear notificación para el administrador
                    try:
                        admins = User.objects.filter(role='admin')
                        for admin in admins:
                            Notification.objects.create(
                                user=admin,
                                reserve=nueva_reserva,
                                notification_type='system',
                                message=f"Reserva modificada por {request.user.username}: {nueva_reserva.vcName}. Requiere revisión."
                            )
                    except Exception as e:
                        logger.error(f"Error creando notificación para admin: {str(e)}")
                    
                    messages.success(request, '🔄 Reserva actualizada. Está pendiente de aprobación por el administrador')
                else:
                    nueva_reserva.status = 'pending'
                nueva_reserva.save()
                messages.success(request, '✅ Reserva actualizada. Está pendiente de aprobación por el administrador')
                return redirect('mis_reservas')

            # Lógica para administradores
            result = update_calendar_event(nueva_reserva, reserva.user)
            
            if result['status'] == 'success':
                nueva_reserva.status = 'approved'
                messages.success(request, '✅ Cambios sincronizados con Google Calendar')
                
                # Notificar al usuario
                try:
                    Notification.objects.create(
                        user=nueva_reserva.user,
                        reserve=nueva_reserva,
                        notification_type='approval',
                        message=f"Tu reserva '{nueva_reserva.vcName}' ha sido actualizada por un administrador."
                    )
                except Exception as e:
                    logger.error(f"Error creando notificación para usuario: {str(e)}")
                
            elif result['status'] == 'offline':
                messages.warning(request, '⚠️ Cambios guardados localmente. Se sincronizarán con conexión')
                
                # Crear notificación en la base de datos
                try:
                    Notification.objects.create(
                        user=nueva_reserva.user,
                        reserve=nueva_reserva,
                        notification_type='system',
                        message=f"Tu reserva '{nueva_reserva.vcName}' ha sido actualizada. Se sincronizará cuando haya conexión."
                    )
                except Exception as e:
                    logger.error(f"Error creando notificación: {str(e)}")
            else:
                messages.error(request, f'❌ Error técnico: {result["message"]}')
                return render(request, 'Reservación/editar_reserva.html', {'form': form, 'reserva': reserva})
            
            nueva_reserva.save()
            return redirect('listar_reservaciones')
        
        else:
            messages.error(request, '❌ Corrige los errores en el formulario')
    else:
        form = ReserveForm(instance=reserva, user=request.user)
    
    return render(request, 'Reservación/editar_reserva.html', {
        'form': form, 
        'reserva': reserva, 
        'online': check_internet_connection(),
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
def eliminar_reserva(request, pk):
    reserva = get_object_or_404(Reserve, pk=pk)
    
    if request.method == 'POST':
        # Guardar información para notificaciones
        reserva_info = {
            'nombre': reserva.vcName,
            'fecha': reserva.dateTime.strftime("%d/%m/%Y %H:%M"),
            'usuario': reserva.user.username
        }
        
        result = delete_calendar_event(reserva.google_calendar_event_id, request.user)

        if result['status'] == 'success':
            messages.success(request, '✅ Evento eliminado del calendario')
        elif result['status'] == 'offline':
            messages.warning(request, '⚠️ Eliminación pendiente de sincronización')
        else:
            messages.error(request, f'❌ Error técnico: {result["message"]}')
        
        # Crear notificación antes de eliminar la reserva
        if request.user.is_superuser:
            try:
                Notification.objects.create(
                    user=reserva.user,
                    notification_type='rejection',
                    message=f"Tu reserva '{reserva_info['nombre']}' ha sido eliminada por un administrador."
                )
            except Exception as e:
                logger.error(f"Error creando notificación: {str(e)}")
        else:
            # Notificar a los administradores
            try:
                admins = User.objects.filter(role='admin')
                for admin in admins:
                    Notification.objects.create(
                        user=admin,
                        notification_type='system',
                        message=f"Reserva '{reserva_info['nombre']}' eliminada por {request.user.username}."
                    )
            except Exception as e:
                logger.error(f"Error creando notificación para admin: {str(e)}")
        
        reserva.delete()
        messages.success(request, '🗑️ Reserva eliminada del sistema local')

        return redirect('listar_reservaciones' if request.user.is_superuser else 'mis_reservas')

    context = {
        'reserva': reserva, 
        'online': check_internet_connection(),
        'is_admin': request.user.is_superuser,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    }
    return render(request, 'Reservación/eliminar_reserva.html', context)

@login_required
@user_passes_test(is_user)
def mis_reservas(request):
    # Obtener eventos del usuario actual
    user_events = []
    user_color = f"hsl({hash(request.user.email) % 360}, 70%, 60%)"  # Color único por usuario
    
    try:
        if check_internet_connection():
            sync_pending_operations(request.user)
        
        # CORRECCIÓN: Obtener todos los eventos para usuarios normales también
        events_data = get_combined_events(request.user)
        
        for event in events_data['calendar_events']:
            # Determinar si el evento pertenece al usuario actual
            is_own = event['extendedProps'].get('user_email') == request.user.email
            
            # CORRECCIÓN: Mostrar todos los eventos para usuarios normales también
            event['backgroundColor'] = user_color if is_own else '#9b59b6'  # Color diferente para eventos de otros
            event['textColor'] = '#ffffff'  # Texto blanco siempre
            event['borderColor'] = user_color if is_own else '#8e44ad'
            user_events.append(event)
        
        # Contar reservas
        total_reservas = len(user_events)
        propias_reservas = sum(1 for e in user_events if e['extendedProps']['user_email'] == request.user.email)
        
    except Exception as e:
        logger.error(f"Error cargando reservas: {str(e)}")
        user_events = []
        total_reservas = 0
        propias_reservas = 0
    
    # Obtener reservas locales
    reservas_list = Reserve.objects.filter(user=request.user).order_by('-dateTime')
    paginator = Paginator(reservas_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'Reservación/mis_reservas.html', {
        'events': json.dumps(user_events),
        'page_obj': page_obj,
        'total_reservas': total_reservas,
        'propias_reservas': propias_reservas,
        'user_color': user_color,
        'online': check_internet_connection(),
        'is_admin': request.user.role == 'admin',
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
def set_theme(request, theme_name):
    if theme_name in ['light', 'dark']:
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        profile.theme = theme_name
        profile.save()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'invalid theme'}, status=400)

@login_required
def calendario_reservaciones(request):
    # Sincronizar primero si hay conexión
    if check_internet_connection():
        sync_pending_operations(request.user)
    
    # Obtener eventos combinados
    events_data = get_combined_events(request.user)
    
    return render(request, 'Reservación/calendario.html', {
        'calendar_events': json.dumps(events_data['calendar_events']),
        'pending_count': events_data['pending_count'],
        'synced_count': events_data['synced_count'],
        'online': check_internet_connection(),
        'is_admin': request.user.role == 'admin',
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

# CORRECCIÓN: Función mejorada para obtener eventos combinados
def get_combined_events(user):
    """Obtiene eventos sincronizados y pendientes combinados"""
    try:
        # Intentar sincronizar si hay conexión
        if check_internet_connection():
            sync_pending_operations(user)
            
        # CORRECCIÓN: Siempre obtener todos los eventos para todos los usuarios
        synced_events = cache.get('all_synced_events', [])
        
        # Si no hay eventos en caché, intentar obtenerlos directamente
        if not synced_events and check_internet_connection():
            try:
                service = get_google_calendar_service()
                if service:
                    events_result = service.events().list(
                        calendarId=CALENDAR_ID,
                        maxResults=2500,
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                    synced_events = events_result.get('items', [])
                    cache.set('all_synced_events', synced_events, CACHE_TIMEOUT)
            except Exception as e:
                logger.error(f"Error obteniendo eventos del calendario: {str(e)}")
        
        # Obtener operaciones pendientes
        pending_creates = cache.get(f'user_{user.id}_pending_creates', [])
        pending_updates = cache.get(f'user_{user.id}_pending_updates', [])
        
        calendar_events = []
        
        # Procesar eventos sincronizados
        for event in synced_events:
            user_email = event.get('extendedProperties', {}).get('private', {}).get('user_email', '')
            username = ''
            if user_email:
                try:
                    user_obj = User.objects.get(email=user_email)
                    username = user_obj.username
                except User.DoesNotExist:
                    username = user_email.split('@')[0]
            
            calendar_events.append({
                'id': event.get('id'),
                'title': event.get('summary', 'Sin título'),
                'start': event.get('start', {}).get('dateTime'),
                'end': event.get('end', {}).get('dateTime'),
                'description': event.get('description', ''),
                'color': '#36a3f7',  # Color base para todos
                'extendedProps': {
                    'status': 'synced',
                    'reserva_id': event.get('extendedProperties', {}).get('private', {}).get('reserva_id', ''),
                    'user_email': user_email,
                    'is_own': user_email == user.email,
                    'username': username
                }
            })
        
        # Procesar eventos pendientes
        for op in pending_creates:
            try:
                reserva = Reserve.objects.get(id=op['reserva_id'])
                event_data = {
                    'id': op.get('temp_id', f"temp_{reserva.id}"),
                    'title': f"{reserva.vcName} (Pendiente)",
                    'start': op['event_data'].get('start', {}).get('dateTime'),
                    'end': op['event_data'].get('end', {}).get('dateTime'),
                    'description': "Reserva pendiente de sincronización",
                    'color': '#ffb878',
                    'extendedProps': {
                        'status': 'pending',
                        'reserva_id': reserva.id,
                        'temp_id': op.get('temp_id', ''),
                        'user_email': user.email,
                        'is_own': True,
                        'username': user.username
                    }
                }
                calendar_events.append(event_data)
            except Reserve.DoesNotExist:
                continue
        
        # Añadir reservas locales que no estén en Google Calendar
        local_reservas = Reserve.objects.filter(status='approved')
        for reserva in local_reservas:
            # Verificar si ya existe en los eventos del calendario
            exists = False
            for event in calendar_events:
                if event['extendedProps'].get('reserva_id') == str(reserva.id):
                    exists = True
                    break
            
            if not exists:
                # Añadir la reserva local al calendario
                calendar_events.append({
                    'id': f"local_{reserva.id}",
                    'title': reserva.vcName,
                    'start': reserva.dateTime.isoformat(),
                    'end': (reserva.dateTime + timedelta(hours=reserva.duration)).isoformat(),
                    'description': f"Reserva de {reserva.user.username}",
                    'color': '#3498db',
                    'extendedProps': {
                        'status': 'local',
                        'reserva_id': str(reserva.id),
                        'user_email': reserva.user.email,
                        'is_own': reserva.user == user,
                        'username': reserva.user.username
                    }
                })
        
        return {
            'calendar_events': calendar_events,
            'pending_count': len(pending_creates) + len(pending_updates),
            'synced_count': len(synced_events)
        }
    except Exception as e:
        logger.error(f"Error obteniendo eventos combinados: {str(e)}")
        return {
            'calendar_events': [],
            'pending_count': 0,
            'synced_count': 0
        }

@login_required
@require_POST
def update_calendar_event_ajax(request):
    try:
        data = json.loads(request.body)
        reserva = Reserve.objects.get(id=data['reserva_id'], user=request.user)
        
        # Actualizar en base de datos local
        reserva.dateTime = datetime.fromisoformat(data['start'].replace('Z', '+00:00'))
        reserva.duration = (datetime.fromisoformat(data['end'].replace('Z', '+00:00')) - 
                           datetime.fromisoformat(data['start'].replace('Z', '+00:00'))).total_seconds() / 3600
        reserva.save()
        
        # Manejar sincronización con Google Calendar
        if reserva.google_calendar_event_id:
            if not reserva.google_calendar_event_id.startswith('offline_'):
                service = get_google_calendar_service()
                if service:
                    event = service.events().update(
                        calendarId=CALENDAR_ID,
                        eventId=reserva.google_calendar_event_id,
                        body={
                            'start': {'dateTime': data['start']},
                            'end': {'dateTime': data['end']},
                            'summary': reserva.vcName,
                            'description': f"Reserva de {request.user.username}"
                        }
                    ).execute()
                    return JsonResponse({'status': 'success'})
            
            # Modo offline o fallo
            cache_key = f'user_{request.user.id}_pending_updates'
            pending = cache.get(cache_key, [])
            pending.append({
                'reserva_id': reserva.id,
                'event_data': {
                    'start': {'dateTime': data['start']},
                    'end': {'dateTime': data['end']},
                    'summary': reserva.vcName
                }
            })
            cache.set(cache_key, pending, None)
            return JsonResponse({'status': 'offline'})
        
        return JsonResponse({'status': 'error', 'message': 'Evento no sincronizado'})
    
    except Exception as e:
        logger.error(f"Error actualizando evento: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
def get_pending_count(request):
    try:
        pending_creates = cache.get(f'user_{request.user.id}_pending_creates', [])
        pending_updates = cache.get(f'user_{request.user.id}_pending_updates', [])
        synced_events = cache.get(f'user_{request.user.id}_events', [])
        
        return JsonResponse({
            'pending_count': len(pending_creates) + len(pending_updates),
            'synced_count': len(synced_events)
        })
    except Exception as e:
        logger.error(f"Error obteniendo conteo de eventos: {str(e)}")
        return JsonResponse({
            'pending_count': 0,
            'synced_count': 0
        })

@login_required
def check_connection(request):
    return JsonResponse({
        'online': check_internet_connection()
    })

def documentacion(request):
    return render(request, 'app/documentacion.html', {
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count() if request.user.is_authenticated else 0
    })

def cerrar_sesion(request):
    return render(request, 'app/cerrar_sesión.html')

def get_user_events(user):
    """Obtiene eventos sincronizados y pendientes para un usuario"""
    try:
        if check_internet_connection():
            events = sync_events(user)
            cache.set(f'user_{user.id}_events', events, CACHE_TIMEOUT)
        else:
            events = cache.get(f'user_{user.id}_events', [])
            
        pending_creates = [
            op for op in cache.get(f'user_{user.id}_pending_creates', [])
            if Reserve.objects.filter(
                id=op['reserva_id'],
                user=user
            ).exists()
        ]
        
        return {
            'synced_events': events,
            'pending_events': pending_creates
        }
    except Exception as e:
        logger.error(f"Error obteniendo eventos: {str(e)}")
        return {
            'synced_events': [],
            'pending_events': []
        }

@login_required
def check_events_update(request):
    last_sync = cache.get(f'user_{request.user.id}_last_sync')
    return JsonResponse({
        'updated': last_sync != cache.get(f'user_{request.user.id}_current_sync')
    })


def send_reservation_notification(reserva, is_approved=True, rejection_reason=None, max_retries=3):
    """
    Envía notificación por email al usuario sobre el estado de su reserva
    con reintentos automáticos y múltiples métodos de conexión.

    Args:
        reserva: Objeto Reserve
        is_approved: Bool - True si la reserva fue aprobada
        rejection_reason: Str - Motivo de rechazo (opcional)
        max_retries: Int - Intentos máximos de envío

    Returns:
        bool: True si se envió correctamente, False si falló
    """
    # Configuración base del email
    subject = f'Reserva {"Aprobada" if is_approved else "Rechazada"} - {reserva.vcName}'
    context = {
        'reserva': reserva,
        'is_approved': is_approved,
        'rejection_reason': rejection_reason,
        'fecha': reserva.dateTime.strftime("%d/%m/%Y a las %H:%M"),
        'admin_email': settings.DEFAULT_FROM_EMAIL,
        'detalles_rechazo': getattr(reserva, 'rejection_details', None)
    }

    # Renderizar plantillas
    html_message = render_to_string('app/notificaciones.html', context)
    plain_message = strip_tags(html_message)

    # Configuraciones de conexión a probar (TLS y SSL)
    connection_configs = [
        {
            'host': settings.EMAIL_HOST,
            'port': 587,
            'use_tls': True,
            'use_ssl': False,
            'desc': 'TLS'
        },
        {
            'host': settings.EMAIL_HOST,
            'port': 465,
            'use_tls': False,
            'use_ssl': True,
            'desc': 'SSL'
        }
    ]

    # Intentar enviar con cada configuración y reintentos
    for config in connection_configs:
        for attempt in range(max_retries):
            try:
                connection = get_connection(
                    host=config['host'],
                    port=config['port'],
                    username=settings.EMAIL_HOST_USER,
                    password=settings.EMAIL_HOST_PASSWORD,
                    use_tls=config['use_tls'],
                    use_ssl=config['use_ssl']
                )

                email = EmailMultiAlternatives(
                    subject=subject,
                    body=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[reserva.user.email],
                    reply_to=[settings.DEFAULT_FROM_EMAIL],
                    connection=connection
                )
                email.attach_alternative(html_message, "text/html")
                email.send()

                logger.info(f"Email enviado usando {config['desc']} (Intento {attempt + 1})")
                return True

            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"Error de autenticación con {config['desc']}: {str(e)}")
                break  # No reintentar con credenciales inválidas

            except smtplib.SMTPException as e:
                wait_time = (attempt + 1) * 2  # Espera exponencial
                logger.warning(f"Error SMTP ({config['desc']}, intento {attempt + 1}): {str(e)}. Reintentando en {wait_time}s...")
                sleep(wait_time)  # Usa la función importada
                continue

            except Exception as e:
                logger.error(f"Error inesperado con {config['desc']}: {str(e)}")
                break

    # Si todas las configuraciones fallaron
    logger.error("Todos los métodos de envío fallaron")
    return False

@login_required
@user_passes_test(is_admin)
def approve_reservation(request, pk):
    reserva = get_object_or_404(Reserve, pk=pk)
    
    if request.method == 'POST':
        form = ApproveReserveForm(request.POST, instance=reserva)
        if form.is_valid():
            reserva = form.save(commit=False)
            evento_id_original = reserva.google_calendar_event_id  # Guardar ID original
            
            if reserva.status == 'approved':
                # Manejar actualización o creación
                if reserva.google_calendar_event_id and not reserva.google_calendar_event_id.startswith('offline'):
                    result = update_calendar_event(reserva, reserva.user)
                else:
                    result = create_calendar_event(reserva, reserva.user)
                
                if result['status'] == 'success':
                    messages.success(request, '✅ Reserva sincronizada con Google Calendar')
                    
                    # Enviar notificación al usuario
                    try:
                        send_reservation_notification(reserva, is_approved=True)
                        
                        # Crear notificación en la base de datos
                        Notification.objects.create(
                            user=reserva.user,
                            reserve=reserva,
                            notification_type='approval',
                            message=f"Tu reserva '{reserva.vcName}' ha sido aprobada."
                        )
                    except Exception as e:
                        logger.error(f"Error enviando notificación: {str(e)}")
                        messages.warning(request, '⚠️ No se pudo enviar la notificación por email')
                    
                elif result['status'] == 'offline':
                    messages.warning(request, '⚠️ Reserva aprobada localmente. Se sincronizará cuando haya conexión')
                    
                    # Crear notificación en la base de datos
                    try:
                        Notification.objects.create(
                            user=reserva.user,
                            reserve=reserva,
                            notification_type='approval',
                            message=f"Tu reserva '{reserva.vcName}' ha sido aprobada. Se sincronizará cuando haya conexión."
                        )
                    except Exception as e:
                        logger.error(f"Error creando notificación: {str(e)}")
                
                else:
                    messages.error(request, f'❌ Error: {result.get("message")}')
                    return render(request, 'Reservación/aprobar_reserva.html', {'form': form, 'reserva': reserva})
                
                # Actualizar cachés
                cache.delete(f'user_{reserva.user.id}_events')
                cache.delete('all_synced_events')
                
            elif reserva.status == 'rejected':
                # Eliminar evento solo si fue previamente aprobado
                if evento_id_original and not evento_id_original.startswith('offline'):
                    delete_calendar_event(evento_id_original, reserva.user)
                
                # Restaurar estado original si estaba en pending_update
                if reserva.status_anterior == 'approved':
                    reserva.status = 'rejected'  # CORRECCIÓN: Mantener como rechazado
                    reserva.google_calendar_event_id = None  # Eliminar ID de Google Calendar
                else:
                    reserva.google_calendar_event_id = None
                
                messages.success(request, '🗑️ Reserva rechazada')
                
                # Enviar notificación al usuario
                try:
                    rejection_details = form.cleaned_data.get('rejection_details', 'No especificado')
                    send_reservation_notification(
                        reserva, 
                        is_approved=False, 
                        rejection_reason=form.cleaned_data.get('rejection_reason', 'other')
                    )
                    
                    # Crear notificación en la base de datos
                    Notification.objects.create(
                        user=reserva.user,
                        reserve=reserva,
                        notification_type='rejection',
                        message=f"Tu reserva '{reserva.vcName}' ha sido rechazada. Motivo: {rejection_details}"
                    )
                except Exception as e:
                    logger.error(f"Error enviando notificación: {str(e)}")
            
            reserva.save()
            return redirect('listar_reservaciones')
    
    form = ApproveReserveForm(instance=reserva)
    return render(request, 'Reservación/aprobar_reserva.html', {
        'form': form, 
        'reserva': reserva,
        'online': check_internet_connection(),
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })

@login_required
def notifications_view(request):
    notifications = {
        'all': Notification.objects.filter(user=request.user).order_by('-created_at'),
        'unread': Notification.objects.filter(user=request.user, is_read=False),
    }
    context = {
        'notifications': notifications,
        'unread_count': notifications['unread'].count(),
        'online': check_internet_connection()
    }
    return render(request, 'app/notificaciones.html', context)

@login_required
@require_POST
def mark_as_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'status': 'success'})  

def base_context(request):
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        return {'unread_count': unread_count}
    return {}

@login_required
def check_notifications(request):
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(
            user=request.user, 
            is_read=False
        ).count()
        return JsonResponse({'unread_count': unread_count})
    return JsonResponse({'unread_count': 0})

@login_required
def delete_notification(request, notification_id):
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.delete()
        return JsonResponse({'status': 'success'})
    except Notification.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Notificación no encontrada'}, status=404)

# Función para verificar conexión a internet
@login_required
def check_connection_view(request):
    """Vista para verificar el estado de la conexión a internet"""
    is_online = check_internet_connection()
    
    # Obtener el número de operaciones pendientes si está offline
    pending_count = 0
    if not is_online and request.user.is_authenticated:
        pending_creates = cache.get(f'user_{request.user.id}_pending_creates', [])
        pending_updates = cache.get(f'user_{request.user.id}_pending_updates', [])
        pending_deletes = cache.get(f'user_{request.user.id}_pending_deletes', [])
        pending_count = len(pending_creates) + len(pending_updates) + len(pending_deletes)
    
    return JsonResponse({
        'online': is_online,
        'pending_count': pending_count
    })