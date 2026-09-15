"""
Django settings for core project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-viwntswg350de)u67-d&vtlf&lkmas+yq4)7fz(7c&@kke=3vk')

DEBUG = _env_bool('DEBUG', True)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1, 10.120.110.16').split(',')
    if host.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'controladoria',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# SQLite: metadados do sistema (medidas, regras, exceções)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    },
}

# SQL Server DW: leitura da FatoResultadoFinanceiroQ12 e dimensões
_mssql_server = os.getenv('mssql_server') or os.getenv('SQL_SERVER', 'localhost')
_mssql_database = os.getenv('mssql_database') or os.getenv('SQL_DATABASE', 'DW')
_mssql_user = os.getenv('mssql_user') or os.getenv('SQL_USERNAME', '')
_mssql_password = os.getenv('mssql_password') or os.getenv('SQL_PASSWORD', '')
_mssql_port = os.getenv('mssql_port') or os.getenv('SQL_PORT', '1433')

if _mssql_database and _mssql_server:
    DATABASES['dw'] = {
        'ENGINE': 'mssql',
        'NAME': _mssql_database,
        'HOST': _mssql_server,
        'PORT': _mssql_port,
        'USER': _mssql_user,
        'PASSWORD': _mssql_password,
        'OPTIONS': {
            'driver': os.getenv('SQL_DRIVER', 'ODBC Driver 17 for SQL Server'),
        },
    }

DATABASE_SCHEMA_DW = os.getenv('DATABASE_SCHEMA_DW', 'dbo')

# Fonte das regras no DW: VIEW consolidada (padrão) ou fato + joins manuais
FONTE_REGRAS_TABELA = os.getenv('FONTE_REGRAS_TABELA', 'VW_Q12_SISTEMA')
FONTE_REGRAS_USAR_JOINS = _env_bool('FONTE_REGRAS_USAR_JOINS', False)
FONTE_REGRAS_AUTO_CAMPOS = _env_bool('FONTE_REGRAS_AUTO_CAMPOS', True)

DATABASE_ROUTERS = ['controladoria.db_router.DWRouter']

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = os.getenv('TIME_ZONE', 'America/Fortaleza')
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'controladoria:login'
LOGIN_REDIRECT_URL = 'controladoria:medida_list'
LOGOUT_REDIRECT_URL = 'controladoria:login'

# Sessão persistente: refresh não deve deslogar o usuário.
SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 horas
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
