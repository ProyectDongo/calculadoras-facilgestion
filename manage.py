#!/usr/bin/env python
"""manage.py — Django CLI entrypoint."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. ¿Activaste el venv o estás dentro del "
            "contenedor docker?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
