from django.test import TestCase
from models import Moderator
# Create your tests here.g

class TestModerator(TestCase):
    def setUp (self):{}


# Listar
query = Moderator.objects.all()

# Insercion
M = Moderator()
M.moderatorName = 'Accionista'
M.email = 'adawd@gamil.com'
M.phoneNumber = '2132312313'
M.save()

# Edicion
M = Moderator.objects.get(email = 'adawd@gamil.com')
M.moderatorName = 'Accionistassss'
M.save()

# Eliminar
'''
M = Moderator.objects.get(id = 1)
M.delete
'''


