from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Reserve
from .google_calendar import check_internet_connection
from datetime import timedelta

@receiver(post_save, sender=Reserve)
def sync_on_save(sender, instance, **kwargs):
    """Maneja creaciones/actualizaciones solo en modo offline."""
    if check_internet_connection():
        return  # No hacer nada si hay conexión
    
    if not instance.google_calendar_event_id or instance.google_calendar_event_id.startswith('offline_'):
        cache_key = f'user_{instance.user.id}_pending_creates'
        pending = cache.get(cache_key, [])
        
        # Evitar duplicados
        existing = [op for op in pending if op['reserva_id'] == instance.id]
        if not existing:
            pending.append({
                'reserva_id': instance.id,
                'event_data': {
                    'summary': instance.vcName,
                    'description': f"Reserva de {instance.user.username}\nMotivo: {instance.get_vcMotive_display()}\nObservaciones: {instance.observations}",
                    'start': {'dateTime': instance.dateTime.isoformat(), 'timeZone': 'UTC'},
                    'end': {'dateTime': (instance.dateTime + timedelta(hours=instance.duration)).isoformat(), 'timeZone': 'UTC'},
                    'colorId': hash(instance.user.email) % 11 + 1,
                    'extendedProperties': {'private': {'user_email': instance.user.email}}
                }
            })
            cache.set(cache_key, pending, None)

@receiver(post_delete, sender=Reserve)
def sync_on_delete(sender, instance, **kwargs):
    """Maneja eliminaciones solo si el evento fue sincronizado."""
    if instance.google_calendar_event_id and not instance.google_calendar_event_id.startswith('offline_'):
        cache_key = f'user_{instance.user.id}_pending_deletes'
        pending = cache.get(cache_key, [])
        if instance.google_calendar_event_id not in pending:
            pending.append(instance.google_calendar_event_id)
            cache.set(cache_key, pending, None)