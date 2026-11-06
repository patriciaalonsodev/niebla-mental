# Configuración de gunicorn (el servidor web en producción).
# gunicorn lee este archivo solo si está en la carpeta desde la que arranca.
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", 2))
# Las recetas con IA pueden tardar bastante más que los 30 s por defecto
timeout = 120
accesslog = "-"
