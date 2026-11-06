# ══════════════════════════════════════════════════════════════
#  App de organización · salud.py
#  Salud: registro diario de síntomas
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from formularios import FormularioSintomas
from models import COLUMNAS_SINTOMAS, RegistroSintomas

bp = Blueprint("salud", __name__, url_prefix="/salud")

DIAS_HISTORIAL = 14

# Qué significa cada escala. "peor_si_alto": en casi todas, 10 es lo
# peor; en sueño y ánimo, 10 es lo mejor (sirve para los colores).
SINTOMAS = [
    {"clave": "dolor", "icono": "⚡", "pregunta": "¿Cuánto dolor tienes?",
     "bajo": "Nada", "alto": "Insoportable", "peor_si_alto": True},
    {"clave": "fatiga", "icono": "🔋", "pregunta": "¿Cuánto cansancio?",
     "bajo": "Con energía", "alto": "Agotamiento", "peor_si_alto": True},
    {"clave": "sueno", "icono": "😴", "pregunta": "¿Qué tal has dormido?",
     "bajo": "Fatal", "alto": "Genial", "peor_si_alto": False},
    {"clave": "niebla", "icono": "🌫️", "pregunta": "¿Cuánta niebla mental?",
     "bajo": "Mente clara", "alto": "Mucha niebla", "peor_si_alto": True},
    {"clave": "rigidez", "icono": "🦴", "pregunta": "¿Cuánta rigidez?",
     "bajo": "Ninguna", "alto": "Mucha", "peor_si_alto": True},
    {"clave": "animo", "icono": "💜", "pregunta": "¿Cómo está tu ánimo?",
     "bajo": "Muy bajo", "alto": "Muy bueno", "peor_si_alto": False},
]
assert tuple(s["clave"] for s in SINTOMAS) == COLUMNAS_SINTOMAS


def nivel(sintoma, valor):
    """"bien", "regular" o "mal" según el valor y el sentido de la escala."""
    if valor is None:
        return None
    malestar = valor if sintoma["peor_si_alto"] else 10 - valor
    return "bien" if malestar <= 3 else "regular" if malestar <= 6 else "mal"


@bp.before_request
@login_required
def _requiere_sesion():
    """Todas las páginas de salud necesitan haber iniciado sesión."""


@bp.app_template_global()
def nivel_sintoma(sintoma, valor):
    return nivel(sintoma, valor)


def _fecha_pedida():
    """Día que se quiere ver o registrar (?fecha=AAAA-MM-DD). Por
    defecto hoy; no se permiten días futuros."""
    hoy = current_user.hoy()
    try:
        fecha = date.fromisoformat(request.args.get("fecha", ""))
    except ValueError:
        return hoy
    return min(fecha, hoy)


def _registro_del_dia(fecha):
    return db.session.scalar(
        db.select(RegistroSintomas).filter_by(usuario_id=current_user.id, fecha=fecha)
    )


def _pintar(form, fecha):
    hoy = current_user.hoy()
    desde = hoy - timedelta(days=DIAS_HISTORIAL - 1)
    registros = {
        r.fecha: r
        for r in db.session.scalars(
            db.select(RegistroSintomas).where(
                RegistroSintomas.usuario_id == current_user.id,
                RegistroSintomas.fecha >= desde,
            )
        )
    }
    historial = [(hoy - timedelta(days=n), registros.get(hoy - timedelta(days=n)))
                 for n in range(DIAS_HISTORIAL)]
    return render_template(
        "salud/inicio.html",
        form=form,
        fecha=fecha,
        hoy=hoy,
        dia_anterior=fecha - timedelta(days=1),
        dia_siguiente=fecha + timedelta(days=1) if fecha < hoy else None,
        sintomas=SINTOMAS,
        historial=historial,
        ya_registrado=_registro_del_dia(fecha) is not None,
    )


@bp.get("/")
def inicio():
    fecha = _fecha_pedida()
    return _pintar(FormularioSintomas(obj=_registro_del_dia(fecha)), fecha)


@bp.post("/sintomas")
def guardar_sintomas():
    fecha = _fecha_pedida()
    form = FormularioSintomas()
    if not form.validate_on_submit():
        return _pintar(form, fecha), 400

    registro = _registro_del_dia(fecha) or RegistroSintomas(
        usuario_id=current_user.id, fecha=fecha
    )
    form.populate_obj(registro)
    registro.notas = registro.notas or None

    if registro.esta_vacio():
        # Nada marcado: no guardar un registro vacío (y quitarlo si existía)
        if registro.id:
            db.session.delete(registro)
            db.session.commit()
            flash("Registro del día borrado.", "info")
        else:
            flash("No has marcado nada, así que no se ha guardado.", "info")
    else:
        db.session.add(registro)
        db.session.commit()
        flash("Guardado ✓ Gracias por cuidarte 💜", "exito")

    if fecha == current_user.hoy():
        return redirect(url_for("salud.inicio"))
    return redirect(url_for("salud.inicio", fecha=fecha.isoformat()))
