from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from app.google_calendar import sync_pending_operations
from django.utils import timezone

User = get_user_model()

class Command(BaseCommand):
    help = 'Sincroniza operaciones pendientes con Google Calendar'

    def handle(self, *args, **options):
        users = User.objects.all()
        for user in users:
            result = sync_pending_operations(user)
            self.stdout.write(f"Sincronizadas {result} operaciones para {user.email}")