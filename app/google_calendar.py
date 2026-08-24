import os
import json
import logging
from datetime import datetime, timedelta
import time
import requests
import socket
import random
import string

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from django.contrib.auth import get_user_model 
from django.core.cache import cache
from django.conf import settings
from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth import get_user_model
from django.urls import reverse

logger = logging.getLogger(__name__)
SCOPES = ['https://www.googleapis.com/auth/calendar']
CACHE_TIMEOUT = 60 * 60 * 24 * 3  # 3 días
CALENDAR_ID = "neffex.pp@gmail.com"

# Configurar variables globales
try:
    Reserve = apps.get_model('app', 'Reserve')
    User = get_user_model()
except:
    logger.warning("No se pudieron cargar los modelos - probablemente durante la inicialización")

# Configurar proxy y desactivar advertencias SSL
os.environ['NO_PROXY'] = 'google.com,googleapis.com'
requests.packages.urllib3.disable_warnings()

def check_internet_connection():
    """Verifica conexión a internet con múltiples métodos y caché temporal."""
    # Verificar si ya tenemos un resultado en caché (válido por 30 segundos)
    cache_key = 'internet_connection_status'
    cached_status = cache.get(cache_key)
    
    if cached_status is not None:
        return cached_status
    
    # Lista de dominios y IPs a probar
    test_targets = [
        {"url": "https://www.google.com", "timeout": 3},
        {"url": "https://www.cloudflare.com", "timeout": 3},
        {"url": "https://1.1.1.1", "timeout": 2},
        {"ip": "8.8.8.8", "port": 53, "timeout": 2},
        {"ip": "1.1.1.1", "port": 53, "timeout": 2}
    ]
    
    # Intentar conexiones HTTP
    for target in test_targets:
        if "url" in target:
            try:
                response = requests.head(
                    target["url"], 
                    timeout=target["timeout"],
                    verify=False
                )
                if response.status_code < 500:  # Aceptar incluso errores 4xx
                    cache.set(cache_key, True, 30)  # Cachear por 30 segundos
                    return True
            except:
                continue
        elif "ip" in target:
            try:
                # Intento con socket directo
                socket.create_connection(
                    (target["ip"], target["port"]), 
                    timeout=target["timeout"]
                )
                cache.set(cache_key, True, 30)
                return True
            except:
                continue
    
    # Si todos los intentos fallan, no hay conexión
    logger.warning("Sin conexión a internet")
    cache.set(cache_key, False, 30)
    return False

def get_google_calendar_service(offline=False):
    """Obtiene el servicio con manejo mejorado de caché offline"""
    try:
        # Verificar conexión solo si no se solicitó explícitamente modo offline
        if not offline and not check_internet_connection():
            offline = True
            logger.info("Usando modo offline para el servicio de calendario")
        
        # Si estamos en modo offline, intentar usar servicio en caché
        if offline:
            cached_service = cache.get('cached_calendar_service')
            if cached_service:
                return cached_service
            logger.warning("Servicio no disponible en caché y sin conexión")
            return None
        
        # Intentar obtener credenciales
        creds = None
        token_path = os.path.join(settings.BASE_DIR, 'token.json')
        
        if os.path.exists(token_path):
            try:
                with open(token_path, 'r') as token:
                    creds = Credentials.from_authorized_user_info(json.load(token), SCOPES)
            except Exception as e:
                logger.error(f"Error leyendo token.json: {str(e)}")
                # Si hay error al leer el token, intentar con caché
                cached_service = cache.get('cached_calendar_service')
                if cached_service:
                    return cached_service
        
        # Verificar validez de credenciales
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Error refrescando token: {str(e)}")
                    # Si hay error al refrescar, intentar con caché
                    cached_service = cache.get('cached_calendar_service')
                    if cached_service:
                        return cached_service
                    return None
            else:
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        os.path.join(settings.BASE_DIR, 'credentials.json'),
                        SCOPES,
                        redirect_uri='urn:ietf:wg:oauth:2.0:oob'
                    )
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Error en flujo de autenticación: {str(e)}")
                    # Si hay error en autenticación, intentar con caché
                    cached_service = cache.get('cached_calendar_service')
                    if cached_service:
                        return cached_service
                    return None

            # Guardar token actualizado
            try:
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
            except Exception as e:
                logger.error(f"Error guardando token: {str(e)}")
        
        # Construir servicio
        try:
            service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
            # Guardar en caché para uso offline
            cache.set('cached_calendar_service', service, CACHE_TIMEOUT)
            
            # Actualizar caché de eventos al obtener servicio
            try:
                events_result = service.events().list(
                    calendarId=CALENDAR_ID,
                    maxResults=1000,
                    singleEvents=True
                ).execute()
                all_events = events_result.get('items', [])
                cache.set('all_synced_events', all_events, CACHE_TIMEOUT)
                
                # Actualizar cachés por usuario
                for event in all_events:
                    user_email = event.get('extendedProperties', {}).get('private', {}).get('user_email')
                    if user_email:
                        try:
                            user = User.objects.get(email=user_email)
                            user_events = [e for e in all_events if 
                                        e.get('extendedProperties', {}).get('private', {}).get('user_email') == user_email]
                            cache.set(f'user_{user.id}_events', user_events, CACHE_TIMEOUT)
                        except User.DoesNotExist:
                            continue
            except Exception as e:
                logger.error(f"Error actualizando caché de eventos: {str(e)}")
            
            return service
        except Exception as e:
            logger.error(f"Error construyendo servicio: {str(e)}")
            # Intentar con caché en caso de error
            cached_service = cache.get('cached_calendar_service')
            if cached_service:
                return cached_service
            return None
    
    except Exception as e:
        logger.error(f"Error obteniendo servicio: {str(e)}")
        # Último intento con caché
        cached_service = cache.get('cached_calendar_service')
        if cached_service:
            return cached_service
        return None

def sync_events(user):
    """Sincroniza eventos con manejo mejorado de caché offline"""
    logger.info(f"Sincronizando eventos para {user.email} ({'online' if check_internet_connection() else 'offline'})")
    
    try:
        # Obtener servicio (puede ser None si estamos offline y no hay caché)
        service = get_google_calendar_service()
        online_events = []
        
        if service:  # Modo online
            try:
                if user.role == 'admin':
                    events_result = service.events().list(
                        calendarId=CALENDAR_ID,
                        maxResults=2500,
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                    online_events = events_result.get('items', [])
                    cache.set('all_synced_events', online_events, CACHE_TIMEOUT)
                else:
                    events_result = service.events().list(
                        calendarId=CALENDAR_ID,
                        privateExtendedProperty=f"user_email={user.email}",
                        maxResults=2500,
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                    online_events = events_result.get('items', [])
                
                # Guardar en caché específica del usuario
                cache.set(f'user_{user.id}_events', online_events, CACHE_TIMEOUT)
                cache.set(f'user_{user.id}_last_sync', datetime.now().isoformat(), CACHE_TIMEOUT)
                
                # Procesar operaciones pendientes
                clean_pending_operations(user, online_events)
                return apply_pending_operations(user, online_events)
            except Exception as e:
                logger.error(f"Error sincronizando eventos: {str(e)}")
                # Caer al modo offline
                pass
            
        # Modo offline
        # Obtener de caché con fallback a lista vacía
        if user.role == 'admin':
            cached_events = cache.get('all_synced_events', [])
        else:
            cached_events = cache.get(f'user_{user.id}_events', [])
        
        return apply_pending_operations(user, cached_events)
    
    except Exception as e:
        logger.error(f"Error en sync_events: {str(e)}")
        # Siempre retornar algo, incluso si es una lista vacía
        if user.role == 'admin':
            return apply_pending_operations(user, cache.get('all_synced_events', []))
        else:
            return apply_pending_operations(user, cache.get(f'user_{user.id}_events', []))

def apply_pending_operations(user, base_events):
    """Aplica operaciones pendientes a los eventos base"""
    try:
        # Convertir a diccionario para facilitar operaciones
        events_dict = {e.get('id', f"unknown_{i}"): e for i, e in enumerate(base_events)}
        
        # Aplicar eliminaciones pendientes
        pending_deletes = cache.get(f'user_{user.id}_pending_deletes', [])
        for event_id in pending_deletes:
            if event_id in events_dict:
                del events_dict[event_id]
        
        # Aplicar actualizaciones pendientes
        pending_updates = cache.get(f'user_{user.id}_pending_updates', [])
        for op in pending_updates:
            try:
                reserva_id = op.get('reserva_id')
                if not reserva_id:
                    continue
                    
                # Intentar obtener la reserva
                try:
                    reserva = Reserve.objects.get(id=reserva_id)
                    event_id = op.get('event_id', reserva.google_calendar_event_id)
                    
                    # Si el evento existe, actualizarlo
                    if event_id in events_dict:
                        for key, value in op.get('event_data', {}).items():
                            events_dict[event_id][key] = value
                except Reserve.DoesNotExist:
                    continue
            except Exception as e:
                logger.error(f"Error procesando actualización: {str(e)}")
                continue
        
        # Aplicar creaciones pendientes
        pending_creates = cache.get(f'user_{user.id}_pending_creates', [])
        for op in pending_creates:
            try:
                reserva_id = op.get('reserva_id')
                if not reserva_id:
                    continue
                    
                # Verificar si la reserva existe
                try:
                    reserva = Reserve.objects.get(id=reserva_id)
                    temp_id = op.get('temp_id', f"offline_{reserva.id}_{int(time.time())}")
                    
                    # Crear evento temporal
                    temp_event = {
                        'id': temp_id,
                        'summary': op['event_data'].get('summary', reserva.vcName),
                        'description': op['event_data'].get('description', f"Reserva pendiente de {user.username}"),
                        'start': op['event_data'].get('start', {
                            'dateTime': reserva.dateTime.isoformat(),
                            'timeZone': 'UTC'
                        }),
                        'end': op['event_data'].get('end', {
                            'dateTime': (reserva.dateTime + timedelta(hours=reserva.duration)).isoformat(),
                            'timeZone': 'UTC'
                        }),
                        'extendedProperties': {
                            'private': {
                                'status': 'pending_create',
                                'reserva_id': str(reserva.id),
                                'user_email': user.email
                            }
                        },
                        'status': 'tentative'  # Marcar como tentativo hasta sincronización
                    }
                    events_dict[temp_id] = temp_event
                except Reserve.DoesNotExist:
                    continue
            except Exception as e:
                logger.error(f"Error procesando creación: {str(e)}")
                continue
        
        # Convertir de vuelta a lista y ordenar por fecha
        result_events = list(events_dict.values())
        
        # Ordenar eventos por fecha (con manejo de errores)
        def get_event_datetime(event):
            try:
                start = event.get('start', {})
                if 'dateTime' in start:
                    return start['dateTime']
                elif 'date' in start:
                    return start['date']
                return "0000-00-00"  # Valor por defecto
            except:
                return "0000-00-00"  # En caso de error
        
        result_events.sort(key=get_event_datetime)
        return result_events
        
    except Exception as e:
        logger.error(f"Error en apply_pending_operations: {str(e)}")
        return base_events  # Devolver eventos originales en caso de error

def clean_pending_operations(user, online_events):
    """Limpia operaciones pendientes ya sincronizadas"""
    try:
        # Obtener todos los IDs de eventos existentes
        online_ids = {e.get('id', '') for e in online_events}
        
        # Limpiar creaciones pendientes
        pending_creates = cache.get(f'user_{user.id}_pending_creates', [])
        remaining_creates = []
        
        for op in pending_creates:
            try:
                reserva_id = op.get('reserva_id')
                if not reserva_id:
                    continue
                    
                # Verificar si la reserva existe
                try:
                    reserva = Reserve.objects.get(id=reserva_id)
                    
                    # Si tiene ID de Google (no offline) y existe en el calendario
                    if (reserva.google_calendar_event_id and 
                        not reserva.google_calendar_event_id.startswith(('offline_', 'temp_')) and
                        reserva.google_calendar_event_id in online_ids):
                        continue  # Ya está sincronizado, no lo incluimos
                    
                    # Si no, mantenerlo en la lista
                    remaining_creates.append(op)
                except Reserve.DoesNotExist:
                    # La reserva ya no existe, no la incluimos
                    continue
            except Exception as e:
                logger.error(f"Error limpiando creación: {str(e)}")
                # En caso de error, mantener la operación
                remaining_creates.append(op)
        
        # Actualizar caché solo si hay cambios
        if len(remaining_creates) != len(pending_creates):
            cache.set(f'user_{user.id}_pending_creates', remaining_creates, None)
        
        # Limpiar actualizaciones pendientes
        pending_updates = cache.get(f'user_{user.id}_pending_updates', [])
        remaining_updates = []
        
        for op in pending_updates:
            try:
                reserva_id = op.get('reserva_id')
                if not reserva_id:
                    continue
                    
                # Verificar si la reserva existe
                try:
                    reserva = Reserve.objects.get(id=reserva_id)
                    
                    # Si tiene ID de Google y existe en el calendario
                    if (reserva.google_calendar_event_id and 
                        not reserva.google_calendar_event_id.startswith(('offline_', 'temp_')) and
                        reserva.google_calendar_event_id in online_ids):
                        # Verificar si los datos ya están actualizados
                        # (simplificado - en una implementación real habría que comparar los datos)
                        continue  # Asumimos que ya está sincronizado
                    
                    # Si no, mantenerlo en la lista
                    remaining_updates.append(op)
                except Reserve.DoesNotExist:
                    # La reserva ya no existe, no la incluimos
                    continue
            except Exception as e:
                logger.error(f"Error limpiando actualización: {str(e)}")
                # En caso de error, mantener la operación
                remaining_updates.append(op)
        
        # Actualizar caché solo si hay cambios
        if len(remaining_updates) != len(pending_updates):
            cache.set(f'user_{user.id}_pending_updates', remaining_updates, None)
        
        # Limpiar eliminaciones pendientes
        pending_deletes = cache.get(f'user_{user.id}_pending_deletes', [])
        remaining_deletes = [eid for eid in pending_deletes if eid in online_ids]
        
        # Actualizar caché solo si hay cambios
        if len(remaining_deletes) != len(pending_deletes):
            cache.set(f'user_{user.id}_pending_deletes', remaining_deletes, None)
    
    except Exception as e:
        logger.error(f"Error en clean_pending_operations: {str(e)}")

def generate_temp_id():
    """Genera un ID temporal único para eventos offline"""
    timestamp = int(time.time())
    random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    return f"offline_{timestamp}_{random_str}"

def create_calendar_event(reserva, user):
    """Crea un evento en Google Calendar con mejor manejo de errores"""
    if reserva.status != 'approved':
        return {'status': 'pending', 'message': 'Esperando aprobación'}
    
    # Preparar datos del evento
    event_data = {
        'summary': reserva.vcName,
        'description': f"Reserva de {user.username}\nMotivo: {reserva.get_vcMotive_display()}\nObservaciones: {reserva.observations}",
        'start': {'dateTime': reserva.dateTime.isoformat(), 'timeZone': 'UTC'},
        'end': {'dateTime': (reserva.dateTime + timedelta(hours=reserva.duration)).isoformat(), 'timeZone': 'UTC'},
        'colorId': hash(user.email) % 11 + 1,
        'extendedProperties': {
            'private': {
                'user_email': user.email,
                'reserva_id': str(reserva.id),
                'created_at': datetime.now().isoformat()
            }
        }
    }
    
    try:
        # Verificar conexión
        if check_internet_connection():
            service = get_google_calendar_service()
            if service:
                try:
                    # Intentar crear el evento
                    event = service.events().insert(
                        calendarId=CALENDAR_ID,
                        body=event_data
                    ).execute()
                    
                    # Actualizar la reserva con el ID del evento
                    reserva.google_calendar_event_id = event['id']
                    reserva.save(update_fields=['google_calendar_event_id'])
                    
                    # Limpiar pendientes del usuario
                    cache_key = f'user_{user.id}_pending_creates'
                    pending = cache.get(cache_key, [])
                    pending = [op for op in pending if op.get('reserva_id') != reserva.id]
                    cache.set(cache_key, pending, None)
                    
                    # Actualizar cachés
                    cache.delete(f'user_{user.id}_events')
                    cache.delete('all_synced_events')
                    
                    return {'status': 'success', 'event_id': event['id']}
                except Exception as e:
                    logger.error(f"Error creando evento en Google Calendar: {str(e)}")
                    # Caer al modo offline
        
        # Modo offline
        temp_event_id = generate_temp_id()
        reserva.google_calendar_event_id = temp_event_id
        reserva.save(update_fields=['google_calendar_event_id'])
        
        # Guardar en caché para sincronización posterior
        cache_key = f'user_{user.id}_pending_creates'
        pending = cache.get(cache_key, [])
        
        # Eliminar entradas duplicadas
        pending = [op for op in pending if op.get('reserva_id') != reserva.id]
        pending.append({
            'reserva_id': reserva.id,
            'event_data': event_data,
            'temp_id': temp_event_id,
            'created_at': datetime.now().isoformat()
        })
        cache.set(cache_key, pending, None)
        
        return {'status': 'offline', 'message': 'Evento guardado localmente'}
    
    except Exception as e:
        logger.error(f"Error crítico creando evento: {str(e)}", exc_info=True)
        return {'status': 'error', 'message': str(e)}

def update_calendar_event(reserva, user):
    """Actualiza evento existente con manejo mejorado"""
    if not reserva.google_calendar_event_id:
        return {'status': 'error', 'message': 'El evento no tiene ID de Google Calendar'}
    
    # Preparar datos del evento
    event_data = {
        'summary': reserva.vcName,
        'description': f"Reserva de {reserva.user.username}\nMotivo: {reserva.get_vcMotive_display()}\nObservaciones: {reserva.observations}",
        'start': {'dateTime': reserva.dateTime.isoformat(), 'timeZone': 'UTC'},
        'end': {'dateTime': (reserva.dateTime + timedelta(hours=reserva.duration)).isoformat(), 'timeZone': 'UTC'},
        'colorId': hash(reserva.user.email) % 11 + 1,
        'extendedProperties': {
            'private': {
                'user_email': reserva.user.email,
                'reserva_id': str(reserva.id),
                'updated_at': datetime.now().isoformat()
            }
        }
    }
    
    try:
        # Verificar conexión
        if check_internet_connection():
            service = get_google_calendar_service()
            if service:
                try:
                    # Verificar si el evento existe
                    existing_event = service.events().get(
                        calendarId=CALENDAR_ID,
                        eventId=reserva.google_calendar_event_id
                    ).execute()
                    
                    # Actualizar evento existente
                    updated_event = service.events().update(
                        calendarId=CALENDAR_ID,
                        eventId=reserva.google_calendar_event_id,
                        body=event_data
                    ).execute()
                    
                    # Actualizar cachés
                    cache.delete('all_synced_events')
                    cache.delete(f'user_{reserva.user.id}_events')
                    
                    # Limpiar pendientes
                    cache_key = f'user_{user.id}_pending_updates'
                    pending = cache.get(cache_key, [])
                    pending = [op for op in pending if op.get('event_id') != reserva.google_calendar_event_id]
                    cache.set(cache_key, pending, None)
                    
                    return {'status': 'success', 'event_id': updated_event['id']}
                
                except HttpError as e:
                    if e.resp.status == 404:
                        # Evento no existe, crear uno nuevo
                        try:
                            new_event = service.events().insert(
                                calendarId=CALENDAR_ID,
                                body=event_data
                            ).execute()
                            
                            # Actualizar ID en la reserva
                            reserva.google_calendar_event_id = new_event['id']
                            reserva.save(update_fields=['google_calendar_event_id'])
                            
                            return {'status': 'success', 'event_id': new_event['id']}
                        except Exception as e:
                            logger.error(f"Error creando evento nuevo: {str(e)}")
                            # Caer al modo offline
                    else:
                        logger.error(f"Error HTTP: {str(e)}")
                        # Caer al modo offline
                except Exception as e:
                    logger.error(f"Error actualizando evento: {str(e)}")
                    # Caer al modo offline
        
        # Modo offline: guardar actualización pendiente
        cache_key = f'user_{user.id}_pending_updates'
        pending = cache.get(cache_key, [])
        
        # Eliminar entradas duplicadas
        pending = [op for op in pending if op.get('event_id') != reserva.google_calendar_event_id]
        
        # Añadir nueva operación pendiente
        pending.append({
            'reserva_id': reserva.id,
            'event_id': reserva.google_calendar_event_id,
            'event_data': event_data,
            'created_at': datetime.now().isoformat()
        })
        cache.set(cache_key, pending, None)
        
        return {'status': 'offline', 'message': 'Cambios guardados localmente'}
    
    except Exception as e:
        logger.error(f"Error crítico actualizando evento: {str(e)}")
        return {'status': 'error', 'message': str(e)}

def delete_calendar_event(event_id, user):
    """Elimina evento con manejo de errores 410."""
    if not event_id:
        logger.error("Intento de eliminar evento sin ID")
        return {'status': 'error', 'message': 'Falta el ID del evento'}
    
    try:
        # Verificar conexión
        if check_internet_connection():
            service = get_google_calendar_service()
            if service:
                try:
                    # Intentar eliminar el evento
                    service.events().delete(
                        calendarId=CALENDAR_ID,
                        eventId=event_id
                    ).execute()
                    
                    # Limpiar pendientes
                    cache_key = f'user_{user.id}_pending_deletes'
                    pending = cache.get(cache_key, [])
                    if event_id in pending:
                        pending.remove(event_id)
                        cache.set(cache_key, pending, None)
                    
                    # Actualizar cachés
                    cache.delete('all_synced_events')
                    cache.delete(f'user_{user.id}_events')
                    
                    return {'status': 'success', 'message': 'Evento eliminado'}
                
                except HttpError as e:
                    if e.resp.status == 410:
                        logger.warning(f"Evento {event_id} ya eliminado")
                        
                        # Limpiar pendientes
                        cache_key = f'user_{user.id}_pending_deletes'
                        pending = cache.get(cache_key, [])
                        if event_id in pending:
                            pending.remove(event_id)
                            cache.set(cache_key, pending, None)
                        
                        return {'status': 'success', 'message': 'Evento ya eliminado'}
                    else:
                        logger.error(f"Error HTTP: {str(e)}")
                        # Caer al modo offline
                except Exception as e:
                    logger.error(f"Error eliminando evento: {str(e)}")
                    # Caer al modo offline

        # Modo offline
        cache_key = f'user_{user.id}_pending_deletes'
        pending = cache.get(cache_key, [])
        
        # Evitar duplicados
        if event_id not in pending:
            pending.append(event_id)
            cache.set(cache_key, pending, None)
        
        return {'status': 'offline', 'message': 'Eliminación pendiente'}
    
    except Exception as e:
        logger.error(f"Error crítico eliminando evento: {str(e)}", exc_info=True)
        return {'status': 'error', 'message': str(e)}

def sync_pending_operations(user):
    """Versión final con manejo completo de errores"""
    results = {
        'created': 0, 
        'updated': 0, 
        'deleted': 0, 
        'errors': 0,
        'not_found': 0,
        'status': 'success'
    }
    
    try:
        # Verificar conexión
        if not check_internet_connection():
            return {'status': 'offline', 'message': 'Sin conexión a internet'}
        
        # Obtener servicio
        service = get_google_calendar_service()
        if not service:
            raise ConnectionError("Servicio no disponible")

        # Obtener eventos existentes con manejo de errores
        try:
            events_result = service.events().list(
                calendarId=CALENDAR_ID,
                maxResults=2500,
                singleEvents=True
            ).execute()
            existing_events = {e['id']: e for e in events_result.get('items', [])}
        except Exception as e:
            logger.error(f"Error obteniendo eventos: {str(e)}")
            existing_events = {}

        # Procesar operaciones con merge de resultados seguro
        def safe_update(current, new):
            if new:  # Solo actualizar si new no es None
                for k, v in new.items():
                    current[k] = current.get(k, 0) + v
            return current

        safe_update(results, process_pending_creations(user, service, existing_events))
        safe_update(results, process_pending_updates(user, service, existing_events))
        safe_update(results, process_pending_deletions(user, service, existing_events))

        # Actualizar caché
        try:
            updated_events = service.events().list(
                calendarId=CALENDAR_ID,
                maxResults=2500,
                singleEvents=True
            ).execute().get('items', [])
            cache.set(f'user_{user.id}_events', updated_events, CACHE_TIMEOUT)
            cache.set(f'user_{user.id}_current_sync', datetime.now().isoformat(), CACHE_TIMEOUT)
        except Exception as e:
            logger.error(f"Error actualizando caché: {str(e)}")

    except ConnectionError:
        logger.warning("Modo offline - No se pudo sincronizar")
        results['status'] = 'offline'
    except Exception as e:
        logger.error(f"Error crítico en sincronización: {str(e)}")
        results['status'] = 'error'
        results['errors'] += 1
    
    # Limpiar reservas no encontradas
    if results['not_found'] > 0:
        clean_invalid_reservations(user)
    
    return results

def process_pending_creations(user, service, existing_events):
    """Procesa creaciones pendientes con mejor manejo de errores"""
    results = {'created': 0, 'errors': 0, 'not_found': 0}
    pending_creates = cache.get(f'user_{user.id}_pending_creates', [])
    remaining_creates = []
    
    for op in pending_creates:
        try:
            reserva_id = op.get('reserva_id')
            if not reserva_id:
                continue
                
            # Intentar obtener la reserva
            try:
                reserva = Reserve.objects.get(id=reserva_id)
                
                # Verificar si ya existe un evento para esta reserva
                event_exists = False
                for event_id, event in existing_events.items():
                    if event.get('extendedProperties', {}).get('private', {}).get('reserva_id') == str(reserva_id):
                        # Ya existe un evento para esta reserva
                        event_exists = True
                        # Actualizar ID en la reserva
                        reserva.google_calendar_event_id = event_id
                        reserva.save(update_fields=['google_calendar_event_id'])
                        results['created'] += 1
                        break
                
                if event_exists:
                    continue
                
                # Preparar datos del evento
                event_data = {
                    'summary': reserva.vcName,
                    'description': f"Reserva de {user.username}",
                    'start': {'dateTime': reserva.dateTime.isoformat(), 'timeZone': 'UTC'},
                    'end': {'dateTime': (reserva.dateTime + timedelta(hours=reserva.duration)).isoformat(), 'timeZone': 'UTC'},
                    'extendedProperties': {
                        'private': {
                            'reserva_id': str(reserva.id),
                            'user_email': user.email
                        }
                    }
                }
                
                # Insertar nuevo evento
                event = service.events().insert(
                    calendarId=CALENDAR_ID,
                    body=event_data
                ).execute()
                
                # Actualizar ID en la reserva
                reserva.google_calendar_event_id = event['id']
                reserva.save(update_fields=['google_calendar_event_id'])
                results['created'] += 1
                
            except Reserve.DoesNotExist:
                logger.warning(f"Reserva {reserva_id} no existe - Eliminando de pendientes")
                results['not_found'] += 1
            except Exception as e:
                logger.error(f"Error creando reserva {reserva_id}: {str(e)}")
                remaining_creates.append(op)
                results['errors'] += 1
        except Exception as e:
            logger.error(f"Error procesando creación: {str(e)}")
            remaining_creates.append(op)
            results['errors'] += 1
    
    # Actualizar caché solo si hay cambios
    if len(remaining_creates) != len(pending_creates):
        cache.set(f'user_{user.id}_pending_creates', remaining_creates, None)
    
    return results

def process_pending_updates(user, service, existing_events):
    """Procesa actualizaciones pendientes con manejo robusto de errores"""
    results = {'updated': 0, 'errors': 0, 'not_found': 0}
    pending_updates = cache.get(f'user_{user.id}_pending_updates', [])
    remaining_updates = []
    
    for op in pending_updates:
        try:
            reserva_id = op.get('reserva_id')
            if not reserva_id:
                continue
                
            # Intentar obtener la reserva
            try:
                reserva = Reserve.objects.get(id=reserva_id)
                event_id = op.get('event_id', reserva.google_calendar_event_id)
                
                # Verificar si el evento existe en Google
                if event_id in existing_events:
                    # Preparar datos completos del evento
                    event_data = {
                        'summary': reserva.vcName,
                        'description': f"Reserva de {user.username}",
                        'start': {'dateTime': reserva.dateTime.isoformat(), 'timeZone': 'UTC'},
                        'end': {'dateTime': (reserva.dateTime + timedelta(hours=reserva.duration)).isoformat(), 'timeZone': 'UTC'},
                        'extendedProperties': {
                            'private': {
                                'reserva_id': str(reserva.id),
                                'user_email': user.email,
                                'updated_at': datetime.now().isoformat()
                            }
                        }
                    }
                    
                    # Actualizar evento
                    service.events().update(
                        calendarId=CALENDAR_ID,
                        eventId=event_id,
                        body=event_data
                    ).execute()
                    results['updated'] += 1
                else:
                    # El evento no existe, intentar crearlo
                    try:
                        event_data = {
                            'summary': reserva.vcName,
                            'description': f"Reserva de {user.username}",
                            'start': {'dateTime': reserva.dateTime.isoformat(), 'timeZone': 'UTC'},
                            'end': {'dateTime': (reserva.dateTime + timedelta(hours=reserva.duration)).isoformat(), 'timeZone': 'UTC'},
                            'extendedProperties': {
                                'private': {
                                    'reserva_id': str(reserva.id),
                                    'user_email': user.email,
                                    'created_at': datetime.now().isoformat()
                                }
                            }
                        }
                        
                        new_event = service.events().insert(
                            calendarId=CALENDAR_ID,
                            body=event_data
                        ).execute()
                        
                        # Actualizar ID en la reserva
                        reserva.google_calendar_event_id = new_event['id']
                        reserva.save(update_fields=['google_calendar_event_id'])
                        results['updated'] += 1
                    except Exception as e:
                        logger.error(f"Error creando evento para actualización: {str(e)}")
                        remaining_updates.append(op)
                        results['errors'] += 1
            except Reserve.DoesNotExist:
                logger.warning(f"Reserva {reserva_id} no existe - Eliminando de pendientes")
                results['not_found'] += 1
            except Exception as e:
                logger.error(f"Error actualizando reserva {reserva_id}: {str(e)}")
                remaining_updates.append(op)
                results['errors'] += 1
        except Exception as e:
            logger.error(f"Error procesando actualización: {str(e)}")
            remaining_updates.append(op)
            results['errors'] += 1
    
    # Actualizar caché solo si hay cambios
    if len(remaining_updates) != len(pending_updates):
        cache.set(f'user_{user.id}_pending_updates', remaining_updates, None)
    
    return results

def process_pending_deletions(user, service, existing_events):
    """Procesa las eliminaciones pendientes de eventos"""
    results = {'deleted': 0, 'errors': 0}
    pending_deletes = cache.get(f'user_{user.id}_pending_deletes', [])
    remaining_deletes = []
    
    for event_id in pending_deletes:
        try:
            # Verificar si el evento existe antes de eliminarlo
            if event_id in existing_events:
                try:
                    service.events().delete(
                        calendarId=CALENDAR_ID,
                        eventId=event_id
                    ).execute()
                    results['deleted'] += 1
                    
                    # Actualizar la reserva en la base de datos local
                    Reserve.objects.filter(google_calendar_event_id=event_id).update(
                        google_calendar_event_id=None
                    )
                except Exception as e:
                    logger.error(f"Error eliminando evento {event_id}: {str(e)}")
                    remaining_deletes.append(event_id)
                    results['errors'] += 1
            else:
                # El evento ya no existe en Google Calendar
                # Actualizar la reserva en la base de datos local
                Reserve.objects.filter(google_calendar_event_id=event_id).update(
                    google_calendar_event_id=None
                )
        except Exception as e:
            logger.error(f"Error procesando eliminación: {str(e)}")
            remaining_deletes.append(event_id)
            results['errors'] += 1
    
    # Actualizar caché solo si hay cambios
    if len(remaining_deletes) != len(pending_deletes):
        cache.set(f'user_{user.id}_pending_deletes', remaining_deletes, None)
    
    return results

def find_existing_event(reserva, existing_events):
    """Busca un evento existente por reserva_id en propiedades extendidas"""
    for event_id, event in existing_events.items():
        if event.get('extendedProperties', {}).get('private', {}).get('reserva_id') == str(reserva.id):
            return event_id
    return None

def add_reserva_properties(event_data, reserva):
    """Añade metadatos a los eventos nuevos"""
    if 'extendedProperties' not in event_data:
        event_data['extendedProperties'] = {'private': {}}
    
    event_data['extendedProperties']['private'].update({
        'reserva_id': str(reserva.id),
        'user_email': reserva.user.email,
        'created_at': str(time.time())
    })
    
    return event_data

def clean_invalid_reservations(user):
    """Elimina operaciones pendientes de reservas que ya no existen"""
    for op_type in ['creates', 'updates', 'deletes']:
        cache_key = f'user_{user.id}_pending_{op_type}'
        pending_ops = cache.get(cache_key, [])
        
        valid_ops = []
        for op in pending_ops:
            try:
                if op_type == 'deletes':
                    # Para deletes, op es solo el ID del evento
                    valid_ops.append(op)
                    continue
                
                reserva_id = op.get('reserva_id')
                if not reserva_id:
                    continue
                    
                if isinstance(reserva_id, str) and reserva_id.startswith(('offline_', 'temp_')):
                    valid_ops.append(op)
                elif Reserve.objects.filter(id=reserva_id).exists():
                    valid_ops.append(op)
            except Exception as e:
                logger.error(f"Error limpiando operación: {str(e)}")
                # En caso de error, mantener la operación
                valid_ops.append(op)
        
        if len(valid_ops) != len(pending_ops):
            cache.set(cache_key, valid_ops, None)

__all__ = [
    'check_internet_connection',
    'sync_events',
    'create_calendar_event',
    'update_calendar_event',
    'delete_calendar_event',
    'sync_pending_operations',
    'CACHE_TIMEOUT'
]