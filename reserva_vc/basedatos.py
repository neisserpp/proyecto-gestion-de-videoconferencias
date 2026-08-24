import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SQLITE = {
    'defailt': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db/sqlite/db.sqlite3'),
    }
}

POSTGRESQL = {
    'defailt': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'reserva',
        'USER': 'postgres',
        'PASSWORD': '1234',
        'HOST': 'localhost',
        'PORT': '5432'
    }
}