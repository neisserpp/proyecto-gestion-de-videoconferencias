import time
import logging
import threading
from django.core.cache import cache
from .google_calendar import check_internet_connection, sync_pending_operations
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()

def sync_worker():
    """Worker que sincroniza operaciones pendientes periódicamente"""
    while True:
        try:
            if check_internet_connection():
                logger.info("Sincronizando operaciones pendientes...")
                
                # Sincronizar para todos los usuarios
                for user in User.objects.all():
                    try:
                        sync_pending_operations(user)
                    except Exception as e:
                        logger.error(f"Error sincronizando para {user.email}: {str(e)}")
                
                logger.info("Sincronización completada")
            
            # Esperar 5 minutos antes de la próxima sincronización
            time.sleep(300)
        
        except Exception as e:
            logger.error(f"Error en sync_worker: {str(e)}")
            time.sleep(60)  # Esperar 1 minuto en caso de error

# Iniciar el worker en un hilo separado
def start_sync_worker():
    thread = threading.Thread(target=sync_worker, daemon=True)
    thread.start()
    logger.info("Sync worker iniciado")