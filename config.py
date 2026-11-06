# ══════════════════════════════════════════════════════════════
#  App de organización · config.py
#  Configuración por entorno (desarrollo, producción y tests)
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

import os
from datetime import timedelta

from dotenv import load_dotenv

# Carga el .env en os.environ. Importante: models._fernet() lee
# CLAVE_CIFRADO_DATOS directamente de os.environ.
load_dotenv()


def _url_base_datos():
    """Los proveedores (Railway, Render…) dan la URL como postgres:// o
    postgresql://. Se fija el controlador psycopg 3, que es el que está
    instalado (así no depende de cuál elija SQLAlchemy por defecto)."""
    url = os.environ.get("DATABASE_URL", "")
    for prefijo in ("postgres://", "postgresql://"):
        if url.startswith(prefijo):
            return "postgresql+psycopg://" + url[len(prefijo):]
    return url


# ──────────────────────────────────────────────────────────────
# Configuración base
# ──────────────────────────────────────────────────────────────

class Config:
    # Nombre visible de la app: cámbialo aquí (o en el .env) y se actualiza en todas partes
    APP_NOMBRE = os.environ.get("APP_NOMBRE", "Niebla Mental")

    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _url_base_datos()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Comprueba la conexión antes de usarla (evita errores tras
    # periodos de inactividad del servidor de base de datos).
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Cookies de sesión
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # "Recordarme" durante 30 días: no tener que acordarse de la
    # contraseña cada vez que se abre la app.
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_HTTPONLY = True

    # Recetas con IA (opcional): clave de la API de Claude y límite diario
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    RECETAS_IA_AL_DIA = int(os.environ.get("RECETAS_IA_AL_DIA", 10))
    COMIDAS_IA_AL_DIA = int(os.environ.get("COMIDAS_IA_AL_DIA", 40))

    # Tamaño máximo de lo que se sube (fotos): 8 MB
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024

    # Google Calendar (opcional: sin ellas no aparece la opción de conectar)
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

    # Variables que deben existir para arrancar
    VARIABLES_OBLIGATORIAS = ("SECRET_KEY", "DATABASE_URL", "CLAVE_CIFRADO_DATOS")


class DesarrolloConfig(Config):
    DEBUG = True


class ProduccionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True     # solo por HTTPS
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    # Railway (y casi todos los servidores) ponen un «proxy» delante que
    # recibe el https; esto le dice a Flask que se fíe de él (1 salto).
    DETRAS_DE_PROXY = True


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "clave-solo-para-tests"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    VARIABLES_OBLIGATORIAS = ("CLAVE_CIFRADO_DATOS",)
    WTF_CSRF_ENABLED = False  # los tests envían formularios sin token
    # Nunca las claves reales de Google: los tests usan un Google simulado
    GOOGLE_CLIENT_ID = None
    GOOGLE_CLIENT_SECRET = None
    ANTHROPIC_API_KEY = None     # los tests usan una IA simulada


CONFIGURACIONES = {
    "desarrollo": DesarrolloConfig,
    "produccion": ProduccionConfig,
    "test": TestConfig,
}
