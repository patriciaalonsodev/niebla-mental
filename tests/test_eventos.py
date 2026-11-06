# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_eventos.py
#  Agenda: eventos y citas médicas
# ══════════════════════════════════════════════════════════════

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from conftest import crear_usuario, entrar
from extensions import db
from models import Evento, Usuario

AHORA = datetime(2026, 11, 6, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))   # viernes
HOY = AHORA.date()


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr(Usuario, "ahora", lambda self: AHORA)


def _nuevo(cliente, titulo="Comida con mamá", fecha=HOY, **extra):
    datos = {"tipo": "evento", "titulo": titulo, "fecha": fecha.isoformat(), **extra}
    return cliente.post("/eventos/nuevo", data=datos, follow_redirects=True)


def test_agenda_pide_sesion(cliente):
    assert cliente.get("/eventos/").status_code == 302


def test_agenda_es_una_pagina_de_3_dias(cliente_con_sesion):
    texto = cliente_con_sesion.get("/eventos/").get_data(as_text=True)
    assert texto.count('class="dia-libreta') == 3
    assert "Añadir algo el viernes 6 de noviembre" in texto        # «＋» en cada día
    assert "Añadir algo el domingo 8 de noviembre" in texto
    assert "lunes 9" not in texto


def test_pasar_paginas_y_elegir_2_dias(cliente_con_sesion):
    texto = cliente_con_sesion.get("/eventos/?desde=2026-11-09").get_data(as_text=True)
    assert "Añadir algo el lunes 9 de noviembre" in texto and 'href="/eventos/?desde=2026-11-06"' in texto
    texto = cliente_con_sesion.get("/eventos/?dias=2").get_data(as_text=True)
    assert texto.count('class="dia-libreta') == 2
    texto = cliente_con_sesion.get("/eventos/").get_data(as_text=True)    # se recuerda
    assert texto.count('class="dia-libreta') == 2


def test_formulario_nuevo(cliente_con_sesion):
    texto = cliente_con_sesion.get("/eventos/nuevo").get_data(as_text=True)
    assert f'value="{HOY.isoformat()}"' in texto and "Guardar en la agenda" in texto


def test_crear_evento(cliente_con_sesion):
    texto = _nuevo(
        cliente_con_sesion, hora_inicio="13:30", hora_fin="15:00", lugar="Casa", coste_energia="3"
    ).get_data(as_text=True)
    evento = Evento.query.one()
    assert (evento.tipo, evento.hora_inicio, evento.hora_fin, evento.coste_energia) == ("evento", time(13, 30), time(15), 3)
    assert "Evento guardado" in texto and "13:30–15:00" in texto and "Comida con mamá" in texto
    assert "3🥄" in texto                                 # cucharas del día


def test_textos_cifrados(cliente_con_sesion):
    _nuevo(cliente_con_sesion, titulo="Psiquiatra", tipo="cita", preguntas="¿Subo la dosis?")
    fila = db.session.execute(db.text("SELECT titulo, preguntas FROM eventos")).one()
    assert "Psiquiatra" not in fila.titulo and "dosis" not in fila.preguntas


def test_validaciones(cliente_con_sesion):
    assert _nuevo(cliente_con_sesion, titulo=" ").status_code == 400
    respuesta = _nuevo(cliente_con_sesion, hora_inicio="12:00", hora_fin="11:00")
    assert respuesta.status_code == 400 and "después de la hora de inicio" in respuesta.get_data(as_text=True)
    respuesta = _nuevo(cliente_con_sesion, hora_fin="11:00")
    assert "Pon también la hora de inicio" in respuesta.get_data(as_text=True)
    assert _nuevo(cliente_con_sesion, tipo="fiesta").status_code == 400
    assert Evento.query.count() == 0


def test_ordenado_dentro_del_dia(cliente_con_sesion):
    _nuevo(cliente_con_sesion, "Fisio", fecha=HOY + timedelta(days=1), hora_inicio="09:00")
    _nuevo(cliente_con_sesion, "Cumple de Ana", fecha=HOY + timedelta(days=1))          # todo el día
    _nuevo(cliente_con_sesion, "Yoga suave", fecha=HOY + timedelta(days=2), hora_inicio="18:00")
    _nuevo(cliente_con_sesion, "Lejano", fecha=HOY + timedelta(days=4))
    texto = cliente_con_sesion.get("/eventos/").get_data(as_text=True)
    assert texto.index("Cumple de Ana") < texto.index("Fisio") < texto.index("Yoga suave")
    assert "Todo el día" in texto and "Lejano" not in texto              # en la página siguiente


def test_al_guardar_vuelve_a_la_pagina_de_ese_dia(cliente_con_sesion):
    respuesta = cliente_con_sesion.post("/eventos/nuevo", data={
        "tipo": "evento", "titulo": "Viaje", "fecha": "2026-12-20",
    })
    assert respuesta.location == "/eventos/?desde=2026-12-20"


def test_cita_medica_con_preguntas(cliente_con_sesion):
    _nuevo(
        cliente_con_sesion, "Reumatólogo", fecha=HOY + timedelta(days=2), tipo="cita",
        profesional="Dra. López", preguntas="- ¿Puedo hacer pilates?\n\n• ¿Cambio la pregabalina?",
    )
    cita = Evento.query.one()
    assert cita.es_cita
    assert cita.lista_preguntas() == ["¿Puedo hacer pilates?", "¿Cambio la pregabalina?"]

    texto = cliente_con_sesion.get("/eventos/").get_data(as_text=True)
    assert "Cita médica: </span>Reumatólogo" in texto

    texto = cliente_con_sesion.get(f"/eventos/{cita.id}/editar").get_data(as_text=True)
    assert "Para preguntar en la consulta" in texto and "<li>¿Puedo hacer pilates?</li>" in texto


def test_cita_pasada_pide_resumen(cliente_con_sesion):
    _nuevo(cliente_con_sesion, "Neuróloga", fecha=HOY - timedelta(days=1), tipo="cita", preguntas="¿Resonancia?")
    cita = Evento.query.one()
    texto = cliente_con_sesion.get(f"/eventos/{cita.id}/editar").get_data(as_text=True)
    assert "Esta cita ya pasó" in texto and "Para preguntar en la consulta" not in texto

    cliente_con_sesion.post(f"/eventos/{cita.id}/editar", data={
        "tipo": "cita", "titulo": "Neuróloga", "fecha": cita.fecha.isoformat(),
        "preguntas": "¿Resonancia?", "resumen": "Pide resonancia en enero",
    })
    db.session.refresh(cita)
    assert cita.resumen == "Pide resonancia en enero"
    assert "Esta cita ya pasó" not in cliente_con_sesion.get(f"/eventos/{cita.id}/editar").get_data(as_text=True)


def test_llegar_con_fecha_y_tipo(cliente_con_sesion):
    texto = cliente_con_sesion.get("/eventos/nuevo?fecha=2026-12-01&tipo=cita").get_data(as_text=True)
    assert 'value="2026-12-01"' in texto
    assert re.search(r'<input checked[^>]*value="cita"', texto)      # «Cita médica» ya marcada


def test_resumen_en_el_inicio(cliente_con_sesion):
    _nuevo(cliente_con_sesion, "Fisio", hora_inicio="17:00")
    _nuevo(cliente_con_sesion, "Dentista", fecha=HOY + timedelta(days=1), tipo="cita")
    _nuevo(cliente_con_sesion, "Lejano", fecha=HOY + timedelta(days=5))
    texto = cliente_con_sesion.get("/").get_data(as_text=True)
    assert "📅 Hoy" in texto and "📅 Mañana" in texto
    assert "Fisio" in texto and "Dentista" in texto and "Lejano" not in texto


def test_editar_y_borrar(cliente_con_sesion):
    _nuevo(cliente_con_sesion, hora_inicio="10:00")
    evento = Evento.query.one()
    cliente_con_sesion.post(f"/eventos/{evento.id}/editar", data={
        "tipo": "evento", "titulo": "Cambiado", "fecha": HOY.isoformat(), "hora_inicio": "", "lugar": "",
    })
    db.session.refresh(evento)
    assert (evento.titulo, evento.hora_inicio, evento.lugar) == ("Cambiado", None, None)
    cliente_con_sesion.post(f"/eventos/{evento.id}/borrar")
    assert Evento.query.count() == 0


def test_no_se_ven_eventos_ajenos(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    ajeno = Evento(usuario=otra, titulo="Secreto", fecha=HOY)
    db.session.add(ajeno)
    db.session.commit()

    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)

    assert "Secreto" not in cliente.get("/eventos/").get_data(as_text=True)
    assert "Secreto" not in cliente.get("/").get_data(as_text=True)
    assert cliente.get(f"/eventos/{ajeno.id}/editar").status_code == 404
    assert cliente.post(f"/eventos/{ajeno.id}/borrar").status_code == 404
