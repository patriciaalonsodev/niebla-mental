# ══════════════════════════════════════════════════════════════
#  App de organización · tareas.py
#  Sección de tareas, con su coste de energía (cucharas)
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

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


def _pintar_listado(form):
    hoy = current_user.hoy()
    pendientes = db.session.scalars(
        db.select(Tarea)
        .filter_by(usuario_id=current_user.id, completada=False)
        .order_by(Tarea.fecha.is_(None), Tarea.fecha, Tarea.creado_en)
    ).all()
    completadas = db.session.scalars(
        db.select(Tarea)
        .filter_by(usuario_id=current_user.id, completada=True)
        .order_by(Tarea.completada_en.desc())
        .limit(15)
    ).all()

    grupos = {
        "anteriores": [t for t in pendientes if t.fecha and t.fecha < hoy],
        "hoy": [t for t in pendientes if t.fecha == hoy],
        "proximas": [t for t in pendientes if t.fecha and t.fecha > hoy],
        "sin_fecha": [t for t in pendientes if t.fecha is None],
    }
    # Cucharas de lo pendiente para hoy (incluye lo que quedó de días anteriores)
    cucharas_hoy = sum(t.coste_energia or 0 for t in grupos["anteriores"] + grupos["hoy"])

    return render_template(
        "tareas/listado.html",
        form=form,
        grupos=grupos,
        completadas=completadas,
        cucharas_hoy=cucharas_hoy,
        hoy=hoy,
    )


# ──────────────────────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────────────────────

@bp.get("/")
def listado():
    form = FormularioTarea()
    form.fecha.data = current_user.hoy()  # por defecto, para hoy
    return _pintar_listado(form)


@bp.post("/nueva")
def nueva():
    form = FormularioTarea()
    if not form.validate_on_submit():
        return _pintar_listado(form), 400

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
    return redirect(url_for("tareas.listado"))


@bp.post("/<int:tarea_id>/borrar")
def borrar(tarea_id):
    tarea = _tarea_propia(tarea_id)
    db.session.delete(tarea)
    db.session.commit()
    flash("Tarea borrada", "info")
    return redirect(url_for("tareas.listado"))
