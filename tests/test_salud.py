# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_salud.py
#  Registro diario de síntomas
# ══════════════════════════════════════════════════════════════

import re
from datetime import timedelta

from conftest import crear_usuario, entrar
from extensions import db
from models import RegistroSintomas, Usuario
from utilidades import fecha_corta, fecha_larga


def _hoy():
    return db.session.scalar(db.select(Usuario)).hoy()


def _guardar(cliente, fecha=None, **valores):
    ruta = "/salud/sintomas" + (f"?fecha={fecha.isoformat()}" if fecha else "")
    return cliente.post(ruta, data=valores, follow_redirects=True)


def test_salud_pide_sesion(cliente):
    assert cliente.get("/salud/").status_code == 302


def test_pagina_de_hoy(cliente_con_sesion):
    texto = cliente_con_sesion.get("/salud/").get_data(as_text=True)
    assert "Hoy, " + fecha_larga(_hoy()) in texto
    assert "¿Cuánto dolor tienes?" in texto
    assert "Guardar cómo estoy" in texto


def test_guardar_registro_de_hoy(cliente_con_sesion):
    texto = _guardar(cliente_con_sesion, dolor="7", sueno="3", notas="Me duelen las lumbares").get_data(as_text=True)
    registro = RegistroSintomas.query.one()
    assert (registro.fecha, registro.dolor, registro.sueno, registro.fatiga) == (_hoy(), 7, 3, None)
    assert registro.notas == "Me duelen las lumbares"
    assert "Guardado ✓" in texto and "Guardar cambios" in texto
    assert re.search(r'<input checked[^>]*name="dolor"[^>]*value="7"', texto)   # se queda marcado


def test_notas_se_guardan_cifradas(cliente_con_sesion):
    _guardar(cliente_con_sesion, notas="Muy privado")
    crudo = db.session.execute(db.text("SELECT notas FROM registros_sintomas")).scalar()
    assert crudo and "Muy privado" not in crudo


def test_el_cero_cuenta(cliente_con_sesion):
    _guardar(cliente_con_sesion, dolor="0")
    assert RegistroSintomas.query.one().dolor == 0          # 0 no es «sin indicar»


def test_un_registro_por_dia_se_actualiza(cliente_con_sesion):
    _guardar(cliente_con_sesion, dolor="7")
    _guardar(cliente_con_sesion, dolor="4", animo="8")
    registro = RegistroSintomas.query.one()
    assert (registro.dolor, registro.animo) == (4, 8)


def test_vaciar_borra_el_registro(cliente_con_sesion):
    _guardar(cliente_con_sesion, dolor="5")
    texto = _guardar(cliente_con_sesion, dolor="").get_data(as_text=True)
    assert RegistroSintomas.query.count() == 0
    assert "Registro del día borrado" in texto


def test_sin_marcar_nada_no_guarda(cliente_con_sesion):
    texto = _guardar(cliente_con_sesion).get_data(as_text=True)
    assert RegistroSintomas.query.count() == 0
    assert "no se ha guardado" in texto


def test_valor_fuera_de_rango(cliente_con_sesion):
    assert _guardar(cliente_con_sesion, dolor="11").status_code == 400
    assert RegistroSintomas.query.count() == 0


def test_registrar_un_dia_pasado(cliente_con_sesion):
    ayer = _hoy() - timedelta(days=1)
    _guardar(cliente_con_sesion, fecha=ayer, fatiga="9")
    assert RegistroSintomas.query.one().fecha == ayer

    texto = cliente_con_sesion.get(f"/salud/?fecha={ayer.isoformat()}").get_data(as_text=True)
    assert fecha_larga(ayer) in texto and "Hoy, " not in texto


def test_no_se_registran_dias_futuros(cliente_con_sesion):
    manana = _hoy() + timedelta(days=1)
    _guardar(cliente_con_sesion, fecha=manana, dolor="2")
    assert RegistroSintomas.query.one().fecha == _hoy()


def test_fecha_rara_es_hoy(cliente_con_sesion):
    texto = cliente_con_sesion.get("/salud/?fecha=patata").get_data(as_text=True)
    assert "Hoy, " in texto


def test_historial(cliente_con_sesion):
    hace3 = _hoy() - timedelta(days=3)
    _guardar(cliente_con_sesion, fecha=hace3, dolor="8", sueno="9")
    texto = cliente_con_sesion.get("/salud/").get_data(as_text=True)
    assert "Últimos 14 días" in texto
    assert fecha_corta(hace3) in texto
    assert 'data-nivel="mal"' in texto and 'data-nivel="bien"' in texto


def test_no_se_ven_registros_ajenos(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    db.session.add(RegistroSintomas(usuario=otra, fecha=otra.hoy(), dolor=9, notas="Secreto"))
    db.session.commit()

    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)

    texto = cliente.get("/salud/").get_data(as_text=True)
    assert "Secreto" not in texto and 'data-nivel="mal"' not in texto.split("<tbody>")[1].split("</tbody>")[0]
    cliente.post("/salud/sintomas", data={"dolor": "1"})
    assert db.session.scalar(db.select(RegistroSintomas).filter_by(usuario_id=otra.id)).dolor == 9


def test_fechas_en_espanol():
    from datetime import date
    assert fecha_larga(date(2026, 11, 6)) == "viernes 6 de noviembre"
    assert fecha_corta(date(2026, 11, 8)) == "dom 8"
