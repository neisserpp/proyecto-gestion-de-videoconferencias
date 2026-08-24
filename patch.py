import sys
import warnings
warnings.filterwarnings('ignore')

try:
    import cgi
except ImportError:
    import types
    class FieldStorage:
        def __init__(self, *args, **kwargs):
            self.fp = None
            self.headers = {}
            self.list = []
    def parse_multipart(*args, **kwargs):
        return {}
    def parse_header(string):
        return {}, {}
    cgi_module = types.ModuleType('cgi')
    cgi_module.FieldStorage = FieldStorage
    cgi_module.parse_multipart = parse_multipart
    cgi_module.parse_header = parse_header
    sys.modules['cgi'] = cgi_module
print('✅ Parches aplicados')
