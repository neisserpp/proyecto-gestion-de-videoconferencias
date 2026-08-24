import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reserva_vc.settings')
application = get_wsgi_application()

# Para Vercel
app = application