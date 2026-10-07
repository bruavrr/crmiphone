import os
from pathlib import Path
from urllib.parse import urlparse, unquote
BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv('DEBUG', 'true').lower() == 'true'
SECRET_KEY = os.getenv('SECRET_KEY', 'local-development-only-change-before-deployment')
if not DEBUG and SECRET_KEY == 'local-development-only-change-before-deployment':
    raise RuntimeError('SECRET_KEY obrigatória em produção')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','crm']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','whitenoise.middleware.WhiteNoiseMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','crm.middleware.SecurityMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF='config.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','crm.context.navigation']}}]
WSGI_APPLICATION='config.wsgi.application'
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':os.getenv('SQLITE_PATH',str(BASE_DIR/'db.sqlite3')),'OPTIONS':{'timeout':30}}}
if os.getenv('DATABASE_URL'):
    u=urlparse(os.environ['DATABASE_URL'])
    DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':u.path.lstrip('/'),'USER':unquote(u.username or ''),'PASSWORD':unquote(u.password or ''),'HOST':u.hostname,'PORT':u.port or 5432,'CONN_MAX_AGE':60,'OPTIONS':{'sslmode':os.getenv('DB_SSLMODE','require')}}}
AUTH_USER_MODEL='crm.User'
AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE='pt-br'
TIME_ZONE='America/Sao_Paulo'
USE_I18N=True
USE_TZ=True
STATIC_URL='/static/'
STATIC_ROOT=BASE_DIR/'staticfiles'
MEDIA_ROOT=BASE_DIR/'media'
MEDIA_URL='/media/'
LOGIN_URL='/login/'
LOGIN_REDIRECT_URL='/dashboard/'
LOGOUT_REDIRECT_URL='/login/'
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE='Lax'
CSRF_COOKIE_SAMESITE='Lax'
SESSION_COOKIE_SECURE=not DEBUG
CSRF_COOKIE_SECURE=not DEBUG
SECURE_SSL_REDIRECT=not DEBUG
SECURE_HSTS_SECONDS=31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS=not DEBUG
SECURE_HSTS_PRELOAD=not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF=True
X_FRAME_OPTIONS='DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE=5*1024*1024
META_ACCESS_TOKEN=os.getenv('META_ACCESS_TOKEN','')
META_APP_SECRET=os.getenv('META_APP_SECRET','')
META_VERIFY_TOKEN=os.getenv('META_VERIFY_TOKEN','')
LEAD_API_KEY=os.getenv('LEAD_API_KEY','')

if not DEBUG and not os.getenv('DATABASE_URL'):
    raise RuntimeError('DATABASE_URL PostgreSQL obrigatória em produção')

STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
SECURE_REDIRECT_EXEMPT=[r'^health/$']
if os.getenv('TRUST_PROXY','false').lower()=='true':
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')
