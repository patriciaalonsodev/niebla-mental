# ══════════════════════════════════════════════════════════════
#  App de organización · diario.py
#  Diario personal (el texto se guarda cifrado)
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

import unicodedata

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from wtforms.fields.choices import SelectChoice

from extensions import db
from formularios import ESTADOS_ANIMO, FormularioDiario
from models import EntradaDiario, Etiqueta
from utilidades import etiquetas_desde_texto, obtener_propio

bp = Blueprint("diario", __name__, url_prefix="/diario")



@bp.before_request
@login_required
def _requiere_sesion():
    """Todas las páginas del diario necesitan haber iniciado sesión."""


@bp.app_template_global()
def emoji_animo(valor):
    return ESTADOS_ANIMO[valor] if valor in ESTADOS_ANIMO else None


def _normalizar(texto):
    """Minúsculas y sin tildes, para que «dolor» encuentre «Dolor» y
    «medico» encuentre «médico»."""
    sin_tildes = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")


def _guardar(entrada, form):
    entrada.fecha = form.fecha.data
    entrada.estado_animo = form.estado_animo.data
    entrada.pregunta_guia = form.pregunta_guia.data
    entrada.contenido = form.contenido.data
    entrada.etiquetas = etiquetas_desde_texto(form.etiquetas.data)


def _fecha_valida(form):
    """No se escribe en días futuros."""
    if form.fecha.data and form.fecha.data > current_user.hoy():
        form.fecha.errors.append("No puede ser un día que aún no ha llegado.")
        return False
    return True


def _entradas_filtradas(busqueda, etiqueta):
    """Entradas del usuario de la más antigua a la más nueva, como las
    páginas de un diario de papel."""
    consulta = db.select(EntradaDiario).filter_by(usuario_id=current_user.id)
    if etiqueta:
        consulta = consulta.filter(EntradaDiario.etiquetas.any(Etiqueta.nombre == etiqueta))
    entradas = db.session.scalars(
        consulta.order_by(EntradaDiario.fecha, EntradaDiario.creado_en)
    ).all()
    if busqueda:
        # El texto está cifrado en la base de datos: se busca después de descifrarlo
        buscado = _normalizar(busqueda)
        entradas = [
            e for e in entradas
            if buscado in _normalizar(e.contenido) or buscado in _normalizar(e.pregunta_guia or "")
        ]
    return entradas


@bp.get("/")
def listado():
    """Una entrada por página. Sin indicar página, se abre por la última
    (lo más reciente), como cuando abres tu diario para seguir escribiendo."""
    busqueda = request.args.get("q", "").strip()
    etiqueta = request.args.get("etiqueta", "").strip().lower()
    entradas = _entradas_filtradas(busqueda, etiqueta)
    total = len(entradas)
    try:
        pagina = int(request.args.get("pagina", total))
    except ValueError:
        pagina = total
    pagina = min(max(pagina, 1), total) if total else 0

    etiquetas = db.session.scalars(
        db.select(Etiqueta)
        .filter(Etiqueta.usuario_id == current_user.id, Etiqueta.entradas_diario.any())
        .order_by(Etiqueta.nombre)
    ).all()
    filtros = {"q": busqueda or None, "etiqueta": etiqueta or None}
    return render_template(
        "diario/listado.html",
        entrada=entradas[pagina - 1] if total else None,
        pagina=pagina,
        total=total,
        filtros=filtros,
        etiquetas=etiquetas,
        busqueda=busqueda,
        etiqueta_activa=etiqueta,
        sin_entradas=total == 0 and not busqueda and not etiqueta,
        anio_actual=current_user.hoy().year,
    )


def _pintar_nueva(form):
    return render_template("diario/nueva.html", form=form)


@bp.get("/nueva")
def formulario_nueva():
    return _pintar_nueva(FormularioDiario(fecha=current_user.hoy()))


@bp.post("/nueva")
def nueva():
    form = FormularioDiario()
    if not (form.validate_on_submit() and _fecha_valida(form)):
        return _pintar_nueva(form), 400
    entrada = EntradaDiario(usuario_id=current_user.id)
    _guardar(entrada, form)
    db.session.add(entrada)
    db.session.commit()
    flash("Guardado en tu diario 📖", "exito")
    return redirect(_pagina_de(entrada))


def _pagina_de(entrada):
    """URL de la página del diario donde queda esa entrada."""
    ids = [e.id for e in _entradas_filtradas("", "")]
    return url_for("diario.listado", pagina=ids.index(entrada.id) + 1)


@bp.route("/<int:entrada_id>/editar", methods=["GET", "POST"])
def editar(entrada_id):
    entrada = obtener_propio(EntradaDiario, entrada_id)
    if request.method == "GET":
        form = FormularioDiario(obj=entrada)
        form.etiquetas.data = ", ".join(e.nombre for e in entrada.etiquetas)
    else:
        form = FormularioDiario()
        if form.validate_on_submit() and _fecha_valida(form):
            _guardar(entrada, form)
            db.session.commit()
            flash("Cambios guardados ✓", "exito")
            return redirect(_pagina_de(entrada))

    # Si la entrada usaba una pregunta que ya no está en la lista, mostrarla igual
    actual = form.pregunta_guia.data
    if actual and actual not in [c.value for c in form.pregunta_guia.choices]:
        form.pregunta_guia.choices = [*form.pregunta_guia.choices, SelectChoice(actual, actual)]
    return render_template("diario/editar.html", form=form, entrada=entrada)


@bp.post("/<int:entrada_id>/borrar")
def borrar(entrada_id):
    entrada = obtener_propio(EntradaDiario, entrada_id)
    db.session.delete(entrada)
    db.session.commit()
    flash("Entrada borrada.", "info")
    return redirect(url_for("diario.listado"))
