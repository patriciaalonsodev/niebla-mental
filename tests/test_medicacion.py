# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_medicacion.py
#  Medicamentos, tomas del día y avisos
# ══════════════════════════════════════════════════════════════

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from conftest import crear_usuario, entrar
from extensions import db
from models import HoraToma, Medicamento, Toma, Usuario

AHORA = datetime(2026, 11, 6, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))   # viernes, 10:00


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    """Hora fija para que los tests no dependan de cuándo se ejecutan."""
    monkeypatch.setattr(Usuario, "ahora", lambda self: AHORA)


def _nuevo(cliente, nombre="Pregabalina", dosis="75 mg", horas=("09:00", "21:00"), instrucciones=""):
    datos = {"nombre": nombre, "dosis": dosis, "instrucciones": instrucciones}
    for i, h in enumerate(horas):
        datos[f"horas-{i}"] = h
    return cliente.post("/salud/medicacion/nuevo", data=datos, follow_redirects=True)


def _tomar(cliente, med, hora="", estado="tomada", volver=None):
    datos = {"hora": hora, "estado": estado}
    if volver:
        datos["volver"] = volver
    return cliente.post(f"/salud/medicacion/{med.id}/tomar", data=datos)


def test_pide_sesion(cliente):
    assert cliente.get("/salud/medicacion/").status_code == 302
    assert cliente.get("/salud/medicacion/avisos.json").status_code == 302


def test_pagina_vacia(cliente_con_sesion):
    texto = cliente_con_sesion.get("/salud/medicacion/").get_data(as_text=True)
    assert "Aún no tienes medicamentos" in texto
    assert "Hoy, viernes 6 de noviembre" in texto


def test_anadir_medicamento(cliente_con_sesion):
    texto = _nuevo(cliente_con_sesion, horas=("21:00", "09:00", "09:00")).get_data(as_text=True)
    med = Medicamento.query.one()
    assert (med.nombre, med.dosis) == ("Pregabalina", "75 mg")
    assert [h.hora for h in med.horas] == [time(9), time(21)]   # ordenadas y sin repetir
    assert "Añadido: Pregabalina" in texto
    # 09:00 ya ha pasado (son las 10:00) → toca; 21:00 → todavía no
    assert texto.index("09:00") < texto.index("21:00")
    assert "⏰ Te toca" in texto


def test_nombre_y_dosis_cifrados(cliente_con_sesion):
    _nuevo(cliente_con_sesion, nombre="Duloxetina", dosis="60 mg")
    fila = db.session.execute(db.text("SELECT nombre, dosis FROM medicamentos")).one()
    assert "Duloxetina" not in fila.nombre and "60 mg" not in fila.dosis


def test_nombre_obligatorio(cliente_con_sesion):
    assert _nuevo(cliente_con_sesion, nombre=" ").status_code == 400
    assert Medicamento.query.count() == 0


def test_marcar_tomada_y_deshacer(cliente_con_sesion):
    _nuevo(cliente_con_sesion)
    med = Medicamento.query.one()

    _tomar(cliente_con_sesion, med, "09:00")
    toma = Toma.query.one()
    assert (toma.fecha, toma.hora_prevista, toma.estado) == (date(2026, 11, 6), time(9), "tomada")

    texto = cliente_con_sesion.get("/salud/medicacion/").get_data(as_text=True)
    assert "✓ Tomada" in texto and "⏰ Te toca" not in texto

    # Cambiar de idea: saltada en vez de tomada (no se duplica)
    _tomar(cliente_con_sesion, med, "09:00", estado="saltada")
    assert Toma.query.one().estado == "saltada"

    cliente_con_sesion.post(f"/salud/medicacion/tomas/{toma.id}/deshacer")
    assert Toma.query.count() == 0


def test_hora_que_no_es_del_medicamento(cliente_con_sesion):
    _nuevo(cliente_con_sesion)
    med = Medicamento.query.one()
    assert _tomar(cliente_con_sesion, med, "13:00").status_code == 400
    assert _tomar(cliente_con_sesion, med, "patata").status_code == 400
    assert _tomar(cliente_con_sesion, med, "09:00", estado="raro").status_code == 400
    assert Toma.query.count() == 0


def test_a_demanda(cliente_con_sesion):
    texto = _nuevo(cliente_con_sesion, nombre="Paracetamol", dosis="1 g", horas=()).get_data(as_text=True)
    med = Medicamento.query.one()
    assert med.a_demanda and "Cuando lo necesites" in texto

    _tomar(cliente_con_sesion, med)
    _tomar(cliente_con_sesion, med)
    assert Toma.query.count() == 2                      # se puede tomar varias veces
    texto = cliente_con_sesion.get("/salud/medicacion/").get_data(as_text=True)
    assert "Hoy: 2 veces" in texto


def test_aviso_en_el_inicio(cliente_con_sesion):
    _nuevo(cliente_con_sesion)
    med = Medicamento.query.one()
    texto = cliente_con_sesion.get("/").get_data(as_text=True)
    assert "Medicación" in texto and "Pregabalina" in texto and "09:00" in texto

    respuesta = _tomar(cliente_con_sesion, med, "09:00", volver="/")
    assert respuesta.location == "/"                    # vuelve al inicio
    assert "Tomada" in cliente_con_sesion.get("/").get_data(as_text=True)


def test_avisos_json(cliente_con_sesion):
    _nuevo(cliente_con_sesion, horas=("06:00", "09:00", "21:00"), instrucciones="con comida")
    avisos = cliente_con_sesion.get("/salud/medicacion/avisos.json").get_json()["avisos"]
    # 06:00 fue hace más de 3 horas: ya no se avisa; 21:00 aún no toca
    assert [a["clave"].rsplit("-", 1)[-1] for a in avisos] == ["09:00"]
    assert avisos[0]["titulo"] == "💊 Pregabalina · 75 mg"
    assert "con comida" in avisos[0]["texto"]


def test_pausar(cliente_con_sesion):
    _nuevo(cliente_con_sesion)
    med = Medicamento.query.one()
    cliente_con_sesion.post(f"/salud/medicacion/{med.id}/pausar")
    db.session.refresh(med)
    assert not med.activo
    assert cliente_con_sesion.get("/salud/medicacion/avisos.json").get_json()["avisos"] == []
    assert "Te toca la medicación" not in cliente_con_sesion.get("/").get_data(as_text=True)


def test_editar_cambia_horas(cliente_con_sesion):
    _nuevo(cliente_con_sesion)
    med = Medicamento.query.one()

    texto = cliente_con_sesion.get(f"/salud/medicacion/{med.id}/editar").get_data(as_text=True)
    assert 'value="09:00"' in texto and 'value="21:00"' in texto

    cliente_con_sesion.post(
        f"/salud/medicacion/{med.id}/editar",
        data={"nombre": "Pregabalina", "dosis": "150 mg", "horas-0": "21:00", "horas-1": "08:00"},
    )
    db.session.refresh(med)
    assert med.dosis == "150 mg"
    assert [h.hora for h in med.horas] == [time(8), time(21)]
    assert HoraToma.query.count() == 2                  # las viejas no se quedan sueltas


def test_borrar_borra_tomas(cliente_con_sesion):
    _nuevo(cliente_con_sesion)
    med = Medicamento.query.one()
    _tomar(cliente_con_sesion, med, "09:00")
    cliente_con_sesion.post(f"/salud/medicacion/{med.id}/borrar")
    assert Medicamento.query.count() == Toma.query.count() == HoraToma.query.count() == 0


def test_no_se_tocan_medicamentos_ajenos(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    ajeno = Medicamento(usuario=otra, nombre="Secreto", horas=[HoraToma(hora=time(9))])
    db.session.add(ajeno)
    db.session.flush()
    toma_ajena = Toma(medicamento=ajeno, fecha=date(2026, 11, 6), hora_prevista=time(9))
    db.session.add(toma_ajena)
    db.session.commit()

    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)

    assert "Secreto" not in cliente.get("/salud/medicacion/").get_data(as_text=True)
    assert "Secreto" not in cliente.get("/").get_data(as_text=True)
    assert cliente.get("/salud/medicacion/avisos.json").get_json()["avisos"] == []
    for metodo, ruta in (("get", "editar"), ("post", "pausar"), ("post", "borrar"), ("post", "tomar")):
        assert getattr(cliente, metodo)(f"/salud/medicacion/{ajeno.id}/{ruta}").status_code == 404
    assert cliente.post(f"/salud/medicacion/tomas/{toma_ajena.id}/deshacer").status_code == 404
    assert db.session.get(Toma, toma_ajena.id) is not None
