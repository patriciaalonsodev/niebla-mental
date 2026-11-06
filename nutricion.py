# ══════════════════════════════════════════════════════════════
#  App de organización · nutricion.py
#  Nutrición: plan diario (calorías y macros), comidas, mis
#  alimentos, peso con gráfica y recetas buscadas por IA
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

import json
from datetime import date, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from pydantic import ValidationError
from wtforms.fields.choices import SelectChoice

import recetas_ia

from extensions import db
from formularios import (
    FormularioAlimento, FormularioComida, FormularioPeso, FormularioPlanNutricion, FormularioReceta,
)
from models import (
    MOMENTOS_COMIDA, Alimento, Comida, PlanNutricion, RecetaGuardada, RegistroPeso, UsoIA,
)
from utilidades import obtener_propio

bp = Blueprint("nutricion", __name__, url_prefix="/nutricion")

NOMBRES_MOMENTO = {
    "desayuno": "☕ Desayuno", "media_manana": "🍎 Media mañana", "comida": "🍲 Comida",
    "merienda": "🥪 Merienda", "cena": "🌙 Cena", "picoteo": "🍫 Picoteo",
}
MACROS = (("kcal", "Calorías", "kcal"), ("proteinas", "Proteínas", "g"),
          ("hidratos", "Hidratos", "g"), ("grasas", "Grasas", "g"))


@bp.before_request
@login_required
def _requiere_sesion():
    """Toda la sección de nutrición necesita haber iniciado sesión."""


# ──────────────────────────────────────────────────────────────
# Cálculos (orientativos: no sustituyen a un profesional)
# ──────────────────────────────────────────────────────────────

FACTOR_ACTIVIDAD = {"sedentaria": 1.2, "ligera": 1.375, "moderada": 1.55, "alta": 1.725}
AJUSTE_OBJETIVO = {"perder": -0.15, "mantener": 0.0, "ganar": 0.10}
PROTEINA_POR_KG = {"perder": 1.6, "mantener": 1.3, "ganar": 1.7}
MINIMO_KCAL = {"mujer": 1200, "hombre": 1500}


def calcular_objetivos(sexo, edad, altura_cm, peso_kg, actividad, objetivo):
    """Calorías con la fórmula de Mifflin-St Jeor por la actividad, y
    reparto: proteína según el peso, 30 % de grasas y el resto hidratos.
    Devuelve None si faltan datos."""
    if not all((sexo, edad, altura_cm, peso_kg, actividad, objetivo)):
        return None
    basal = 10 * peso_kg + 6.25 * altura_cm - 5 * edad + (5 if sexo == "hombre" else -161)
    kcal = basal * FACTOR_ACTIVIDAD[actividad] * (1 + AJUSTE_OBJETIVO[objetivo])
    kcal = max(kcal, MINIMO_KCAL[sexo])          # nunca por debajo de un mínimo seguro
    proteinas = PROTEINA_POR_KG[objetivo] * peso_kg
    grasas = kcal * 0.30 / 9
    hidratos = max((kcal - proteinas * 4 - grasas * 9) / 4, 0)
    return {
        "kcal": round(kcal / 10) * 10,
        "proteinas_g": round(proteinas),
        "hidratos_g": round(hidratos),
        "grasas_g": round(grasas),
        "basal": round(basal),
    }


def ultimo_peso():
    return db.session.scalar(
        db.select(RegistroPeso).filter_by(usuario_id=current_user.id).order_by(RegistroPeso.fecha.desc())
    )


def _plan():
    return db.session.scalar(db.select(PlanNutricion).filter_by(usuario_id=current_user.id))


def _fecha_pedida():
    hoy = current_user.hoy()
    try:
        return date.fromisoformat(request.args.get("fecha", ""))
    except ValueError:
        return hoy


def totales(comidas):
    return {clave: sum(getattr(c, clave) or 0 for c in comidas) for clave, _, _ in MACROS}


def resumen_del_dia(fecha):
    """Comidas del día por momento, totales y lo que queda frente al plan."""
    comidas = db.session.scalars(
        db.select(Comida).filter_by(usuario_id=current_user.id, fecha=fecha).order_by(Comida.creado_en)
    ).all()
    plan = _plan()
    objetivo = {
        "kcal": plan.kcal, "proteinas": plan.proteinas_g, "hidratos": plan.hidratos_g, "grasas": plan.grasas_g,
    } if plan and plan.kcal else None
    suma = totales(comidas)
    barras = []
    for clave, nombre, unidad in MACROS:
        meta = objetivo[clave] if objetivo else None
        barras.append({
            "clave": clave, "nombre": nombre, "unidad": unidad, "llevas": suma[clave], "meta": meta,
            "por_ciento": min(round(100 * suma[clave] / meta), 100) if meta else 0,
            "pasado": bool(meta) and suma[clave] > meta * 1.05,
            "queda": (meta - suma[clave]) if meta else None,
        })
    return {
        "por_momento": [(m, NOMBRES_MOMENTO[m], [c for c in comidas if c.momento == m]) for m in MOMENTOS_COMIDA],
        "barras": barras,
        "totales": suma,
        "objetivo": objetivo,
    }


# ──────────────────────────────────────────────────────────────
# El día
# ──────────────────────────────────────────────────────────────

@bp.get("/")
def inicio():
    fecha = _fecha_pedida()
    hoy = current_user.hoy()
    return render_template(
        "nutricion/inicio.html",
        fecha=fecha,
        hoy=hoy,
        dia_anterior=fecha - timedelta(days=1),
        dia_siguiente=fecha + timedelta(days=1),
        grafica=grafica_peso(dias=60),
        **resumen_del_dia(fecha),
    )


def _opciones_alimentos(form):
    alimentos = db.session.scalars(
        db.select(Alimento).filter_by(usuario_id=current_user.id).order_by(Alimento.nombre)
    ).all()
    form.alimento.choices = [SelectChoice("", "— Escribirlo a mano —")] + [
        SelectChoice(str(a.id), f"{a.nombre} ({a.kcal:g} kcal/100 g)") for a in alimentos
    ]
    return alimentos


MACROS_COMIDA = ("kcal", "proteinas", "hidratos", "grasas")


def _numero_o_none(campo):
    return float(campo.data) if campo.data is not None else None


@bp.route("/anadir", methods=["GET", "POST"])
def anadir():
    form = FormularioComida()
    alimentos = _opciones_alimentos(form)
    if request.method == "GET":
        form.fecha.data = _fecha_pedida()
        form.cantidad.data = 1
        if request.args.get("momento") in MOMENTOS_COMIDA:
            form.momento.data = request.args["momento"]
        return _pintar_anadir(form, alimentos)
    if not form.validate_on_submit():
        return _pintar_anadir(form, alimentos), 400

    cantidad = _numero_o_none(form.cantidad) or 1
    gramos = _numero_o_none(form.gramos)
    comida = Comida(usuario_id=current_user.id, fecha=form.fecha.data, momento=form.momento.data,
                    cantidad=cantidad, gramos=gramos, nombre=form.nombre.data or "")
    aviso = None

    if form.alimento.data:
        # 1. De «mis alimentos»: valores por 100 g × gramos
        alimento = obtener_propio(Alimento, form.alimento.data)
        gramos = gramos or ((alimento.racion_g or 0) * cantidad) or None
        if not gramos:
            form.gramos.errors.append("¿Cuántos gramos?")
            return _pintar_anadir(form, alimentos), 400
        comida.nombre, comida.gramos, comida.origen_datos = alimento.nombre, gramos, "alimento"
        for clave in MACROS_COMIDA:
            setattr(comida, clave, round(getattr(alimento, clave) * gramos / 100, 1))

    elif form.kcal.data is not None:
        # 2. Valores escritos a mano
        comida.origen_datos = "manual"
        for clave in MACROS_COMIDA:
            setattr(comida, clave, _numero_o_none(getattr(form, clave)) or 0)
        if form.guardar_alimento.data and gramos:
            db.session.add(Alimento(
                usuario_id=current_user.id, nombre=comida.nombre, racion_g=gramos / cantidad,
                **{c: round(getattr(comida, c) * 100 / gramos, 1) for c in MACROS_COMIDA},
            ))

    elif recetas_ia.disponible():
        # 3. La IA lo calcula (con lo escrito y/o la foto)
        foto = None
        if form.foto.data:
            foto = recetas_ia.preparar_foto(form.foto.data.stream)
            if foto is None:
                form.foto.errors.append("No he podido leer esa foto. Prueba con otra.")
                return _pintar_anadir(form, alimentos), 400
        if _usos_hoy("comidas") >= current_app.config["COMIDAS_IA_AL_DIA"]:
            aviso = "Hoy ya se ha calculado mucho con la IA: lo apunto sin calorías."
        else:
            _contar_uso("comidas")
            try:
                estimacion, origen = recetas_ia.estimar_comida(form.nombre.data, cantidad, gramos, foto)
            except recetas_ia.ErrorRecetas as error:
                aviso = f"{error} Lo apunto sin calorías; puedes volver a intentarlo."
            else:
                comida.nombre = form.nombre.data or estimacion.nombre
                comida.gramos = gramos or estimacion.gramos_totales
                comida.origen_datos = origen
                for clave in MACROS_COMIDA:
                    setattr(comida, clave, round(max(getattr(estimacion, clave), 0), 1))
                aviso = estimacion.nota
    else:
        if form.foto.data:
            form.foto.errors.append("Para leer fotos hace falta activar la IA (ver Recetas).")
            return _pintar_anadir(form, alimentos), 400
        aviso = "Apuntado sin calorías: para calcularlas sola, la app necesita la IA activada."

    comida.nombre = (comida.nombre or "Comida")[:160]
    db.session.add(comida)
    db.session.commit()
    texto = f"Apuntado: {comida.nombre}"
    if comida.origen_datos:
        texto += f" ({comida.kcal:g} kcal)"
    flash(texto + " ✓" + (f" · {aviso}" if aviso else ""), "exito")
    return redirect(_url_dia(comida.fecha))


def _pintar_anadir(form, alimentos):
    return render_template("nutricion/anadir.html", form=form, alimentos=alimentos,
                           ia=recetas_ia.disponible())


def _url_dia(fecha):
    if fecha == current_user.hoy():
        return url_for("nutricion.inicio")
    return url_for("nutricion.inicio", fecha=fecha.isoformat())


@bp.post("/comidas/<int:comida_id>/borrar")
def borrar_comida(comida_id):
    comida = obtener_propio(Comida, comida_id)
    fecha = comida.fecha
    db.session.delete(comida)
    db.session.commit()
    return redirect(_url_dia(fecha))


@bp.post("/comidas/<int:comida_id>/repetir")
def repetir_comida(comida_id):
    """Volver a apuntar algo hoy (lo de siempre en el desayuno, p. ej.)."""
    original = obtener_propio(Comida, comida_id)
    hoy = current_user.hoy()
    db.session.add(Comida(
        usuario_id=current_user.id, fecha=hoy, momento=original.momento, nombre=original.nombre,
        cantidad=original.cantidad, gramos=original.gramos, origen_datos=original.origen_datos,
        kcal=original.kcal, proteinas=original.proteinas, hidratos=original.hidratos, grasas=original.grasas,
    ))
    db.session.commit()
    flash(f"Apuntado hoy: {original.nombre} ✓", "exito")
    return redirect(url_for("nutricion.inicio"))


# ──────────────────────────────────────────────────────────────
# Plan
# ──────────────────────────────────────────────────────────────

@bp.route("/plan", methods=["GET", "POST"])
def plan():
    plan = _plan() or PlanNutricion(usuario_id=current_user.id)
    peso = ultimo_peso()
    if request.method == "GET":
        form = FormularioPlanNutricion(obj=plan)
        if peso:
            form.peso.data = peso.kg
        calculo = calcular_objetivos(plan.sexo, plan.edad, plan.altura_cm, peso.kg if peso else None,
                                     plan.actividad, plan.objetivo)
        return render_template("nutricion/plan.html", form=form, calculo=calculo, plan=plan)

    form = FormularioPlanNutricion()
    if not form.validate_on_submit():
        return render_template("nutricion/plan.html", form=form, calculo=None, plan=plan), 400

    for campo in ("sexo", "edad", "altura_cm", "actividad", "objetivo"):
        setattr(plan, campo, getattr(form, campo).data or None)
    kg = float(form.peso.data) if form.peso.data else None
    if kg:
        _guardar_peso(current_user.hoy(), kg)

    calculo = calcular_objetivos(plan.sexo, plan.edad, plan.altura_cm, kg or (peso.kg if peso else None),
                                 plan.actividad, plan.objetivo)
    recalcular = request.form.get("accion") == "calcular"
    for campo in ("kcal", "proteinas_g", "hidratos_g", "grasas_g"):
        if recalcular and calculo:
            setattr(plan, campo, calculo[campo])
        else:
            setattr(plan, campo, getattr(form, campo).data or (calculo or {}).get(campo))
    db.session.add(plan)
    db.session.commit()
    flash("Plan guardado ✓" if plan.kcal else "Datos guardados. Completa los que faltan para calcular tu plan.", "exito")
    return redirect(url_for("nutricion.plan"))


# ──────────────────────────────────────────────────────────────
# Mis alimentos
# ──────────────────────────────────────────────────────────────

@bp.route("/alimentos", methods=["GET", "POST"])
def alimentos():
    form = FormularioAlimento()
    if form.validate_on_submit():
        alimento = Alimento(usuario_id=current_user.id)
        form.populate_obj(alimento)
        for campo in ("kcal", "proteinas", "hidratos", "grasas", "racion_g"):
            valor = getattr(form, campo).data
            setattr(alimento, campo, float(valor) if valor is not None else (None if campo == "racion_g" else 0))
        db.session.add(alimento)
        db.session.commit()
        flash(f"Guardado: {alimento.nombre} ✓", "exito")
        return redirect(url_for("nutricion.alimentos"))
    lista = db.session.scalars(
        db.select(Alimento).filter_by(usuario_id=current_user.id).order_by(Alimento.nombre)
    ).all()
    return render_template("nutricion/alimentos.html", form=form, alimentos=lista), (400 if form.errors else 200)


@bp.post("/alimentos/<int:alimento_id>/borrar")
def borrar_alimento(alimento_id):
    alimento = obtener_propio(Alimento, alimento_id)
    db.session.delete(alimento)
    db.session.commit()
    return redirect(url_for("nutricion.alimentos"))


# ──────────────────────────────────────────────────────────────
# Peso
# ──────────────────────────────────────────────────────────────

def _guardar_peso(fecha, kg):
    registro = db.session.scalar(
        db.select(RegistroPeso).filter_by(usuario_id=current_user.id, fecha=fecha)
    ) or RegistroPeso(usuario_id=current_user.id, fecha=fecha)
    registro.kg = round(kg, 2)
    db.session.add(registro)


def grafica_peso(dias=90, ancho=320, alto=110, margen=8):
    """Puntos de una gráfica de línea pequeña (SVG, sin librerías)."""
    desde = current_user.hoy() - timedelta(days=dias)
    registros = db.session.scalars(
        db.select(RegistroPeso)
        .where(RegistroPeso.usuario_id == current_user.id, RegistroPeso.fecha >= desde)
        .order_by(RegistroPeso.fecha)
    ).all()
    if not registros:
        return None
    minimo, maximo = min(r.kg for r in registros), max(r.kg for r in registros)
    rango = max(maximo - minimo, 1.0)                     # que 0,2 kg no parezcan una montaña
    centro = (maximo + minimo) / 2
    abajo, arriba = centro - rango / 2 - 0.5, centro + rango / 2 + 0.5
    primero = registros[0].fecha
    total_dias = max((registros[-1].fecha - primero).days, 1)

    def x(r):
        return margen + (ancho - 2 * margen) * ((r.fecha - primero).days / total_dias if len(registros) > 1 else 0.5)

    def y(r):
        return margen + (alto - 2 * margen) * (1 - (r.kg - abajo) / (arriba - abajo))

    puntos = [(round(x(r), 1), round(y(r), 1), r) for r in registros]
    return {
        "ancho": ancho, "alto": alto,
        "linea": " ".join(f"{px},{py}" for px, py, _ in puntos),
        "puntos": puntos,
        "primero": registros[0], "ultimo": registros[-1],
        "diferencia": round(registros[-1].kg - registros[0].kg, 1),
        "minimo": minimo, "maximo": maximo,
    }


@bp.route("/peso", methods=["GET", "POST"])
def peso():
    form = FormularioPeso()
    if request.method == "GET":
        form.fecha.data = current_user.hoy()
    elif form.validate_on_submit():
        if form.fecha.data > current_user.hoy():
            form.fecha.errors.append("No puede ser un día que aún no ha llegado.")
        else:
            _guardar_peso(form.fecha.data, float(form.kg.data))
            db.session.commit()
            flash(f"Peso apuntado: {float(form.kg.data):g} kg ✓", "exito")
            return redirect(url_for("nutricion.peso"))
    registros = db.session.scalars(
        db.select(RegistroPeso).filter_by(usuario_id=current_user.id).order_by(RegistroPeso.fecha.desc()).limit(30)
    ).all()
    return render_template(
        "nutricion/peso.html", form=form, registros=registros, grafica=grafica_peso(dias=180),
    ), (400 if form.errors else 200)


@bp.post("/peso/<int:registro_id>/borrar")
def borrar_peso(registro_id):
    registro = obtener_propio(RegistroPeso, registro_id)
    db.session.delete(registro)
    db.session.commit()
    return redirect(url_for("nutricion.peso"))


# ──────────────────────────────────────────────────────────────
# Recetas con IA
# ──────────────────────────────────────────────────────────────



def _usos_hoy(tipo="recetas"):
    uso = db.session.scalar(
        db.select(UsoIA).filter_by(usuario_id=current_user.id, fecha=current_user.hoy(), tipo=tipo))
    return uso.veces if uso else 0


def _contar_uso(tipo="recetas"):
    hoy = current_user.hoy()
    uso = db.session.scalar(db.select(UsoIA).filter_by(usuario_id=current_user.id, fecha=hoy, tipo=tipo))
    if uso is None:
        uso = UsoIA(usuario_id=current_user.id, fecha=hoy, tipo=tipo, veces=0)
        db.session.add(uso)
    uso.veces += 1
    db.session.commit()


def _pintar_recetas(form, sugerencias=None, error=None, codigo=200):
    guardadas = db.session.scalars(
        db.select(RecetaGuardada).filter_by(usuario_id=current_user.id).order_by(RecetaGuardada.creado_en.desc())
    ).all()
    limite = current_app.config["RECETAS_IA_AL_DIA"]
    return render_template(
        "nutricion/recetas.html",
        form=form,
        sugerencias=sugerencias,
        error=error,
        guardadas=guardadas,
        disponible=recetas_ia.disponible(),
        quedan=max(limite - _usos_hoy(), 0),
        momentos=NOMBRES_MOMENTO,
    ), codigo


@bp.get("/recetas")
def recetas():
    return _pintar_recetas(FormularioReceta())


@bp.post("/recetas/buscar")
def buscar_recetas():
    form = FormularioReceta()
    if not recetas_ia.disponible():
        return _pintar_recetas(form, error="Las recetas con IA no están activadas.", codigo=400)
    if not form.validate_on_submit():
        return _pintar_recetas(form, codigo=400)
    if _usos_hoy() >= current_app.config["RECETAS_IA_AL_DIA"]:
        return _pintar_recetas(form, error="Has llegado al límite de búsquedas de hoy. Mañana más 💜", codigo=429)

    restante = None
    if form.ajustar.data:
        resumen = resumen_del_dia(current_user.hoy())
        if resumen["objetivo"]:
            restante = {b["clave"]: b["queda"] for b in resumen["barras"]}
    _contar_uso()          # se cuenta aunque falle: la llamada a la IA ya se ha hecho
    try:
        sugerencias = recetas_ia.pedir_recetas(form.peticion.data, restante)
    except recetas_ia.ErrorRecetas as error:
        return _pintar_recetas(form, error=str(error), codigo=502)
    return _pintar_recetas(form, sugerencias=sugerencias)


def _receta_del_formulario():
    """La receta llega como JSON en un campo oculto: se valida entera."""
    texto = request.form.get("receta", "")
    if len(texto) > 30_000:
        return None
    try:
        return recetas_ia.Receta.model_validate_json(texto)
    except ValidationError:
        return None


@bp.post("/recetas/guardar")
def guardar_receta():
    receta = _receta_del_formulario()
    if receta is None:
        flash("No he podido guardar esa receta.", "error")
    else:
        db.session.add(RecetaGuardada(
            usuario_id=current_user.id, titulo=receta.titulo[:200], datos=receta.model_dump(),
        ))
        db.session.commit()
        flash(f"Receta guardada: {receta.titulo} ⭐", "exito")
    return redirect(url_for("nutricion.recetas"))


@bp.post("/recetas/apuntar")
def apuntar_receta():
    """Apuntar hoy una ración de una receta (sugerida o guardada)."""
    guardada_id = request.form.get("guardada", type=int)
    if guardada_id:
        receta = recetas_ia.Receta.model_validate(obtener_propio(RecetaGuardada, guardada_id).datos)
    else:
        receta = _receta_del_formulario()
    momento = request.form.get("momento", "comida")
    if receta is None or momento not in MOMENTOS_COMIDA:
        flash("No he podido apuntar esa receta.", "error")
        return redirect(url_for("nutricion.recetas"))
    db.session.add(Comida(
        usuario_id=current_user.id, fecha=current_user.hoy(), momento=momento,
        nombre=f"{receta.titulo} (1 ración)"[:160], cantidad=1, origen_datos="ia",
        kcal=receta.kcal, proteinas=receta.proteinas,
        hidratos=receta.hidratos, grasas=receta.grasas,
    ))
    db.session.commit()
    flash(f"Apuntada una ración de {receta.titulo} ✓", "exito")
    return redirect(url_for("nutricion.inicio"))


@bp.post("/recetas/<int:receta_id>/borrar")
def borrar_receta(receta_id):
    receta = obtener_propio(RecetaGuardada, receta_id)
    db.session.delete(receta)
    db.session.commit()
    return redirect(url_for("nutricion.recetas"))


@bp.app_template_filter("receta_json")
def receta_json(receta):
    datos = receta.model_dump() if hasattr(receta, "model_dump") else receta
    return json.dumps(datos, ensure_ascii=False)
