# ══════════════════════════════════════════════════════════════
#  App de organización · tareas.py
#  Sección de tareas, con su coste de energía (cucharas)
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from datetime import date, time

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from auth import _destino_seguro
from extensions import db
from formularios import FormularioTarea
from models import Tarea
from utilidades import obtener_propio

bp = Blueprint("tareas", __name__, url_prefix="/tareas")


@bp.before_request
@login_required
def _requiere_sesion():
    """Todas las páginas de tareas necesitan haber iniciado sesión."""


def _tarea_propia(tarea_id):
    return obtener_propio(Tarea, tarea_id)


def _pintar_listado():
    """Solo la lista: pendientes (las atrasadas y las de hoy primero) y,
    debajo, las últimas hechas."""
    pendientes = db.session.scalars(
        db.select(Tarea).filter_by(usuario_id=current_user.id, completada=False)
    ).all()
    pendientes.sort(key=lambda t: (t.fecha is None, t.fecha or date.max, t.hora is None, t.hora or time.max, t.creado_en))
    completadas = db.session.scalars(
        db.select(Tarea)
        .filter_by(usuario_id=current_user.id, completada=True)
        .order_by(Tarea.completada_en.desc())
        .limit(15)
    ).all()
    return render_template(
        "tareas/listado.html", pendientes=pendientes, completadas=completadas, hoy=current_user.hoy(),
    )


def _pintar_nueva(form):
    return render_template("tareas/nueva.html", form=form)


# ──────────────────────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────────────────────

@bp.get("/")
def listado():
    return _pintar_listado()


@bp.get("/nueva")
def formulario_nueva():
    form = FormularioTarea()
    form.fecha.data = current_user.hoy()  # por defecto, para hoy
    return _pintar_nueva(form)


@bp.post("/nueva")
def nueva():
    form = FormularioTarea()
    if not form.validate_on_submit():
        return _pintar_nueva(form), 400

    tarea = Tarea(usuario_id=current_user.id)
    form.populate_obj(tarea)
    db.session.add(tarea)
    db.session.commit()
    flash("Tarea apuntada ✅", "exito")
    return redirect(url_for("tareas.listado"))


@bp.route("/<int:tarea_id>/editar", methods=["GET", "POST"])
def editar(tarea_id):
    tarea = _tarea_propia(tarea_id)
    form = FormularioTarea(obj=tarea)
    if form.validate_on_submit():
        form.populate_obj(tarea)
        db.session.commit()
        flash("Tarea guardada", "exito")
        return redirect(url_for("tareas.listado"))
    return render_template("tareas/editar.html", form=form, tarea=tarea)


@bp.post("/<int:tarea_id>/completar")
def completar(tarea_id):
    tarea = _tarea_propia(tarea_id)
    tarea.marcar_completada(not tarea.completada)
    db.session.commit()
    destino = request.form.get("volver")
    return redirect(_destino_seguro(destino) if destino else url_for("tareas.listado"))


@bp.post("/<int:tarea_id>/borrar")
def borrar(tarea_id):
    tarea = _tarea_propia(tarea_id)
    db.session.delete(tarea)
    db.session.commit()
    flash("Tarea borrada", "info")
    return redirect(url_for("tareas.listado"))
