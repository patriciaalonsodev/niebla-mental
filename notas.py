# ══════════════════════════════════════════════════════════════
#  App de organización · notas.py
#  Sección de notas, con etiquetas y buscador
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from extensions import db
from formularios import FormularioNota
from models import Etiqueta, Nota
from utilidades import etiquetas_desde_texto, obtener_propio

bp = Blueprint("notas", __name__, url_prefix="/notas")


@bp.before_request
@login_required
def _requiere_sesion():
    """Todas las páginas de notas necesitan haber iniciado sesión."""


def _guardar(nota, form):
    # No usamos form.populate_obj: "etiquetas" es texto en el formulario
    # pero una lista de objetos en el modelo.
    nota.titulo = form.titulo.data or None
    nota.contenido = form.contenido.data
    nota.fijada = form.fijada.data
    nota.etiquetas = etiquetas_desde_texto(form.etiquetas.data)


def _pintar_listado(form):
    busqueda = request.args.get("q", "").strip()
    etiqueta = request.args.get("etiqueta", "").strip().lower()

    consulta = db.select(Nota).filter_by(usuario_id=current_user.id)
    if busqueda:
        consulta = consulta.filter(
            or_(
                Nota.titulo.icontains(busqueda, autoescape=True),
                Nota.contenido.icontains(busqueda, autoescape=True),
            )
        )
    if etiqueta:
        consulta = consulta.filter(Nota.etiquetas.any(Etiqueta.nombre == etiqueta))
    notas = db.session.scalars(
        consulta.order_by(Nota.fijada.desc(), Nota.actualizado_en.desc())
    ).all()

    # Solo las etiquetas que se usan en alguna nota
    etiquetas = db.session.scalars(
        db.select(Etiqueta)
        .filter(Etiqueta.usuario_id == current_user.id, Etiqueta.notas.any())
        .order_by(Etiqueta.nombre)
    ).all()

    return render_template(
        "notas/listado.html",
        form=form,
        notas=notas,
        etiquetas=etiquetas,
        busqueda=busqueda,
        etiqueta_activa=etiqueta,
    )


# ──────────────────────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────────────────────

@bp.get("/")
def listado():
    return _pintar_listado(FormularioNota())


@bp.post("/nueva")
def nueva():
    form = FormularioNota()
    if not form.validate_on_submit():
        return _pintar_listado(form), 400

    nota = Nota(usuario_id=current_user.id)
    _guardar(nota, form)
    db.session.add(nota)
    db.session.commit()
    flash("Nota guardada 📝", "exito")
    return redirect(url_for("notas.listado"))


@bp.route("/<int:nota_id>/editar", methods=["GET", "POST"])
def editar(nota_id):
    nota = obtener_propio(Nota, nota_id)
    form = FormularioNota(obj=nota)
    if request.method == "GET":
        form.etiquetas.data = ", ".join(e.nombre for e in nota.etiquetas)

    if form.validate_on_submit():
        _guardar(nota, form)
        db.session.commit()
        flash("Nota guardada", "exito")
        return redirect(url_for("notas.listado"))
    return render_template("notas/editar.html", form=form, nota=nota)


@bp.post("/<int:nota_id>/fijar")
def fijar(nota_id):
    nota = obtener_propio(Nota, nota_id)
    nota.fijada = not nota.fijada
    db.session.commit()
    return redirect(url_for("notas.listado"))


@bp.post("/<int:nota_id>/borrar")
def borrar(nota_id):
    nota = obtener_propio(Nota, nota_id)
    db.session.delete(nota)
    db.session.commit()
    flash("Nota borrada", "info")
    return redirect(url_for("notas.listado"))
