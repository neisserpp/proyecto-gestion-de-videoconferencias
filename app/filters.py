import django_filters
from .models import Moderator, Local, Reserve
from django.core.validators import MinValueValidator
from django.forms import NumberInput
from django.forms import DateTimeInput

class ModeratorFilter(django_filters.FilterSet):
    nombre = django_filters.CharFilter(lookup_expr='icontains', label='Nombre del Moderador')
    email = django_filters.CharFilter(lookup_expr='icontains', label='Correo Electrónico')
    disponible = django_filters.BooleanFilter(label='Disponible')

    class Meta:
        model = Moderator
        fields = ['nombre', 'email', 'disponible']

class LocalFilter(django_filters.FilterSet):
    nombre = django_filters.CharFilter(lookup_expr='icontains', label='Nombre del Local')
    sede = django_filters.ChoiceFilter(choices=Local.SEDE_CHOICES, label='Sede')
    disponible = django_filters.BooleanFilter(label='Disponible')
    capacidad = django_filters.NumberFilter(
        label='Capacidad',
        widget=NumberInput(attrs={'min': 0}),  # Solo permite valores positivos
        lookup_expr='gte'  # Filtra por capacidad mayor o igual al valor ingresado
    )

    class Meta:
        model = Local
        fields = ['nombre', 'sede', 'disponible', 'capacidad']

from .models import Reserve

class ReserveFilter(django_filters.FilterSet):
    vcName = django_filters.CharFilter(lookup_expr='icontains', label='Nombre de la Videoconferencia')
    vcMotive = django_filters.ChoiceFilter(choices=Reserve.motivo, label='Motivo')
    platafom = django_filters.ChoiceFilter(choices=Reserve.plataforms, label='Plataforma')
    dateTime = django_filters.DateTimeFilter(
        field_name='dateTime',
        lookup_expr='date',
        label='Fecha y Hora',
    widget=DateTimeInput(attrs={'type': 'datetime-local'})  # Widget para fecha y hora
    )
    idofModerator = django_filters.ModelChoiceFilter(queryset=Moderator.objects.all(), label='Moderador')
    local = django_filters.ModelChoiceFilter(queryset=Local.objects.all(), label='Local')
    class Meta:
        model = Reserve
        fields = ['vcName', 'vcMotive', 'platafom', 'dateTime', 'idofModerator', 'local']
