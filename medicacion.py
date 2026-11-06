# ══════════════════════════════════════════════════════════════
#  App de organización · medicacion.py
#  Salud: medicamentos, horario de tomas y recordatorios
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from auth import _destino_seguro
from extensions import db
from formularios import FormularioMedicamento
from models import HoraToma, Medicamento, Toma
from utilidades import obtener_propio

bp = Blueprint("medicacion", __name__, url_prefix="/salud/medicacion")

# Durante cuánto tiempo después de la hora se sigue avisando
MARGEN_AVISO = timedelta(hours=3)


@bp.before_request
@login_required
def _requiere_sesion():
    """Todas las páginas de medicación necesitan haber iniciado sesión."""


# ──────────────────────────────────────────────────────────────
# Cálculo del día
# ──────────────────────────────────────────────────────────────

def _medicamentos(solo_activos=False):
    consulta = db.select(Medicamento).filter_by(usuario_id=current_user.id)
    if solo_activos:
        consulta = consulta.filter_by(activo=True)
    medicamentos = db.session.scalars(consulta).all()
    # El nombre va cifrado, así que se ordena aquí y no en la base de datos
    return sorted(medicamentos, key=lambda m: (not m.activo, m.nombre.lower()))


def _tomas_de(fecha, medicamentos):
    if not medicamentos:
        return []
    return db.session.scalars(
        db.select(Toma)
        .where(Toma.medicamento_id.in_([m.id for m in medicamentos]), Toma.fecha == fecha)
        .order_by(Toma.registrada_en)
    ).all()


def plan_de_hoy():
    """Lo que toca hoy.

    Devuelve (programadas, a_demanda):
    - programadas: una entrada por cada hora de cada medicamento activo,
      con estado "tomada", "saltada", "toca" (ya es la hora) o "pronto".
    - a_demanda: medicamentos sin horario, con las tomas de hoy.
    """
    ahora = current_user.ahora()
    hoy = ahora.date()
    medicamentos = _medicamentos(solo_activos=True)
    tomas = _tomas_de(hoy, medicamentos)
    registradas = {(t.medicamento_id, t.hora_prevista): t for t in tomas if t.hora_prevista}

    programadas = []
    for med in medicamentos:
        for hora in med.horas:
            toma = registradas.get((med.id, hora.hora))
            if toma:
                estado = toma.estado
            else:
                estado = "toca" if ahora.time() >= hora.hora else "pronto"
            programadas.append({"medicamento": med, "hora": hora.hora, "toma": toma, "estado": estado})
    programadas.sort(key=lambda p: p["hora"])

    a_demanda = [
        {"medicamento": med, "tomas": [t for t in tomas if t.medicamento_id == med.id]}
        for med in medicamentos
        if med.a_demanda
    ]
    return programadas, a_demanda


def pendientes_ahora():
    """Tomas que ya tocan y no se han marcado (para el inicio y los avisos)."""
    programadas, _ = plan_de_hoy()
    return [p for p in programadas if p["estado"] == "toca"]


def _volver():
    destino = request.form.get("volver")
    return redirect(_destino_seguro(destino) if destino else url_for("medicacion.inicio"))


# ──────────────────────────────────────────────────────────────
# Páginas
# ──────────────────────────────────────────────────────────────

def _pintar(form):
    programadas, a_demanda = plan_de_hoy()
    return render_template(
        "medicacion/inicio.html",
        form=form,
        programadas=programadas,
        a_demanda=a_demanda,
        medicamentos=_medicamentos(),
        hoy=current_user.hoy(),
    )


@bp.get("/")
def inicio():
    return _pintar(FormularioMedicamento())


def _guardar(medicamento, form):
    medicamento.nombre = form.nombre.data
    medicamento.dosis = form.dosis.data or None
    medicamento.instrucciones = form.instrucciones.data or None
    medicamento.horas = [HoraToma(hora=h) for h in form.horas_elegidas()]


@bp.post("/nuevo")
def nuevo():
    form = FormularioMedicamento()
    if not form.validate_on_submit():
        return _pintar(form), 400
    medicamento = Medicamento(usuario_id=current_user.id)
    _guardar(medicamento, form)
    db.session.add(medicamento)
    db.session.commit()
    flash(f"Añadido: {medicamento.nombre} 💊", "exito")
    return redirect(url_for("medicacion.inicio"))


@bp.route("/<int:med_id>/editar", methods=["GET", "POST"])
def editar(med_id):
    medicamento = obtener_propio(Medicamento, med_id)
    if request.method == "GET":
        form = FormularioMedicamento(data={
            "nombre": medicamento.nombre,
            "dosis": medicamento.dosis,
            "instrucciones": medicamento.instrucciones,
            "horas": [h.hora for h in medicamento.horas],
        })
    else:
        form = FormularioMedicamento()
        if form.validate_on_submit():
            # Vaciar antes las horas viejas para no chocar con la restricción única
            medicamento.horas = []
            db.session.flush()
            _guardar(medicamento, form)
            db.session.commit()
            flash("Cambios guardados ✓", "exito")
            return redirect(url_for("medicacion.inicio"))
    return render_template("medicacion/editar.html", form=form, medicamento=medicamento)


@bp.post("/<int:med_id>/pausar")
def pausar(med_id):
    medicamento = obtener_propio(Medicamento, med_id)
    medicamento.activo = not medicamento.activo
    db.session.commit()
    if medicamento.activo:
        flash(f"{medicamento.nombre} vuelve a estar activo.", "info")
    else:
        flash(f"{medicamento.nombre} en pausa: no aparecerá en el día ni te avisará.", "info")
    return redirect(url_for("medicacion.inicio"))


@bp.post("/<int:med_id>/borrar")
def borrar(med_id):
    medicamento = obtener_propio(Medicamento, med_id)
    db.session.delete(medicamento)
    db.session.commit()
    flash("Medicamento borrado.", "info")
    return redirect(url_for("medicacion.inicio"))


# ──────────────────────────────────────────────────────────────
# Tomas
# ──────────────────────────────────────────────────────────────

@bp.post("/<int:med_id>/tomar")
def tomar(med_id):
    """Marca una toma de hoy como tomada o saltada.
    Con «hora» (HH:MM) es una toma del horario; sin ella, a demanda."""
    medicamento = obtener_propio(Medicamento, med_id)
    estado = request.form.get("estado", "tomada")
    if estado not in ("tomada", "saltada"):
        abort(400)
    hoy = current_user.hoy()

    texto_hora = request.form.get("hora", "")
    if texto_hora:
        try:
            hora = datetime.strptime(texto_hora, "%H:%M").time()
        except ValueError:
            abort(400)
        if hora not in {h.hora for h in medicamento.horas}:
            abort(400)
        toma = db.session.scalar(
            db.select(Toma).filter_by(medicamento_id=medicamento.id, fecha=hoy, hora_prevista=hora)
        ) or Toma(medicamento=medicamento, fecha=hoy, hora_prevista=hora)
        toma.estado = estado
        db.session.add(toma)
    else:
        db.session.add(Toma(medicamento=medicamento, fecha=hoy, estado="tomada"))

    db.session.commit()
    if estado == "tomada":
        flash(f"Apuntado: {medicamento.nombre} tomado ✓", "exito")
    return _volver()


@bp.post("/tomas/<int:toma_id>/deshacer")
def deshacer(toma_id):
    toma = db.session.get(Toma, toma_id)
    if toma is None or toma.medicamento.usuario_id != current_user.id:
        abort(404)
    db.session.delete(toma)
    db.session.commit()
    return _volver()


@bp.get("/avisos.json")
def avisos():
    """Tomas que tocan ahora, para los recordatorios del navegador.
    Solo las de las últimas horas, para no avisar de algo de esta mañana
    al abrir la app por la noche."""
    ahora = current_user.ahora()
    resultado = []
    for p in pendientes_ahora():
        momento = datetime.combine(ahora.date(), p["hora"], tzinfo=ahora.tzinfo)
        if ahora - momento <= MARGEN_AVISO:
            med = p["medicamento"]
            resultado.append({
                "clave": f"{ahora.date().isoformat()}-{med.id}-{p['hora'].strftime('%H:%M')}",
                "titulo": f"💊 {med.nombre}" + (f" · {med.dosis}" if med.dosis else ""),
                "texto": f"Toca a las {p['hora'].strftime('%H:%M')}"
                         + (f" · {med.instrucciones}" if med.instrucciones else ""),
            })
    return {"avisos": resultado}
