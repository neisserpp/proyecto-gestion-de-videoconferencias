from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator, EmailValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from datetime import timedelta

def validate_unique_on_update(instance, field, value):
    """Valida unicidad excluyendo la instancia actual al editar"""
    if instance and instance.pk:
        queryset = instance.__class__.objects.exclude(pk=instance.pk)
    else:
        queryset = instance.__class__.objects.all()
    
    if queryset.filter(**{field: value}).exists():
        raise ValidationError(_('Este valor ya está registrado.'))

# Validadores base
validate_name_chars = RegexValidator(
    regex=r'^[a-zA-Z\sáéíóúÁÉÍÓÚñÑ]+$',
    message=_("Solo se permiten letras y espacios")
)

validate_url_format = RegexValidator(
    regex=r'^(https?:\/\/)[\w.-]+\.[a-zA-Z]{2,}(\/\S*)?$',
    message=_("Formato de URL inválido. Ejemplo válido: https://ejemplo.com")
)

validate_email_format = EmailValidator(
    message=_("Ingrese un correo electrónico válido. Ejemplo: usuario@dominio.com")
)

# Validaciones personalizadas
def validate_unique_field(model, field_name, instance=None):
    def validator(value):
        queryset = model.objects.filter(**{field_name: value})
        if instance:
            queryset = queryset.exclude(pk=instance.pk)
        if queryset.exists():
            raise ValidationError(_('Este valor ya está registrado.'))
    return validator

def validate_future_date(value):
    if value <= timezone.now() + timedelta(minutes=30):
        raise ValidationError(_("La reserva debe ser al menos 30 minutos en el futuro"))

def validate_working_hours(value):
    if not (8 <= value.hour < 20):
        raise ValidationError(_("Horario laboral permitido: 8:00 AM - 8:00 PM"))

def validate_capacity_range(value):
    if not (5 <= value <= 50):
        raise ValidationError(_("La capacidad debe estar entre 5 y 50 personas"))

def validate_participants(value):
    if not (2 <= value <= 50):
        raise ValidationError(_("Participantes deben ser entre 2 y 50 personas"))

def validate_duration(value):
    if not (1 <= value <= 8):
        raise ValidationError(_("Duración permitida: 1-8 horas"))

def validate_reservation_overlap(local, date_time, duration, instance=None):
    from .models import Reserve
    if local is None:
        return
    if date_time and duration:
        end_time = date_time + timedelta(hours=duration)
        overlapping = Reserve.objects.filter(
            local=local,
            dateTime__lt=end_time,
            dateTime__gte=date_time
        ).exclude(pk=instance.pk if instance else None)
        
        if overlapping.exists():
            raise ValidationError(_("El local ya está reservado en este horario"))

def validate_moderator_availability(moderator):
    if not moderator.disponible:
        raise ValidationError(_("El moderador seleccionado no está disponible"))