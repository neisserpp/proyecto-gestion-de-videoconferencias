from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.conf import settings
import os
import logging
from app.google_calendar import get_google_calendar_service, sync_pending_operations
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sincroniza eliminaciones pendientes usando la cache configurada en settings'

    def handle(self, *args, **options):
        cache_dir = settings.CACHES['default']['LOCATION']
        if not os.path.exists(cache_dir):
            self.stdout.write(self.style.WARNING(f'Creando directorio de cache: {cache_dir}'))
            os.makedirs(cache_dir, exist_ok=True)
        
        if not os.access(cache_dir, os.W_OK):
            self.stdout.write(self.style.ERROR(f'Sin permisos en el directorio de cache: {cache_dir}'))
            return

        pending_ops = cache.get('pending_deletes', [])
        
        if not pending_ops:
            self.stdout.write(self.style.SUCCESS('✅ No hay operaciones pendientes'))
            return

        self.stdout.write(f'🔄 Procesando {len(pending_ops)} eliminaciones pendientes...')
        
        success = 0
        service = get_google_calendar_service()
        
        for op in pending_ops.copy():
            try:
                service.events().delete(
                    calendarId="neffex.pp@gmail.com",
                    eventId=op['event_id']
                ).execute()
                pending_ops.remove(op)
                success += 1
                logger.info(f"Evento {op['event_id']} eliminado exitosamente")
            except Exception as e:
                logger.error(f"Error eliminando evento {op['event_id']}: {str(e)}")
                continue
        
        cache_timeout = settings.CACHES['default']['TIMEOUT']
        cache.set('pending_deletes', pending_ops, timeout=cache_timeout)
        
        result_msg = (
            f"Resultado final:\n"
            f"• 🟢 Eliminaciones exitosas: {success}\n"
            f"• 🟠 Pendientes por reintentar: {len(pending_ops)}\n"
            f"• 📍 Ubicación cache: {cache_dir}"
        )
        
        self.stdout.write(self.style.SUCCESS(result_msg))