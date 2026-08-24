from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, EmailValidator
from datetime import datetime
from django.contrib.auth.models import AbstractUser
from django.contrib.auth import get_user_model
from django.conf import settings 

boolean_choice = ((True, 'Si'),(False, 'No'))

class CustomUser(AbstractUser):
    ROLES = (
        ('admin', 'Administrador'),
        ('user', 'Usuario'),
    )
    role = models.CharField(max_length=10, choices=ROLES, default='user')

    class Meta:
        db_table = 'app_customuser'

    def __str__(self):
        return self.username

class Moderator(models.Model):
    nombre = models.CharField(max_length=50, default='')
    email = models.EmailField(validators=[EmailValidator()])
    disponible = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class Local(models.Model):
    SEDE_CHOICES = [
        ('jose_marti', 'José Martí'),
        ('ignacio_agramonte', 'Ignacio Agramonte'),
    ]
    nombre = models.CharField(max_length=50, default='')
    sede = models.CharField(max_length=50, choices=SEDE_CHOICES, default='')
    disponible = models.BooleanField(default=True)
    capacidad = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.nombre

class Reserve(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'),
    ]
    REJECTION_REASONS = [
        ('schedule', 'Solapamiento de horario'),
        ('capacity', 'Capacidad excedida'),
        ('moderator', 'Moderador no disponible'),
        ('other', 'Otro motivo'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reserves', verbose_name='Usuario', null=True, blank=True)
    nombre_validation = RegexValidator(r'^[a-zA-Z\s]*$', 'El nombre solo puede contener letras y espacios.')
    vcName = models.CharField(max_length=150, validators=[nombre_validation], verbose_name='Nombre de la Videoconferencia')
    motivo = [
        ('mes', 'MES'),
        ('defdoc', 'Defensa de Doctorado'),
        ('defmaest', 'Defensa de Maestría'),
        ('colint', 'Colaboración Internacional'),
        ('proycoop', 'Proyecto de Cooperación'),
        ('acred', 'Acreditación'),
        ('post', 'Posgrado')
    ]
    vcMotive = models.CharField(max_length=50, choices=motivo, default='post', verbose_name='Motivo')
    idofModerator = models.ForeignKey('Moderator', null=True, blank=True, on_delete=models.CASCADE, verbose_name="Moderador")
    area = [
        ('cum', 'CUM'),
        ('fac', 'Facultad'),
        ('dir', 'Dirección'),
        ('dir_gen', 'Dirección General'),
        ('vi', 'Vicerrectoría'),
        ('re', 'Rectoría')
    ]
    requestArea = models.CharField(max_length=10, choices=area, default='fac', verbose_name='Área de Solicitud')
    url = models.URLField(verbose_name='URL')
    plataforms = [
        ('jitsi', 'Jitsi'),
        ('googlemeet', 'Google Meet'),
        ('microteams', 'Microsoft Teams')
    ]
    platafom = models.CharField(max_length=10, choices=plataforms, default='googlemeet', verbose_name='Plataforma')
    weCreators = models.BooleanField(choices=[(True, 'Sí'), (False, 'No')], default=False, verbose_name='¿Somos Creadores?')
    dateTime = models.DateTimeField(verbose_name='Fecha y Hora')
    duration = models.PositiveIntegerField(default=0, verbose_name='Duración')
    cantpart = models.PositiveSmallIntegerField(default=0, verbose_name='Cantidad de Participantes')
    observations = models.TextField(blank=True, verbose_name='Observaciones')
    local = models.CharField(max_length=50, null=True, blank=True, verbose_name='Local')
    google_calendar_event_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="ID de Evento en Google Calendar",
        help_text="Se completa automáticamente al sincronizar"
    )
    status_anterior = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )
    rejection_reason = models.CharField(
        max_length=20,
        choices=REJECTION_REASONS,
        blank=True,
        null=True
    )
    rejection_details = models.TextField(
        blank=True,
        null=True,
        verbose_name='Detalles del rechazo'
    )
    
    def is_synced(self):
        return bool(self.google_calendar_event_id)
    def __str__(self):
        return self.vcName
    
    def save(self, *args, **kwargs):
        """Guardar estado anterior antes de cambios"""
        if self.pk:
            original = Reserve.objects.get(pk=self.pk)
            self.status_anterior = original.status
        super().save(*args, **kwargs)

class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,  # Usar el modelo de usuario configurado
        on_delete=models.CASCADE,
        related_name='profile'
    )
    theme = models.CharField(max_length=10, default='light')
    
    def __str__(self):
        return f"Perfil de {self.user.username}"
    
class Notification(models.Model):
    TYPES = (
        ('approval', 'Aprobación de Reserva'),
        ('rejection', 'Rechazo de Reserva'),
        ('system', 'Sistema'),
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    reserve = models.ForeignKey(
        Reserve,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    notification_type = models.CharField(max_length=20, choices=TYPES)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.get_notification_type_display()} - {self.user.username}"

class PendingOperation(models.Model):
    OPERATION_TYPES = (
        ('create', 'Crear'),
        ('update', 'Actualizar'),
        ('delete', 'Eliminar'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    operation_type = models.CharField(max_length=10, choices=OPERATION_TYPES)
    reserva = models.ForeignKey('Reserve', on_delete=models.CASCADE, null=True, blank=True)
    event_id = models.CharField(max_length=255, null=True, blank=True)
    event_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    attempts = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['created_at']