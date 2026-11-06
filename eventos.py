# ══════════════════════════════════════════════════════════════
#  App de organización · eventos.py
#  Agenda: eventos, planes y citas médicas
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from datetime import date, time, timedelta
from itertools import groupby

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from formularios import FormularioEvento
import google_calendar
from models import Evento
from utilidades import DIAS, MESES, fecha_larga, obtener_propio

bp = Blueprint("eventos", __name__, url_prefix="/eventos")

DIAS_POR_PAGINA = 3     # como una agenda de bolsillo


@bp.before_request
@login_required
def _requiere_sesion():
    """Todas las páginas de la agenda necesitan haber iniciado sesión."""


def _orden(evento):
    # Primero los de todo el día, luego por hora
    return (evento.fecha, evento.hora_inicio is not None, evento.hora_inicio or time.min)


def _eventos_entre(desde, hasta=None):
    consulta = db.select(Evento).where(Evento.usuario_id == current_user.id, Evento.fecha >= desde)
    if hasta:
        consulta = consulta.where(Evento.fecha <= hasta)
    return sorted(db.session.scalars(consulta), key=_orden)


def nombre_dia(fecha, hoy):
    if fecha == hoy:
        return "Hoy"
    if fecha == hoy + timedelta(days=1):
        return "Mañana"
    texto = fecha_larga(fecha)
    if fecha.year != hoy.year:
        texto += f" de {fecha.year}"
    return texto[0].upper() + texto[1:]


def proximos_para_inicio():
    """Eventos de hoy y mañana, para el resumen del inicio."""
    hoy = current_user.hoy()
    return [
        (nombre_dia(dia, hoy), list(eventos))
        for dia, eventos in groupby(_eventos_entre(hoy, hoy + timedelta(days=1)), key=lambda e: e.fecha)
    ]


def _pagina_agenda():
    """Los días que se ven en la página, como en una agenda de papel."""
    hoy = current_user.hoy()
    try:
        desde = date.fromisoformat(request.args.get("desde", ""))
    except ValueError:
        desde = hoy
    n = DIAS_POR_PAGINA
    eventos = _eventos_entre(desde, desde + timedelta(days=n - 1))
    dias = []
    for d in (desde + timedelta(days=k) for k in range(n)):
        del_dia = [e for e in eventos if e.fecha == d]
        dias.append({
            "fecha": d,
            "nombre": nombre_dia(d, hoy),
            "semana": DIAS[d.weekday()],
            "mes": MESES[d.month - 1][:3],
            "eventos": del_dia,
            "cucharas": sum(e.coste_energia or 0 for e in del_dia),
            "es_hoy": d == hoy,
            "pasado": d < hoy,
        })
    return {
        "dias": dias,
        "n": n,
        "hoy": hoy,
        "anterior": desde - timedelta(days=n),
        "siguiente": desde + timedelta(days=n),
        "es_pagina_de_hoy": desde == hoy,
    }


def _pintar_formulario(form):
    return render_template("eventos/nuevo.html", form=form)


def _guardar(evento, form):
    form.populate_obj(evento)
    for campo in ("lugar", "notas", "profesional", "preguntas", "resumen"):
        setattr(evento, campo, getattr(evento, campo) or None)


def _volver_al_dia(fecha):
    """Volver a la página de la agenda donde está ese día."""
    if fecha == current_user.hoy():
        return url_for("eventos.agenda")
    return url_for("eventos.agenda", desde=fecha.isoformat())


def _avisar_si_no_llega(evento):
    if not google_calendar.enviar(evento):
        flash("Guardado aquí, pero no ha llegado a Google. Lo reintentaré al sincronizar.", "info")


@bp.get("/")
def agenda():
    google_calendar.sincronizar_si_toca(current_user)
    return render_template("eventos/agenda.html", **_pagina_agenda())


@bp.get("/nuevo")
def formulario_nuevo():
    form = FormularioEvento()
    # Se puede llegar con ?fecha=AAAA-MM-DD&tipo=cita (el «＋» de cada día)
    try:
        form.fecha.data = date.fromisoformat(request.args.get("fecha", ""))
    except ValueError:
        form.fecha.data = current_user.hoy()
    if request.args.get("tipo") == "cita":
        form.tipo.data = "cita"
    return _pintar_formulario(form)


@bp.post("/nuevo")
def nuevo():
    form = FormularioEvento()
    if not form.validate_on_submit():
        return _pintar_formulario(form), 400
    evento = Evento(usuario_id=current_user.id)
    _guardar(evento, form)
    db.session.add(evento)
    db.session.commit()
    flash(("Cita guardada 🩺" if evento.es_cita else "Evento guardado 📅"), "exito")
    _avisar_si_no_llega(evento)
    return redirect(_volver_al_dia(evento.fecha))


@bp.route("/<int:evento_id>/editar", methods=["GET", "POST"])
def editar(evento_id):
    evento = obtener_propio(Evento, evento_id)
    form = FormularioEvento(obj=evento)
    if form.validate_on_submit():
        _guardar(evento, form)
        db.session.commit()
        flash("Cambios guardados ✓", "exito")
        _avisar_si_no_llega(evento)
        return redirect(_volver_al_dia(evento.fecha))
    return render_template(
        "eventos/editar.html", form=form, evento=evento, ya_paso=evento.fecha < current_user.hoy()
    )


@bp.post("/<int:evento_id>/borrar")
def borrar(evento_id):
    evento = obtener_propio(Evento, evento_id)
    if not google_calendar.borrar_en_google(evento):
        flash("Borrado aquí. En Google no se ha podido: bórralo allí a mano si sigue apareciendo.", "info")
    fecha = evento.fecha
    db.session.delete(evento)
    db.session.commit()
    flash("Borrado de la agenda.", "info")
    return redirect(_volver_al_dia(fecha))
