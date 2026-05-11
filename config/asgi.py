"""ASGI entry point (no usado en fase 1, dejado por consistencia)."""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
application = get_asgi_application()
