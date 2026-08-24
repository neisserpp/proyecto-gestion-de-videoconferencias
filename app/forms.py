from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from .models import Local, Moderator, Reserve
from .validations import *
from django.contrib.auth.forms import AuthenticationForm

class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
            if self.is_bound and field_name in self.errors:
                field.widget.attrs['class'] += ' is-invalid'

class LocalForm(forms.ModelForm):
    nombre = forms.CharField(
        label="Nombre del Local",
        validators=[validate_name_chars],
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    capacidad = forms.IntegerField(
        label="Capacidad",
        validators=[validate_capacity_range],
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Entre 5 y 50 personas"
    )

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre']
        validate_unique_on_update(self.instance, 'nombre', nombre)
        return nombre

    class Meta:
        model = Local
        fields = ['nombre', 'sede', 'capacidad', 'disponible']
        widgets = {
            'sede': forms.Select(attrs={'class': 'form-select'}),
            'disponible': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

class ModeratorForm(forms.ModelForm):
    nombre = forms.CharField(
        label="Nombre Completo",
        validators=[validate_name_chars],
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    email = forms.EmailField(
        label="Correo Electrónico",
        validators=[validate_email_format],
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'ejemplo@uc.cl'
        })
    )

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre']
        validate_unique_on_update(self.instance, 'nombre', nombre)
        return nombre

    def clean_email(self):
        email = self.cleaned_data['email']
        validate_unique_on_update(self.instance, 'email', email)
        return email

    class Meta:
        model = Moderator
        fields = ['nombre', 'email', 'disponible']
        widgets = {
            'disponible': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }

class ReserveForm(forms.ModelForm):
    vcName = forms.CharField(
        label="Nombre de la Videoconferencia",
        validators=[validate_name_chars],
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    
    url = forms.CharField(
        label="URL de la Reunión",
        validators=[validate_url_format],
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://meet.google.com/...'
        })
    )

    
    dateTime = forms.DateTimeField(
        label="Fecha y Hora",
        validators=[validate_future_date, validate_working_hours],
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
            'class': 'form-control'
        })
    )
    
    duration = forms.IntegerField(
        label="Duración (horas)",
        validators=[validate_duration],
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Máximo 8 horas consecutivas"
    )
    
    cantpart = forms.IntegerField(
        label="Número de Participantes",
        validators=[validate_participants],
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Mínimo 2, máximo 50 participantes"
    )

    weCreators = forms.ChoiceField(
        label="¿Somos Creadores?",
        choices=[(True, 'Sí'), (False, 'No')],
        widget=forms.Select(attrs={'class': 'form-select'}),
        initial=False
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Configuración dinámica de campos
        self.fields['local'] = forms.ModelChoiceField(
            queryset=Local.objects.filter(disponible=True),
            label="Local físico",
            empty_label="Seleccionar local (opcional)",
            required=False,
            widget=forms.Select(attrs={'class': 'form-select'}),
            help_text="Espacios disponibles con capacidad verificada"
        )
        
        self.fields['idofModerator'] = forms.ModelChoiceField(
            queryset=Moderator.objects.filter(disponible=True),
            label="Moderador asignado",
            empty_label="Seleccionar moderador (opcional)",
            required=False,
            widget=forms.Select(attrs={'class': 'form-select'})
        )

    def clean_vcName(self):
        vc_name = self.cleaned_data['vcName']
        validate_unique_on_update(self.instance, 'vcName', vc_name)
        return vc_name

    def clean(self):
        cleaned_data = super().clean()
        date_time = cleaned_data.get('dateTime')
        duration = cleaned_data.get('duration')
        local = cleaned_data.get('local')
        cantidad = cleaned_data.get('cantpart')
        moderator = cleaned_data.get('idofModerator')

        # Validación de capacidad vs participantes
        if local and cantidad:
            if not (2 <= cantidad <= local.capacidad):
                self.add_error('cantpart', 
                    f"La cantidad debe estar entre 2 y {local.capacidad} participantes")

        # Validación de solapamiento de horarios
        if all([date_time, duration, local]):
            try:
                validate_reservation_overlap(local, date_time, duration, self.instance)
            except ValidationError as e:
                self.add_error('dateTime', e)

        # Validación de disponibilidad del moderador
        if moderator and not moderator.disponible:
            self.add_error('idofModerator', "Este moderador no está disponible")

        # Validación de anticipación mínima
        if date_time and (date_time - timezone.now()) < timedelta(hours=24):
            self.add_error('dateTime', "Reserva debe hacerse con al menos 24 horas de anticipación")

        return cleaned_data

    class Meta:
        model = Reserve
        fields = [
            'vcName', 'vcMotive', 'requestArea', 'url', 'platafom',
            'weCreators', 'dateTime', 'duration', 'cantpart',
            'observations', 'local', 'idofModerator'
        ]
        widgets = {
            'vcMotive': forms.Select(attrs={'class': 'form-select'}),
            'requestArea': forms.Select(attrs={'class': 'form-select'}),
            'platafom': forms.Select(attrs={'class': 'form-select'}),
            'observations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Detalles adicionales importantes...'
            }),
        }

class ApproveReserveForm(forms.ModelForm):
    class Meta:
        model = Reserve
        fields = ['status', 'rejection_reason', 'rejection_details']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'rejection_reason': forms.Select(attrs={'class': 'form-select'}),
            'rejection_details': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }






