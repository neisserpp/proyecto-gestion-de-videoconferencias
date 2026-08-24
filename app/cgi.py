# cgi.py - Reemplazo para Python 3.13
import sys
import warnings

# Suprimir advertencias de deprecación
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Importar desde el paquete alternativo
try:
    from cgi_standalone import *
except ImportError:
    # Si no está instalado, crea funciones mínimas necesarias
    import os
    import sys
    
    class FieldStorage:
        def __init__(self, *args, **kwargs):
            self.fp = None
            self.headers = {}
            self.list = []
            
    def parse_multipart(*args, **kwargs):
        return {}
        
    def parse_header(string):
        return {}, {}
        
    class MiniFieldStorage:
        def __init__(self, name, value):
            self.name = name
            self.value = value