# ══════════════════════════════════════════════════════════════
#  App de organización · perfil.py
#  Perfil: datos de la cuenta, aspecto y conexiones
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from io import BytesIO

from flask import Blueprint, abort, flash, redirect, render_template, send_file, url_for
from flask_login import current_user, login_required
from PIL import Image, ImageOps, UnidentifiedImageError

import google_calendar
from api_salud import crear_clave
from extensions import db
from models import RegistroActividad, RegistroSueno
from formularios import FormularioFoto, FormularioPerfil

LADO_FOTO = 256          # píxeles: suficiente para un avatar y pesa muy poco

bp = Blueprint("perfil", __name__, url_prefix="/perfil")


@bp.before_request
@login_required
def _requiere_sesion():
    """El perfil necesita haber iniciado sesión."""


def _ultimo_envio_del_reloj():
    """Cuándo llegaron por última vez datos del reloj."""
    fechas = [
        db.session.scalar(
            db.select(db.func.max(modelo.actualizado_en)).where(
                modelo.usuario_id == current_user.id, modelo.origen == "reloj")
        )
        for modelo in (RegistroActividad, RegistroSueno)
    ]
    fechas = [f for f in fechas if f]
    return max(fechas) if fechas else None


def _pintar(form, clave_nueva=None):
    return render_template(
        "perfil/inicio.html",
        form=form,
        form_foto=FormularioFoto(),
        google=google_calendar.estado_conexion(current_user),
        clave_nueva=clave_nueva,
        url_api=url_for("api_salud.recibir", _external=True),
        ultimo_envio=_ultimo_envio_del_reloj(),
    )


@bp.get("/")
def inicio():
    return _pintar(FormularioPerfil(obj=current_user))


@bp.post("/")
def guardar():
    form = FormularioPerfil()
    if not form.validate_on_submit():
        return _pintar(form), 400
    current_user.nombre = form.nombre.data
    current_user.tema = form.tema.data
    current_user.zona_horaria = form.zona_horaria.data
    db.session.commit()
    flash("Perfil guardado ✓", "exito")
    return redirect(url_for("perfil.inicio"))


# ──────────────────────────────────────────────────────────────
# Foto de perfil
# ──────────────────────────────────────────────────────────────

def preparar_foto(archivo):
    """Comprueba que es una imagen de verdad, la gira según el móvil,
    la recorta en cuadrado y la reduce. Devuelve bytes WebP o None."""
    try:
        with Image.open(archivo) as imagen:
            imagen.verify()                      # que no sea un archivo disfrazado
        archivo.seek(0)
        with Image.open(archivo) as imagen:
            if imagen.width * imagen.height > 50_000_000:
                return None                      # demasiado grande para procesarla
            imagen = ImageOps.exif_transpose(imagen).convert("RGB")
            imagen = ImageOps.fit(imagen, (LADO_FOTO, LADO_FOTO), Image.Resampling.LANCZOS)
            salida = BytesIO()
            imagen.save(salida, "WEBP", quality=85)   # sin datos EXIF (ni GPS)
            return salida.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


@bp.post("/foto")
def subir_foto():
    form = FormularioFoto()
    if not form.validate_on_submit():
        for error in form.foto.errors:
            flash(error, "error")
        return redirect(url_for("perfil.inicio"))
    datos = preparar_foto(form.foto.data.stream)
    if datos is None:
        flash("No he podido leer esa imagen. Prueba con una foto JPG o PNG.", "error")
        return redirect(url_for("perfil.inicio"))
    current_user.foto = datos
    current_user.foto_version = (current_user.foto_version or 0) + 1
    db.session.commit()
    flash("¡Foto de perfil puesta! 📸", "exito")
    return redirect(url_for("perfil.inicio"))


@bp.post("/foto/quitar")
def quitar_foto():
    current_user.foto = None
    current_user.foto_version = (current_user.foto_version or 0) + 1
    db.session.commit()
    flash("Foto quitada.", "info")
    return redirect(url_for("perfil.inicio"))


@bp.get("/foto")
def foto():
    """Solo se sirve la foto propia (va en la sesión, no en la URL)."""
    if not current_user.foto:
        abort(404)
    respuesta = send_file(BytesIO(current_user.foto), mimetype="image/webp")
    # La URL lleva ?v=N, así que se puede guardar en caché sin miedo
    respuesta.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return respuesta


# ──────────────────────────────────────────────────────────────
# Reloj: clave personal para Apple Salud (Atajos) o Android
# ──────────────────────────────────────────────────────────────

@bp.post("/reloj/clave")
def clave_reloj():
    """Crea (o renueva) la clave. Se enseña una sola vez, en esta
    respuesta: no se guarda en claro en ningún sitio."""
    clave = crear_clave(current_user)
    db.session.commit()
    return _pintar(FormularioPerfil(obj=current_user), clave_nueva=clave)


@bp.post("/reloj/quitar")
def quitar_reloj():
    current_user.api_token_hash = None
    current_user.api_token_creado = None
    db.session.commit()
    flash("Reloj desconectado: la clave ya no sirve. Tus datos se quedan.", "info")
    return redirect(url_for("perfil.inicio"))


@bp.get("/reloj/guia")
def guia_reloj():
    return render_template("perfil/guia_reloj.html", url_api=url_for("api_salud.recibir", _external=True))
