# app/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.core.cache import cache
from .google_calendar import check_internet_connection, sync_pending_operations

class AutoSyncMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            last_sync = cache.get(f'user_{request.user.id}_last_sync')
            sync_interval = 60  # 1 minuto
            
            if check_internet_connection() and (not last_sync or (timezone.now())):
                try:
                    sync_pending_operations(request.user)
                    cache.set(f'user_{request.user.id}_last_sync', timezone.now())
                except Exception as e:
                    pass  # Evitar interrumpir el flujo por errores de sync