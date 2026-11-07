# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_cuerpo.py
#  Actividad, ejercicio, sueño y la entrada del reloj
# ══════════════════════════════════════════════════════════════

import re
from datetime import time, timedelta

from conftest import crear_usuario, entrar
from extensions import db
from models import Ejercicio, RegistroActividad, RegistroSueno, Usuario


def _usuario():
    return db.session.scalar(db.select(Usuario).filter_by(email="patz@example.com"))


def _hoy():
    return _usuario().hoy()


def _crear_clave(cliente):
    texto = cliente.post("/perfil/reloj/clave").get_data(as_text=True)
    return re.search(r'<code id="clave">([^<]+)</code>', texto).group(1)


def _enviar(cliente, clave, datos):
    return cliente.post("/api/salud", json=datos, headers={"Authorization": f"Bearer {clave}"})


# ── Páginas ───────────────────────────────────────────────────

def test_piden_sesion(cliente):
    for ruta in ("/salud/actividad", "/salud/sueno", "/perfil/reloj/guia"):
        assert cliente.get(ruta).status_code == 302


def test_actividad_vacia(cliente_con_sesion):
    texto = cliente_con_sesion.get("/salud/actividad").get_data(as_text=True)
    assert "de 6.000 pasos" in texto and "Aún no hay pasos de hoy" in texto
    assert texto.count("<rect") == 7                                  # una barra por día


def test_apuntar_pasos_a_mano(cliente_con_sesion):
    cliente_con_sesion.post("/salud/actividad", data={"fecha": _hoy().isoformat(), "pasos": "6500", "minutos_activos": "40"})
    registro = RegistroActividad.query.one()
    assert (registro.pasos, registro.minutos_activos, registro.origen) == (6500, 40, "manual")
    texto = cliente_con_sesion.get("/salud/actividad").get_data(as_text=True)
    assert "6.500" in texto and "Objetivo cumplido" in texto and "barra-llega" in texto


def test_cambiar_objetivo(cliente_con_sesion):
    cliente_con_sesion.post("/salud/actividad/objetivo", data={"objetivo_pasos": "3000"})
    assert _usuario().objetivo_pasos == 3000
    texto = cliente_con_sesion.post("/salud/actividad/objetivo", data={"objetivo_pasos": "10"},
                                    follow_redirects=True).get_data(as_text=True)
    assert "Entre 500 y 50000" in texto and _usuario().objetivo_pasos == 3000


def test_ejercicio(cliente_con_sesion):
    texto = cliente_con_sesion.post("/salud/ejercicio", data={
        "fecha": _hoy().isoformat(), "tipo": "Yoga suave", "minutos": "25", "intensidad": "1",
    }, follow_redirects=True).get_data(as_text=True)
    ejercicio = Ejercicio.query.one()
    assert (ejercicio.tipo, ejercicio.minutos, ejercicio.intensidad) == ("Yoga suave", 25, 1)
    assert "25 min esta semana" in texto
    cliente_con_sesion.post(f"/salud/ejercicio/{ejercicio.id}/borrar")
    assert Ejercicio.query.count() == 0


def test_sueno_con_horas_pasando_la_medianoche(cliente_con_sesion):
    texto = cliente_con_sesion.post("/salud/sueno", data={
        "fecha": _hoy().isoformat(), "hora_acostarse": "23:40", "hora_levantarse": "07:10", "calidad": "4",
    }, follow_redirects=True).get_data(as_text=True)
    noche = RegistroSueno.query.one()
    assert (noche.minutos_dormido, noche.calidad) == (450, 4)
    assert "7 h 30 min" in texto


def test_sueno_horas_con_coma(cliente_con_sesion):
    cliente_con_sesion.post("/salud/sueno", data={"fecha": _hoy().isoformat(), "horas": "6,5"})
    assert RegistroSueno.query.one().minutos_dormido == 390


def test_sueno_sin_datos(cliente_con_sesion):
    respuesta = cliente_con_sesion.post("/salud/sueno", data={"fecha": _hoy().isoformat()})
    assert respuesta.status_code == 400 and RegistroSueno.query.count() == 0


def test_pestanas_de_salud(cliente_con_sesion):
    texto = cliente_con_sesion.get("/salud/sueno").get_data(as_text=True)
    assert "Actividad" in texto and "Medicación" in texto and 'nav-salud nav-activo' in texto


# ── Clave personal y entrada del reloj ────────────────────────

def test_crear_clave_solo_se_ve_una_vez(cliente_con_sesion):
    clave = _crear_clave(cliente_con_sesion)
    assert clave.startswith("nm_") and len(clave) > 30
    usuario = _usuario()
    assert usuario.api_token_hash and clave not in usuario.api_token_hash        # solo la huella
    assert clave not in cliente_con_sesion.get("/perfil/").get_data(as_text=True)


def test_el_reloj_envia_actividad_y_sueno(cliente_con_sesion):
    clave = _crear_clave(cliente_con_sesion)
    respuesta = _enviar(cliente_con_sesion, clave, {
        "pasos": "8.345", "kcal_activas": 320.6, "minutos_activos": "34", "distancia_km": "5,2",
        "ejercicios": [{"tipo": "Paseo", "minutos": 30}],
        "sueno": {"acostarse": "2026-11-05T23:40:00+01:00", "levantarse": "2026-11-06T07:12:00+01:00",
                  "profundo": 60, "rem": "90", "ligero": 250},
    })
    assert respuesta.status_code == 200 and respuesta.get_json()["ok"]
    assert "8345 pasos" in respuesta.get_json()["mensaje"]

    actividad = RegistroActividad.query.one()
    assert (actividad.pasos, actividad.kcal_activas, actividad.distancia_km, actividad.origen) == (8345, 321, 5.2, "reloj")
    assert Ejercicio.query.one().origen == "reloj"
    noche = RegistroSueno.query.one()
    assert (noche.hora_acostarse, noche.hora_levantarse, noche.minutos_dormido) == (time(23, 40), time(7, 12), 452)
    assert noche.minutos_profundo == 60

    texto = cliente_con_sesion.get("/salud/sueno").get_data(as_text=True)
    assert "7 h 32 min" in texto and "del reloj" in texto and "Profundo" in texto


def test_reenviar_el_mismo_dia_actualiza(cliente_con_sesion):
    clave = _crear_clave(cliente_con_sesion)
    _enviar(cliente_con_sesion, clave, {"pasos": 3000})
    _enviar(cliente_con_sesion, clave, {"pasos": 5000})
    assert RegistroActividad.query.one().pasos == 5000


def test_el_reloj_no_borra_la_calidad_apuntada(cliente_con_sesion):
    cliente_con_sesion.post("/salud/sueno", data={"fecha": _hoy().isoformat(), "calidad": "2"})
    clave = _crear_clave(cliente_con_sesion)
    _enviar(cliente_con_sesion, clave, {"sueno": {"horas": 6}})
    noche = RegistroSueno.query.one()
    assert (noche.calidad, noche.minutos_dormido) == (2, 360)


def test_sin_clave_o_clave_falsa(cliente_con_sesion, cliente):
    assert cliente.post("/api/salud", json={"pasos": 1}).status_code == 401
    assert _enviar(cliente, "nm_inventada", {"pasos": 1}).status_code == 401
    assert RegistroActividad.query.count() == 0


def test_clave_renovada_invalida_la_anterior(cliente_con_sesion):
    vieja = _crear_clave(cliente_con_sesion)
    nueva = _crear_clave(cliente_con_sesion)
    assert _enviar(cliente_con_sesion, vieja, {"pasos": 1}).status_code == 401
    assert _enviar(cliente_con_sesion, nueva, {"pasos": 1}).status_code == 200


def test_desconectar_reloj(cliente_con_sesion):
    clave = _crear_clave(cliente_con_sesion)
    cliente_con_sesion.post("/perfil/reloj/quitar")
    assert _enviar(cliente_con_sesion, clave, {"pasos": 1}).status_code == 401


def test_datos_raros(cliente_con_sesion):
    clave = _crear_clave(cliente_con_sesion)
    assert _enviar(cliente_con_sesion, clave, {"pasos": "muchos"}).status_code == 400
    assert _enviar(cliente_con_sesion, clave, {"pasos": -5}).status_code == 400
    manana = (_hoy() + timedelta(days=1)).isoformat()
    assert _enviar(cliente_con_sesion, clave, {"fecha": manana, "pasos": 10}).status_code == 400
    assert cliente_con_sesion.post("/api/salud", data="no es json",
                                   headers={"Authorization": f"Bearer {clave}"}).status_code == 400
    assert RegistroActividad.query.count() == 0
    assert _enviar(cliente_con_sesion, clave, {}).get_json()["mensaje"].startswith("Ha llegado")


def test_cada_clave_es_de_su_dueña(app):
    crear_usuario(email="otra@example.com", nombre="Otra")
    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)
    clave = _crear_clave(cliente)
    _enviar(cliente, clave, {"pasos": 1234})
    registro = RegistroActividad.query.one()
    assert registro.usuario.email == "patz@example.com"


def test_guia(cliente_con_sesion):
    texto = cliente_con_sesion.get("/perfil/reloj/guia").get_data(as_text=True)
    assert "Atajos" in texto and "http://localhost/api/salud" in texto and "Bearer" in texto


def test_conectar_en_salud(cliente_con_sesion):
    texto = cliente_con_sesion.get("/salud/actividad").get_data(as_text=True)
    assert "Conecta tu reloj o tus apps de salud" in texto and 'href="/salud/conectar"' in texto
    texto = cliente_con_sesion.get("/salud/conectar").get_data(as_text=True)
    assert "Apple Watch" in texto and "Garmin" in texto and "Health Connect" in texto
    # Crear la clave desde Salud se queda en Salud
    texto = cliente_con_sesion.post("/perfil/reloj/clave", data={"volver": "salud"}).get_data(as_text=True)
    assert 'id="clave"' in texto and "¿Con qué funciona?" in texto
    assert "Conecta tu reloj o tus apps" not in cliente_con_sesion.get("/salud/actividad").get_data(as_text=True)


def test_sueno_con_fechas_como_las_escribe_atajos(cliente_con_sesion):
    clave = _crear_clave(cliente_con_sesion)
    respuesta = _enviar(cliente_con_sesion, clave, {
        "acostarse": "6 nov 2026, 23:52", "levantarse": "7 nov 2026, 7:31",    # sin «diccionario»
    })
    assert respuesta.status_code == 200 and "sueño 7 h 39 min" in respuesta.get_json()["mensaje"]
    noche = RegistroSueno.query.one()
    assert (noche.hora_acostarse, noche.hora_levantarse, noche.minutos_dormido) == (time(23, 52), time(7, 31), 459)
    assert _enviar(cliente_con_sesion, clave, {"acostarse": "ayer por la noche"}).status_code == 400


def test_sueno_con_todos_los_tramos_de_la_noche(cliente_con_sesion):
    # Atajos manda las listas enteras (una fecha por línea), desordenadas y
    # con un tramo del iPhone que se pisa con el del reloj
    clave = _crear_clave(cliente_con_sesion)
    respuesta = _enviar(cliente_con_sesion, clave, {
        "acostarse": "7 nov 2026, 3:57\n6 nov 2026, 23:50\n7 nov 2026, 2:25\n7 nov 2026, 2:40",
        "levantarse": "7 nov 2026, 9:12\n7 nov 2026, 0:30\n7 nov 2026, 3:30\n7 nov 2026, 3:00",
    })
    # 23:50-0:30 (40) + 2:25-3:30 (65) + 3:57-9:12 (315) = 420 min
    assert "sueño 7 h 0 min (de 23:50 a 09:12)" in respuesta.get_json()["mensaje"]
    noche = RegistroSueno.query.one()
    assert (noche.hora_acostarse, noche.hora_levantarse, noche.minutos_dormido) == (time(23, 50), time(9, 12), 420)


def test_sueno_ignora_el_dormido_generico_si_hay_fases(cliente_con_sesion):
    # El iPhone pone un «Dormido» de toda la noche; el reloj, las fases
    clave = _crear_clave(cliente_con_sesion)
    respuesta = _enviar(cliente_con_sesion, clave, {
        "acostarse": "7 nov 2026, 2:27\n7 nov 2026, 2:30\n7 nov 2026, 4:00\n7 nov 2026, 4:10\n7 nov 2026, 6:00",
        "levantarse": "7 nov 2026, 9:58\n7 nov 2026, 4:00\n7 nov 2026, 4:10\n7 nov 2026, 6:00\n7 nov 2026, 9:12",
        "fases": "Dormido\nBásico\nDespierto\nProfundo\nSueño REM",
    })
    # 90 + 110 + 192 = 392 min (6 h 32), sin los 10 min despierta
    assert "sueño 6 h 32 min (de 02:30 a 09:12)" in respuesta.get_json()["mensaje"]
    noche = RegistroSueno.query.one()
    assert (noche.minutos_ligero, noche.minutos_profundo, noche.minutos_rem, noche.minutos_despierto) == (90, 110, 192, 10)
