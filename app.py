# ══════════════════════════════════════════════════════════════
#  App de organización · app.py
#  Fábrica de la aplicación (create_app)
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

import os

from cryptography.fernet import Fernet
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from config import CONFIGURACIONES
from extensions import csrf, db, login_manager, migrate


def create_app(nombre_config=None):
    """Crea y configura la aplicación.

    nombre_config: "desarrollo", "produccion" o "test". Si no se
    indica, se lee de la variable de entorno APP_CONFIG.
    """
    nombre_config = nombre_config or os.environ.get("APP_CONFIG", "desarrollo")
    app = Flask(__name__)
    app.config.from_object(CONFIGURACIONES[nombre_config])

    _validar_configuracion(app)

    if app.config.get("DETRAS_DE_PROXY"):
        # Para que url_for(..., _external=True) dé https://tu-dominio y no http://interno
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Enlazar extensiones
    db.init_app(app)
    # render_as_batch: SQLite no permite ALTER TABLE completo; en modo
    # batch Alembic recrea la tabla. En PostgreSQL no hace falta.
    es_sqlite = app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite")
    migrate.init_app(app, db, compare_type=True, render_as_batch=es_sqlite)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Inicia sesión para continuar."
    login_manager.login_message_category = "info"
    csrf.init_app(app)

    # Importar los modelos para que Flask-Migrate (Alembic) los vea
    import models  # noqa: F401

    # Blueprints (cada sección de la app tendrá el suyo)
    from api_salud import bp as api_salud_bp
    from auth import bp as auth_bp
    from captura import bp as captura_bp
    from compra import bp as compra_bp
    from cuerpo import bp as cuerpo_bp
    from diario import bp as diario_bp
    from eventos import bp as eventos_bp
    from google_calendar import bp as google_bp
    from medicacion import bp as medicacion_bp
    from notas import bp as notas_bp
    from nutricion import bp as nutricion_bp
    from perfil import bp as perfil_bp
    from salud import bp as salud_bp
    from tareas import bp as tareas_bp
    for blueprint in (
        auth_bp, captura_bp, tareas_bp, notas_bp, compra_bp, salud_bp,
        medicacion_bp, diario_bp, eventos_bp, google_bp, perfil_bp, nutricion_bp, cuerpo_bp,
        api_salud_bp,
    ):
        app.register_blueprint(blueprint)

    from utilidades import fecha_corta, fecha_larga, fecha_larga_dt, hora_local, kg, miles
    for filtro in (fecha_larga, fecha_corta, fecha_larga_dt, hora_local, kg, miles):
        app.add_template_filter(filtro)

    @app.context_processor
    def datos_comunes():
        """Variables disponibles en todas las plantillas."""
        tema = current_user.tema if current_user.is_authenticated else "oscuro"
        return {
            "tema": tema,
            "nombre_app": app.config["APP_NOMBRE"],
            "seccion_activa": SECCION_DE.get(request.blueprint, "inicio"),
            "volver_inicio": request.endpoint in LISTADOS_CON_VOLVER,
            "logo_url": _url_logo(app),
            "icono_url": lambda nombre: _url_icono(app, nombre),
            "icono": lambda nombre, emoji="", tam=24: _icono(app, nombre, emoji, tam),
        }

    _registrar_rutas_basicas(app)

    return app


# ──────────────────────────────────────────────────────────────
# Comprobaciones al arrancar
# ──────────────────────────────────────────────────────────────

def _validar_configuracion(app):
    """Falla pronto y con un mensaje claro si falta algo, en vez
    de dar un error raro más tarde."""
    faltan = [
        nombre
        for nombre in app.config["VARIABLES_OBLIGATORIAS"]
        if not (app.config.get(nombre) or os.environ.get(nombre))
    ]
    if faltan:
        raise RuntimeError(
            "Faltan variables en el .env: " + ", ".join(faltan)
            + ". Copia .env.example como .env y rellénalas."
        )

    # Comprobar que la clave de cifrado tiene el formato correcto
    clave = os.environ.get("CLAVE_CIFRADO_DATOS")
    if clave:
        try:
            Fernet(clave.encode())
        except ValueError as error:
            raise RuntimeError(
                "CLAVE_CIFRADO_DATOS no es una clave Fernet válida. "
                "Genera una nueva con el comando del README."
            ) from error


# ──────────────────────────────────────────────────────────────
# Rutas básicas (las secciones irán en blueprints)
# ──────────────────────────────────────────────────────────────

def _url_icono(app, nombre):
    """static/img/iconos/<nombre>.png si existe (con ?v= para refrescar la caché)."""
    ruta = os.path.join(app.static_folder, "img", "iconos", f"{nombre}.png")
    if not nombre or not os.path.exists(ruta):
        return None
    return url_for("static", filename=f"img/iconos/{nombre}.png", v=int(os.path.getmtime(ruta)))


def _icono(app, nombre, emoji, tam):
    """Tu icono propio en pequeño (junto a un texto) o, si no existe, el emoji."""
    from markupsafe import Markup, escape
    url = _url_icono(app, nombre)
    if not url:
        return escape(emoji)
    return Markup(f'<img class="icono-mini" src="{url}" alt="" width="{int(tam)}" height="{int(tam)}">')


def _enlace_atajos():
    """Enlace que, en el iPhone, ejecuta los atajos de pasos y de sueño
    seguidos y vuelve a la app (x-callback-url de Atajos)."""
    from urllib.parse import quote

    def ejecutar(nombre, despues):
        return (f"shortcuts://x-callback-url/run-shortcut?name={quote(nombre)}"
                f"&x-success={quote(despues, safe='')}&x-error={quote(despues, safe='')}")

    volver = url_for("inicio", _external=True)
    return ejecutar("Pasos Niebla Mental", ejecutar("Sueño Niebla Mental", volver))


def _url_logo(app):
    """El logo, si está guardado en static/img/logo.png (con ?v= para que
    el navegador lo actualice cuando cambie)."""
    ruta = os.path.join(app.static_folder, "img", "logo-64.png")
    if not os.path.exists(ruta):
        return None
    return url_for("static", filename="img/logo-64.png", v=int(os.path.getmtime(ruta)))


# Qué icono de la barra de navegación se ilumina en cada parte de la app
SECCION_DE = {
    "eventos": "agenda", "google": "agenda",
    "tareas": "tareas", "notas": "notas", "compra": "compra", "diario": "diario", "nutricion": "nutricion",
    "salud": "salud", "medicacion": "salud", "cuerpo": "salud",
    "perfil": "perfil", "auth": "perfil",
}

# Secciones a las que se llega desde el inicio: llevan «← Inicio» arriba
LISTADOS_CON_VOLVER = {"captura.bandeja"}   # el resto ya está en la barra de abajo

# Secciones de la app. Las que tienen "endpoint" ya funcionan;
# el resto aparecen como "Próximamente".
SECCIONES = [
    {"icono": "✅", "titulo": "Tareas", "imagen": "tareas", "endpoint": "tareas.listado", "texto": "Lo que tienes que hacer, con su coste de energía."},
    {"icono": "📝", "titulo": "Notas", "imagen": "notas", "endpoint": "notas.listado", "texto": "Apunta cualquier cosa antes de que se escape."},
    {"icono": "📅", "titulo": "Agenda", "imagen": "agenda", "endpoint": "eventos.agenda", "texto": "Planes y citas médicas, con las preguntas para el médico."},
    {"icono": "📖", "titulo": "Diario", "imagen": "diario", "endpoint": "diario.listado", "texto": "Tus reflexiones, cifradas y solo para ti."},
    {"icono": "🛒", "titulo": "Compra", "imagen": "compra", "endpoint": "compra.listado", "texto": "La lista de la compra, siempre a mano."},
    {"icono": "🥗", "titulo": "Nutrición", "imagen": "nutricion", "endpoint": "nutricion.inicio", "texto": "Comidas, calorías y macros, peso y recetas."},
    {"icono": "💊", "titulo": "Salud", "imagen": "salud", "endpoint": "salud.inicio", "texto": "Síntomas, medicación, pasos y sueño."},
]


def _registrar_rutas_basicas(app):
    @app.get("/")
    @login_required
    def inicio():
        from datetime import time
        from captura import apuntes_pendientes
        from eventos import _eventos_entre
        from formularios import FormularioApunte
        from medicacion import plan_de_hoy
        from models import RegistroActividad, RegistroSueno, Tarea

        hoy = current_user.hoy()
        tareas = db.session.scalars(db.select(Tarea).where(
            Tarea.usuario_id == current_user.id, Tarea.completada.is_(False), Tarea.fecha <= hoy)).all()
        tareas.sort(key=lambda t: (t.fecha == hoy, t.hora is None, t.hora or time.max))   # atrasadas primero
        hechas_hoy = db.session.scalar(db.select(db.func.count(Tarea.id)).where(
            Tarea.usuario_id == current_user.id, Tarea.completada.is_(True), Tarea.fecha == hoy))
        programadas, _ = plan_de_hoy()
        sueno = db.session.scalar(db.select(RegistroSueno).filter_by(usuario_id=current_user.id, fecha=hoy))
        actividad = db.session.scalar(db.select(RegistroActividad).filter_by(usuario_id=current_user.id, fecha=hoy))
        pasos = actividad.pasos if actividad and actividad.pasos is not None else None
        objetivo = current_user.objetivo_pasos or 6000
        return render_template(
            "inicio.html",
            hoy=hoy,
            tareas=tareas,
            hechas_hoy=hechas_hoy,
            eventos=_eventos_entre(hoy, hoy),
            tomas_toca=[p for p in programadas if p["estado"] == "toca"],
            siguiente=next((p for p in programadas if p["estado"] == "pronto"), None),
            tomadas=sum(p["estado"] == "tomada" for p in programadas),
            total_tomas=len(programadas),
            sueno=sueno,
            pasos=pasos,
            objetivo_pasos=objetivo,
            por_ciento_pasos=min(100, round((pasos or 0) * 100 / objetivo)),
            enlace_atajos=_enlace_atajos() if current_user.api_token_hash else None,
            form_apunte=FormularioApunte(),
            num_apuntes=len(apuntes_pendientes()),
        )

    @app.after_request
    def cabeceras_de_seguridad(respuesta):
        """Cabeceras que protegen de ataques habituales en la web."""
        respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
        respuesta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        respuesta.headers.setdefault("X-Frame-Options", "DENY")            # que nadie la meta en un iframe
        respuesta.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
        if app.config.get("SESSION_COOKIE_SECURE"):
            respuesta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return respuesta

    @app.errorhandler(413)
    def archivo_demasiado_grande(_error):
        flash("Ese archivo es demasiado grande (máximo 8 MB).", "error")
        return redirect(url_for("perfil.inicio"))

    @app.get("/privacidad")
    def privacidad():
        return render_template("privacidad.html")

    @app.get("/estado")
    def estado():
        """Comprobación rápida de que la app y la base de datos responden."""
        db.session.execute(db.text("SELECT 1"))
        return {"estado": "ok"}


if __name__ == "__main__":
    # Botón ▶ de PyCharm. Puerto 5050 para no chocar con otras apps
    # (PatzOverlays usa el 5000). debug=True recarga al cambiar código.
    create_app().run(port=int(os.environ.get("FLASK_RUN_PORT", 5050)), debug=True)
