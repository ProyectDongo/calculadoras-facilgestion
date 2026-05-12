"""
conftest.py — Setup global para pytest.

Inicializa Django para que tests que importan módulos con `from django.*`
puedan ejecutarse. Los tests de services puros (test_iva, test_honorarios,
etc.) no lo necesitan, pero los de middleware/mindicador/cache sí.
"""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()
