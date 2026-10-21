#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py init_crm

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 1 \
  --timeout 60 \
  --access-logfile -
