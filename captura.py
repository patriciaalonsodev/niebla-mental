# ══════════════════════════════════════════════════════════════
#  App de organización · captura.py
#  Captura rápida: apuntar algo en un segundo y ordenarlo después
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from auth import _destino_seguro
from extensions import db
from formularios import FormularioApunte
from models import Apunte, ItemCompra, Nota, Tarea
from utilidades import obtener_propio

bp = Blueprint("captura", __name__, url_prefix="/apuntar")


@bp.before_request
@login_required
def _requiere_sesion():
    """La captura y la bandeja necesitan haber iniciado sesión."""


def apuntes_pendientes():
    """Apuntes sin ordenar del usuario, del más antiguo al más nuevo."""
    return db.session.scalars(
        db.select(Apunte)
        .filter_by(usuario_id=current_user.id)
        .order_by(Apunte.creado_en, Apunte.id)
    ).all()


def _pintar_bandeja(form):
    return render_template("captura/bandeja.html", form=form, apuntes=apuntes_pendientes())


def _primera_linea_y_resto(texto):
    primera, _, resto = texto.partition("\n")
    return primera.strip(), resto.strip()


# ──────────────────────────────────────────────────────────────
# Apuntar
# ──────────────────────────────────────────────────────────────

@bp.get("/")
def bandeja():
    return _pintar_bandeja(FormularioApunte())


@bp.post("/")
def apuntar():
    form = FormularioApunte()
    volver = request.form.get("volver")
    if not form.validate_on_submit():
        if volver:                       # desde el inicio: avisar y volver
            flash(form.texto.errors[0], "error")
            return redirect(_destino_seguro(volver))
        return _pintar_bandeja(form), 400

    db.session.add(Apunte(usuario_id=current_user.id, texto=form.texto.data))
    db.session.commit()
    flash("Apuntado ✓ Lo tienes en la bandeja para ordenarlo cuando puedas.", "exito")
    return redirect(_destino_seguro(volver) if volver else url_for("captura.bandeja"))


# ──────────────────────────────────────────────────────────────
# Ordenar: convertir un apunte en tarea, nota o compra
# ──────────────────────────────────────────────────────────────

def _convertir(apunte_id, crear, mensaje):
    apunte = obtener_propio(Apunte, apunte_id)
    for objeto in crear(apunte.texto):
        db.session.add(objeto)
    db.session.delete(apunte)
    db.session.commit()
    flash(mensaje, "exito")
    return redirect(url_for("captura.bandeja"))


@bp.post("/<int:apunte_id>/a-tarea")
def a_tarea(apunte_id):
    def crear(texto):
        # La primera línea es el título; el resto, las notas de la tarea
        titulo, resto = _primera_linea_y_resto(texto)
        if len(titulo) > 200:
            titulo, resto = titulo[:199] + "…", texto
        yield Tarea(usuario_id=current_user.id, titulo=titulo, notas=resto or None)

    return _convertir(apunte_id, crear, "Pasado a Tareas ✅")


@bp.post("/<int:apunte_id>/a-nota")
def a_nota(apunte_id):
    def crear(texto):
        yield Nota(usuario_id=current_user.id, contenido=texto)

    return _convertir(apunte_id, crear, "Pasado a Notas 📝")


@bp.post("/<int:apunte_id>/a-compra")
def a_compra(apunte_id):
    def crear(texto):
        # Cada línea es un producto: "leche\npan\nfruta" → 3 productos
        for linea in texto.splitlines():
            nombre = linea.strip(" -•*\t")
            if nombre:
                yield ItemCompra(usuario_id=current_user.id, nombre=nombre[:120])

    return _convertir(apunte_id, crear, "Pasado a la lista de la compra 🛒")


@bp.post("/<int:apunte_id>/borrar")
def borrar(apunte_id):
    apunte = obtener_propio(Apunte, apunte_id)
    db.session.delete(apunte)
    db.session.commit()
    return redirect(url_for("captura.bandeja"))
