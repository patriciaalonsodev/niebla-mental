# ══════════════════════════════════════════════════════════════
#  App de organización · cuerpo.py
#  Salud: actividad (pasos, ejercicio) y sueño
#  Los datos llegan a mano o desde el reloj (Apple Salud vía
#  Atajos, o Android) por la entrada de api_salud.py
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from datetime import date, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from formularios import (
    TIPOS_EJERCICIO, FormularioActividad, FormularioEjercicio, FormularioObjetivoPasos, FormularioSueno,
)
from models import Ejercicio, RegistroActividad, RegistroSueno
from utilidades import obtener_propio

bp = Blueprint("cuerpo", __name__, url_prefix="/salud")

DIAS_GRAFICA = 7
HORAS_SUENO_RECOMENDADAS = 7.5


@bp.before_request
@login_required
def _requiere_sesion():
    """Actividad y sueño necesitan haber iniciado sesión."""


# ──────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────

def _fecha(campo="fecha"):
    try:
        return min(date.fromisoformat(request.args.get(campo, "")), current_user.hoy())
    except ValueError:
        return current_user.hoy()


def barras_semana(valores_por_dia, hoy, objetivo=None, ancho=320, alto=120):
    """Datos para una gráfica de barras de 7 días (SVG, sin librerías).
    valores_por_dia: {fecha: número}."""
    dias = [hoy - timedelta(days=n) for n in range(DIAS_GRAFICA - 1, -1, -1)]
    valores = [valores_por_dia.get(d) or 0 for d in dias]
    tope = max(max(valores, default=0), objetivo or 0, 1) * 1.1
    hueco = ancho / DIAS_GRAFICA
    barras = []
    for i, (d, v) in enumerate(zip(dias, valores)):
        altura = (alto - 22) * v / tope
        barras.append({
            "x": round(i * hueco + hueco * 0.18, 1), "ancho": round(hueco * 0.64, 1),
            "y": round(alto - 18 - altura, 1), "alto": round(altura, 1),
            "valor": v, "fecha": d, "dia": "LMXJVSD"[d.weekday()],   # X = miércoles, como en los calendarios
            "texto_x": round(i * hueco + hueco / 2, 1), "es_hoy": d == hoy,
            "llega": bool(objetivo) and v >= objetivo,
        })
    linea = round(alto - 18 - (alto - 22) * objetivo / tope, 1) if objetivo else None
    return {"ancho": ancho, "alto": alto, "barras": barras, "linea_objetivo": linea}


def horas_y_minutos(minutos):
    if minutos is None:
        return "—"
    return f"{minutos // 60} h {minutos % 60:02d} min"


@bp.app_template_filter("horas_minutos")
def _filtro_horas(minutos):
    return horas_y_minutos(minutos)


def guardar_actividad(usuario_id, fecha, origen, **valores):
    """Crea o completa el registro del día (solo cambia lo que llega)."""
    registro = db.session.scalar(
        db.select(RegistroActividad).filter_by(usuario_id=usuario_id, fecha=fecha)
    ) or RegistroActividad(usuario_id=usuario_id, fecha=fecha)
    for clave, valor in valores.items():
        if valor is not None:
            setattr(registro, clave, valor)
    registro.origen = origen
    db.session.add(registro)
    return registro


def guardar_sueno(usuario_id, fecha, origen, **valores):
    registro = db.session.scalar(
        db.select(RegistroSueno).filter_by(usuario_id=usuario_id, fecha=fecha)
    ) or RegistroSueno(usuario_id=usuario_id, fecha=fecha)
    for clave, valor in valores.items():
        if valor is not None:
            setattr(registro, clave, valor)
    registro.origen = origen
    db.session.add(registro)
    return registro


def minutos_entre(acostarse, levantarse):
    """23:40 → 07:10 = 450 minutos (pasando la medianoche)."""
    inicio = datetime.combine(date.min, acostarse)
    fin = datetime.combine(date.min, levantarse)
    if fin <= inicio:
        fin += timedelta(days=1)
    return int((fin - inicio).total_seconds() // 60)


# ──────────────────────────────────────────────────────────────
# Actividad
# ──────────────────────────────────────────────────────────────

def _pintar_actividad(form, form_ejercicio, form_objetivo, codigo=200):
    hoy = current_user.hoy()
    desde = hoy - timedelta(days=DIAS_GRAFICA - 1)
    registros = {
        r.fecha: r for r in db.session.scalars(
            db.select(RegistroActividad).where(
                RegistroActividad.usuario_id == current_user.id, RegistroActividad.fecha >= desde)
        )
    }
    ejercicios = db.session.scalars(
        db.select(Ejercicio).where(Ejercicio.usuario_id == current_user.id, Ejercicio.fecha >= desde)
        .order_by(Ejercicio.fecha.desc(), Ejercicio.creado_en.desc())
    ).all()
    de_hoy = registros.get(hoy)
    pasos_hoy = (de_hoy.pasos if de_hoy else None) or 0
    objetivo = current_user.objetivo_pasos
    return render_template(
        "cuerpo/actividad.html",
        form=form, form_ejercicio=form_ejercicio, form_objetivo=form_objetivo,
        hoy=hoy, de_hoy=de_hoy, pasos_hoy=pasos_hoy, objetivo=objetivo,
        por_ciento=min(round(100 * pasos_hoy / objetivo), 100) if objetivo else 0,
        grafica=barras_semana({d: r.pasos for d, r in registros.items()}, hoy, objetivo),
        media=round(sum(r.pasos or 0 for r in registros.values()) / DIAS_GRAFICA),
        ejercicios=ejercicios,
        minutos_ejercicio_semana=sum(e.minutos for e in ejercicios),
        tipos=TIPOS_EJERCICIO,
    ), codigo


def _formularios_vacios():
    hoy = current_user.hoy()
    form = FormularioActividad(fecha=hoy)
    registro = db.session.scalar(db.select(RegistroActividad).filter_by(usuario_id=current_user.id, fecha=hoy))
    if registro:
        form = FormularioActividad(obj=registro)
    return form, FormularioEjercicio(fecha=hoy), FormularioObjetivoPasos(obj=current_user)


@bp.get("/actividad")
def actividad():
    return _pintar_actividad(*_formularios_vacios())


@bp.post("/actividad")
def guardar_actividad_manual():
    form = FormularioActividad()
    _, form_ejercicio, form_objetivo = _formularios_vacios()
    if not form.validate_on_submit():
        return _pintar_actividad(form, form_ejercicio, form_objetivo, 400)
    guardar_actividad(
        current_user.id, min(form.fecha.data, current_user.hoy()), "manual",
        pasos=form.pasos.data, minutos_activos=form.minutos_activos.data,
        kcal_activas=form.kcal_activas.data,
        distancia_km=float(form.distancia_km.data) if form.distancia_km.data is not None else None,
    )
    db.session.commit()
    flash("Actividad guardada ✓", "exito")
    return redirect(url_for("cuerpo.actividad"))


@bp.post("/actividad/objetivo")
def objetivo_pasos():
    form = FormularioObjetivoPasos()
    if form.validate_on_submit():
        current_user.objetivo_pasos = form.objetivo_pasos.data
        db.session.commit()
        flash(f"Nuevo objetivo: {form.objetivo_pasos.data} pasos al día ✓", "exito")
    else:
        flash(form.objetivo_pasos.errors[0], "error")
    return redirect(url_for("cuerpo.actividad"))


@bp.post("/ejercicio")
def nuevo_ejercicio():
    form_actividad, _, form_objetivo = _formularios_vacios()
    form = FormularioEjercicio()
    if not form.validate_on_submit():
        return _pintar_actividad(form_actividad, form, form_objetivo, 400)
    db.session.add(Ejercicio(
        usuario_id=current_user.id, fecha=min(form.fecha.data, current_user.hoy()), tipo=form.tipo.data,
        minutos=form.minutos.data, intensidad=form.intensidad.data, kcal=form.kcal.data,
    ))
    db.session.commit()
    flash(f"Apuntado: {form.tipo.data}, {form.minutos.data} min 💪", "exito")
    return redirect(url_for("cuerpo.actividad"))


@bp.post("/ejercicio/<int:ejercicio_id>/borrar")
def borrar_ejercicio(ejercicio_id):
    ejercicio = obtener_propio(Ejercicio, ejercicio_id)
    db.session.delete(ejercicio)
    db.session.commit()
    return redirect(url_for("cuerpo.actividad"))


# ──────────────────────────────────────────────────────────────
# Sueño
# ──────────────────────────────────────────────────────────────

def _pintar_sueno(form, codigo=200):
    hoy = current_user.hoy()
    desde = hoy - timedelta(days=DIAS_GRAFICA - 1)
    registros = {
        r.fecha: r for r in db.session.scalars(
            db.select(RegistroSueno).where(RegistroSueno.usuario_id == current_user.id, RegistroSueno.fecha >= desde)
        )
    }
    anoche = registros.get(hoy) or registros.get(hoy - timedelta(days=1))
    con_datos = [r.minutos_dormido for r in registros.values() if r.minutos_dormido]
    fases = None
    if anoche and any((anoche.minutos_profundo, anoche.minutos_rem, anoche.minutos_ligero)):
        total = sum(x or 0 for x in (anoche.minutos_profundo, anoche.minutos_rem,
                                     anoche.minutos_ligero, anoche.minutos_despierto)) or 1
        fases = [
            {"clave": clave, "nombre": nombre, "minutos": minutos or 0, "por_ciento": round(100 * (minutos or 0) / total)}
            for clave, nombre, minutos in (
                ("profundo", "Profundo", anoche.minutos_profundo), ("rem", "REM", anoche.minutos_rem),
                ("ligero", "Ligero", anoche.minutos_ligero), ("despierto", "Despierto", anoche.minutos_despierto),
            )
        ]
    return render_template(
        "cuerpo/sueno.html",
        form=form, hoy=hoy, anoche=anoche, fases=fases,
        grafica=barras_semana({d: round((r.minutos_dormido or 0) / 60, 1) for d, r in registros.items()},
                              hoy, HORAS_SUENO_RECOMENDADAS),
        media=round(sum(con_datos) / len(con_datos)) if con_datos else None,
        recomendadas=HORAS_SUENO_RECOMENDADAS,
    ), codigo


@bp.get("/sueno")
def sueno():
    hoy = current_user.hoy()
    registro = db.session.scalar(db.select(RegistroSueno).filter_by(usuario_id=current_user.id, fecha=hoy))
    form = FormularioSueno(obj=registro) if registro else FormularioSueno(fecha=hoy)
    if registro and registro.minutos_dormido:
        form.horas.data = round(registro.minutos_dormido / 60, 2)
    return _pintar_sueno(form)


@bp.post("/sueno")
def guardar_sueno_manual():
    form = FormularioSueno()
    if not form.validate_on_submit():
        return _pintar_sueno(form, 400)
    minutos = round(float(form.horas.data) * 60) if form.horas.data else None
    if minutos is None and form.hora_acostarse.data and form.hora_levantarse.data:
        minutos = minutos_entre(form.hora_acostarse.data, form.hora_levantarse.data)
    if minutos is None and form.calidad.data is None:
        form.horas.errors.append("Pon las horas dormidas, a qué hora te dormiste y despertaste, o cómo te has levantado.")
        return _pintar_sueno(form, 400)
    guardar_sueno(
        current_user.id, min(form.fecha.data, current_user.hoy()), "manual",
        minutos_dormido=minutos, hora_acostarse=form.hora_acostarse.data,
        hora_levantarse=form.hora_levantarse.data, calidad=form.calidad.data,
        despertares=form.despertares.data,
    )
    db.session.commit()
    flash("Noche guardada ✓ " + (f"Has dormido {horas_y_minutos(minutos)}." if minutos else ""), "exito")
    return redirect(url_for("cuerpo.sueno"))


# ──────────────────────────────────────────────────────────────
# Conectar el reloj y las apps de salud
# ──────────────────────────────────────────────────────────────

def pintar_conectar(clave_nueva=None):
    from perfil import _ultimo_envio_del_reloj
    return render_template(
        "cuerpo/conectar.html",
        clave_nueva=clave_nueva,
        url_api=url_for("api_salud.recibir", _external=True),
        ultimo_envio=_ultimo_envio_del_reloj(),
        volver="salud",
    )


@bp.get("/conectar")
def conectar():
    return pintar_conectar()
