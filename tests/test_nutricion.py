# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_nutricion.py
#  Plan, comidas, alimentos, peso y recetas con IA (simulada)
# ══════════════════════════════════════════════════════════════

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

import recetas_ia
from conftest import crear_usuario, entrar
from extensions import db
from models import Alimento, Comida, PlanNutricion, RecetaGuardada, RegistroPeso, UsoIA, Usuario
from nutricion import calcular_objetivos


def _hoy():
    return db.session.scalar(db.select(Usuario)).hoy()


def _plan(cliente, **extra):
    datos = {"sexo": "mujer", "edad": "44", "altura_cm": "165", "peso": "68,5",
             "actividad": "ligera", "objetivo": "perder", "accion": "calcular", **extra}
    return cliente.post("/nutricion/plan", data=datos, follow_redirects=True)


def _comer(cliente, **datos):
    base = {"fecha": _hoy().isoformat(), "momento": "comida", "nombre": "Lentejas", "kcal": "450",
            "proteinas": "25", "hidratos": "60", "grasas": "10"}
    return cliente.post("/nutricion/anadir", data={**base, **datos}, follow_redirects=True)


# ── Cálculos ──────────────────────────────────────────────────

def test_calculo_del_plan():
    plan = calcular_objetivos("mujer", 44, 165, 68.5, "ligera", "perder")
    # Mifflin-St Jeor: 10·68,5 + 6,25·165 − 5·44 − 161 = 1335,25
    assert plan["basal"] == 1335
    assert plan["kcal"] == 1560                      # 1335,25 × 1,375 × 0,85 ≈ 1560
    assert plan["proteinas_g"] == 110                # 1,6 g por kg
    assert plan["grasas_g"] == 52                    # 30 % de las kcal
    total = plan["proteinas_g"] * 4 + plan["hidratos_g"] * 4 + plan["grasas_g"] * 9
    assert abs(total - plan["kcal"]) < 15            # el reparto cuadra con las calorías


def test_nunca_por_debajo_del_minimo():
    assert calcular_objetivos("mujer", 80, 145, 40, "sedentaria", "perder")["kcal"] == 1200


def test_faltan_datos():
    assert calcular_objetivos("mujer", None, 165, 68, "ligera", "perder") is None


# ── Páginas ───────────────────────────────────────────────────

def test_pide_sesion(cliente):
    for ruta in ("/nutricion/", "/nutricion/plan", "/nutricion/peso", "/nutricion/recetas"):
        assert cliente.get(ruta).status_code == 302


def test_dia_sin_plan(cliente_con_sesion):
    texto = cliente_con_sesion.get("/nutricion/").get_data(as_text=True)
    assert "Aún no tienes plan" in texto and "Desayuno" in texto and "Cena" in texto


def test_guardar_plan_y_peso(cliente_con_sesion):
    texto = _plan(cliente_con_sesion).get_data(as_text=True)
    plan = PlanNutricion.query.one()
    assert (plan.kcal, plan.proteinas_g) == (1560, 110)
    assert RegistroPeso.query.one().kg == 68.5          # «68,5» con coma
    assert "1560" in texto and "Plan guardado" in texto


def test_ajustar_plan_a_mano(cliente_con_sesion):
    _plan(cliente_con_sesion)
    _plan(cliente_con_sesion, accion="guardar", kcal="1800", proteinas_g="90", hidratos_g="200", grasas_g="60")
    plan = PlanNutricion.query.one()
    assert (plan.kcal, plan.proteinas_g, plan.hidratos_g, plan.grasas_g) == (1800, 90, 200, 60)


def test_apuntar_comida_a_mano(cliente_con_sesion):
    _plan(cliente_con_sesion)
    texto = _comer(cliente_con_sesion).get_data(as_text=True)
    comida = Comida.query.one()
    assert (comida.nombre, comida.kcal, comida.momento) == ("Lentejas", 450, "comida")
    assert "Apuntado: Lentejas" in texto and "Te quedan <strong>1110 kcal</strong>" in texto


def test_comida_sin_calorias(cliente_con_sesion):
    respuesta = _comer(cliente_con_sesion, kcal="")
    assert respuesta.status_code == 400 and "Pon las calorías" in respuesta.get_data(as_text=True)
    assert Comida.query.count() == 0


def test_guardar_como_alimento_y_reutilizar(cliente_con_sesion):
    _comer(cliente_con_sesion, nombre="Yogur griego", gramos="125", kcal="150", proteinas="5",
           hidratos="5", grasas="12,5", guardar_alimento="y")
    alimento = Alimento.query.one()
    assert (alimento.kcal, alimento.grasas, alimento.racion_g) == (120, 10, 125)   # por 100 g

    _comer(cliente_con_sesion, alimento=str(alimento.id), gramos="250", nombre="", kcal="")
    segunda = Comida.query.order_by(Comida.id.desc()).first()
    assert (segunda.nombre, segunda.kcal, segunda.grasas) == ("Yogur griego", 300, 25)


def test_alimento_ajeno_no_se_usa(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    ajeno = Alimento(usuario=otra, nombre="Secreto", kcal=100)
    db.session.add(ajeno)
    db.session.commit()
    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)
    respuesta = cliente.post("/nutricion/anadir", data={
        "fecha": "2026-11-06", "momento": "cena", "alimento": str(ajeno.id), "gramos": "100",
    })
    assert respuesta.status_code == 404 and Comida.query.count() == 0
    assert "Secreto" not in cliente.get("/nutricion/anadir").get_data(as_text=True)


def test_te_has_pasado(cliente_con_sesion):
    _plan(cliente_con_sesion)
    _comer(cliente_con_sesion, kcal="2000")
    texto = cliente_con_sesion.get("/nutricion/").get_data(as_text=True)
    assert "Te has pasado <strong>440 kcal</strong>" in texto and "barra-pasada" in texto


def test_repetir_comida_de_ayer(cliente_con_sesion):
    ayer = _hoy() - timedelta(days=1)
    _comer(cliente_con_sesion, fecha=ayer.isoformat(), nombre="Tostadas", momento="desayuno")
    comida = Comida.query.one()
    cliente_con_sesion.post(f"/nutricion/comidas/{comida.id}/repetir")
    hoy = Comida.query.filter_by(fecha=_hoy()).one()
    assert (hoy.nombre, hoy.momento) == ("Tostadas", "desayuno")


def test_peso_y_grafica(cliente_con_sesion):
    for dias, kg in ((20, "70"), (10, "69,2"), (0, "68,4")):
        cliente_con_sesion.post("/nutricion/peso", data={"fecha": (_hoy() - timedelta(days=dias)).isoformat(), "kg": kg})
    texto = cliente_con_sesion.get("/nutricion/peso").get_data(as_text=True)
    assert "<polyline" in texto and "68,4 kg" in texto and "▼ 1,6 kg" in texto
    # El mismo día se corrige, no se duplica
    cliente_con_sesion.post("/nutricion/peso", data={"fecha": _hoy().isoformat(), "kg": "68"})
    assert RegistroPeso.query.count() == 3


def test_peso_imposible(cliente_con_sesion):
    assert cliente_con_sesion.post("/nutricion/peso", data={"fecha": _hoy().isoformat(), "kg": "500"}).status_code == 400
    assert cliente_con_sesion.post("/nutricion/peso", data={
        "fecha": (_hoy() + timedelta(days=1)).isoformat(), "kg": "60"}).status_code == 400
    assert RegistroPeso.query.count() == 0


# ── Recetas con IA (simulada) ─────────────────────────────────

RECETA = {
    "titulo": "Crema de calabacín", "descripcion": "Suave y reconfortante", "raciones": 2,
    "tiempo_minutos": 20, "esfuerzo": "poco",
    "ingredientes": [{"nombre": "Calabacín", "cantidad": "2"}], "pasos": ["Trocear", "Cocer", "Triturar"],
    "kcal": 180, "proteinas": 6, "hidratos": 20, "grasas": 8, "truco": "Haz el doble y congela",
}


class IAFalsa:
    """Imita client.beta.messages.parse del SDK de Anthropic."""

    def __init__(self, stop_reason="end_turn"):
        self.llamadas = []
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self.parse))

    def parse(self, **opciones):
        self.llamadas.append(opciones)
        salida = recetas_ia.Sugerencias(recetas=[recetas_ia.Receta(**RECETA)] * 3)
        return SimpleNamespace(stop_reason=self.stop_reason,
                               parsed_output=None if self.stop_reason == "refusal" else salida)


@pytest.fixture
def ia(app, monkeypatch):
    app.config["ANTHROPIC_API_KEY"] = "clave-de-prueba"
    falsa = IAFalsa()
    monkeypatch.setattr(recetas_ia, "_cliente", lambda: falsa)
    return falsa


def test_recetas_sin_clave(cliente_con_sesion):
    texto = cliente_con_sesion.get("/nutricion/recetas").get_data(as_text=True)
    assert "ANTHROPIC_API_KEY" in texto and "Buscar 3 recetas" not in texto


def test_buscar_recetas(cliente_con_sesion, ia):
    _plan(cliente_con_sesion)
    _comer(cliente_con_sesion, kcal="560")
    texto = cliente_con_sesion.post("/nutricion/recetas/buscar", data={
        "peticion": "algo con calabacín para cenar", "ajustar": "y",
    }).get_data(as_text=True)
    assert texto.count("Crema de calabacín") >= 3 and "180 kcal" in texto
    llamada = ia.llamadas[0]
    assert llamada["model"] == "claude-opus-5-5" and llamada["output_format"] is recetas_ia.Sugerencias
    assert llamada["fallbacks"] == "default"
    assert "1000 kcal" in llamada["messages"][0]["content"]          # lo que le queda hoy
    assert UsoIA.query.one().veces == 1


def test_limite_diario(cliente_con_sesion, ia, app):
    app.config["RECETAS_IA_AL_DIA"] = 1
    cliente_con_sesion.post("/nutricion/recetas/buscar", data={"peticion": "pasta"})
    respuesta = cliente_con_sesion.post("/nutricion/recetas/buscar", data={"peticion": "pasta"})
    assert respuesta.status_code == 429 and "límite de búsquedas" in respuesta.get_data(as_text=True)
    assert len(ia.llamadas) == 1


def test_ia_rechaza(cliente_con_sesion, ia):
    ia.stop_reason = "refusal"
    respuesta = cliente_con_sesion.post("/nutricion/recetas/buscar", data={"peticion": "algo"})
    assert respuesta.status_code == 502 and "no ha querido responder" in respuesta.get_data(as_text=True)


def test_guardar_y_apuntar_receta(cliente_con_sesion):
    cliente_con_sesion.post("/nutricion/recetas/guardar", data={"receta": json.dumps(RECETA)})
    guardada = RecetaGuardada.query.one()
    assert guardada.titulo == "Crema de calabacín"

    cliente_con_sesion.post("/nutricion/recetas/apuntar", data={"guardada": guardada.id, "momento": "cena"})
    comida = Comida.query.one()
    assert (comida.nombre, comida.kcal, comida.momento) == ("Crema de calabacín (1 ración)", 180, "cena")


def test_receta_manipulada_no_se_guarda(cliente_con_sesion):
    texto = cliente_con_sesion.post("/nutricion/recetas/guardar", data={"receta": '{"titulo": "x"}'},
                                    follow_redirects=True).get_data(as_text=True)
    assert "No he podido guardar" in texto and RecetaGuardada.query.count() == 0


def test_receta_ajena(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    ajena = RecetaGuardada(usuario=otra, titulo="Secreta", datos=RECETA)
    db.session.add(ajena)
    db.session.commit()
    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)
    assert "Secreta" not in cliente.get("/nutricion/recetas").get_data(as_text=True)
    assert cliente.post("/nutricion/recetas/apuntar", data={"guardada": ajena.id}).status_code == 404
    assert cliente.post(f"/nutricion/recetas/{ajena.id}/borrar").status_code == 404
