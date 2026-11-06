# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_diario.py
#  Diario personal cifrado
# ══════════════════════════════════════════════════════════════

from datetime import timedelta

from conftest import crear_usuario, entrar
from extensions import db
from models import EntradaDiario, Etiqueta, Nota, Usuario


def _hoy():
    return db.session.scalar(db.select(Usuario)).hoy()


def _escribir(cliente, contenido="Hoy ha sido un día largo", fecha=None, **extra):
    datos = {"contenido": contenido, "fecha": (fecha or _hoy()).isoformat(), **extra}
    return cliente.post("/diario/nueva", data=datos, follow_redirects=True)


def test_diario_pide_sesion(cliente):
    assert cliente.get("/diario/").status_code == 302


def test_diario_vacio(cliente_con_sesion):
    texto = cliente_con_sesion.get("/diario/").get_data(as_text=True)
    assert "Tu diario está esperando" in texto
    texto = cliente_con_sesion.get("/diario/nueva").get_data(as_text=True)
    assert f'value="{_hoy().isoformat()}"' in texto           # fecha de hoy por defecto
    assert "Querido diario" in texto


def test_escribir_entrada(cliente_con_sesion):
    texto = _escribir(
        cliente_con_sesion, estado_animo="4", etiquetas="Brote, familia",
        pregunta_guia="¿Qué te ha sentado bien hoy?",
    ).get_data(as_text=True)
    entrada = EntradaDiario.query.one()
    assert (entrada.estado_animo, entrada.pregunta_guia) == (4, "¿Qué te ha sentado bien hoy?")
    assert sorted(e.nombre for e in entrada.etiquetas) == ["brote", "familia"]
    assert "Guardado en tu diario" in texto and "🙂" in texto and "#brote" in texto


def test_contenido_cifrado(cliente_con_sesion):
    _escribir(cliente_con_sesion, "Algo muy personal")
    crudo = db.session.execute(db.text("SELECT contenido FROM entradas_diario")).scalar()
    assert "Algo muy personal" not in crudo


def test_contenido_obligatorio(cliente_con_sesion):
    assert _escribir(cliente_con_sesion, "   ").status_code == 400
    assert EntradaDiario.query.count() == 0


def test_no_dias_futuros(cliente_con_sesion):
    respuesta = _escribir(cliente_con_sesion, fecha=_hoy() + timedelta(days=1))
    assert respuesta.status_code == 400
    assert "aún no ha llegado" in respuesta.get_data(as_text=True)


def test_una_pagina_por_entrada_y_se_abre_por_la_ultima(cliente_con_sesion):
    _escribir(cliente_con_sesion, "Entrada de la semana pasada", fecha=_hoy() - timedelta(days=7))
    _escribir(cliente_con_sesion, "Entrada de hoy")
    texto = cliente_con_sesion.get("/diario/").get_data(as_text=True)
    assert "Entrada de hoy" in texto and "semana pasada" not in texto
    assert "Página 2 de 2" in texto and "‹ Anterior" in texto and "Página nueva ›" in texto
    texto = cliente_con_sesion.get("/diario/?pagina=1").get_data(as_text=True)
    assert "semana pasada" in texto and "Siguiente ›" in texto
    assert 'class="boton boton-secundario pasar-atras"' not in texto     # en la 1 no hay anterior


def test_buscar_sin_tildes_ni_mayusculas(cliente_con_sesion):
    _escribir(cliente_con_sesion, "Cita con el Médico de cabecera")
    _escribir(cliente_con_sesion, "Paseo por el parque")
    texto = cliente_con_sesion.get("/diario/?q=medico").get_data(as_text=True)
    assert "Cita con el Médico" in texto and "Paseo" not in texto and "Página 1 de 1" in texto
    texto = cliente_con_sesion.get("/diario/?q=nada").get_data(as_text=True)
    assert "No hay páginas que coincidan" in texto


def test_filtrar_por_etiqueta(cliente_con_sesion):
    _escribir(cliente_con_sesion, "Día de brote", etiquetas="brote")
    _escribir(cliente_con_sesion, "Día tranquilo")
    texto = cliente_con_sesion.get("/diario/?etiqueta=brote").get_data(as_text=True)
    assert "Día de brote" in texto and "Día tranquilo" not in texto


def test_etiquetas_del_diario_no_salen_en_notas(cliente_con_sesion):
    _escribir(cliente_con_sesion, etiquetas="intimo")
    cliente_con_sesion.post("/notas/nueva", data={"contenido": "Nota", "etiquetas": "casa"})
    assert "#intimo" not in cliente_con_sesion.get("/notas/").get_data(as_text=True)
    assert Etiqueta.query.count() == 2 and Nota.query.count() == 1


def test_pasar_paginas_y_fuera_de_rango(cliente_con_sesion):
    for n in range(3):
        _escribir(cliente_con_sesion, f"Entrada {n}", fecha=_hoy() - timedelta(days=3 - n))
    assert "Entrada 0" in cliente_con_sesion.get("/diario/?pagina=1").get_data(as_text=True)
    assert "Entrada 2" in cliente_con_sesion.get("/diario/?pagina=99").get_data(as_text=True)
    assert "Entrada 0" in cliente_con_sesion.get("/diario/?pagina=-4").get_data(as_text=True)
    assert "Entrada 2" in cliente_con_sesion.get("/diario/?pagina=patata").get_data(as_text=True)


def test_al_guardar_lleva_a_su_pagina(cliente_con_sesion):
    _escribir(cliente_con_sesion, "Nueva")
    _escribir(cliente_con_sesion, "Antigua", fecha=_hoy() - timedelta(days=30))
    respuesta = cliente_con_sesion.post("/diario/nueva", data={
        "contenido": "En medio", "fecha": (_hoy() - timedelta(days=10)).isoformat(),
    })
    assert respuesta.location == "/diario/?pagina=2"


def test_editar_y_borrar(cliente_con_sesion):
    _escribir(cliente_con_sesion, "Primera versión", etiquetas="uno", estado_animo="2")
    entrada = EntradaDiario.query.one()

    texto = cliente_con_sesion.get(f"/diario/{entrada.id}/editar").get_data(as_text=True)
    assert "Primera versión" in texto and 'value="uno"' in texto

    cliente_con_sesion.post(f"/diario/{entrada.id}/editar", data={
        "contenido": "Corregida", "fecha": _hoy().isoformat(), "estado_animo": "", "etiquetas": "",
    })
    db.session.refresh(entrada)
    assert (entrada.contenido, entrada.estado_animo, entrada.etiquetas) == ("Corregida", None, [])

    cliente_con_sesion.post(f"/diario/{entrada.id}/borrar")
    assert EntradaDiario.query.count() == 0


def test_no_se_leen_diarios_ajenos(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    ajena = EntradaDiario(usuario=otra, fecha=otra.hoy(), contenido="Secreto")
    db.session.add(ajena)
    db.session.commit()

    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)

    assert "Secreto" not in cliente.get("/diario/").get_data(as_text=True)
    assert "Tu diario está esperando" in cliente.get("/diario/").get_data(as_text=True)
    assert cliente.get(f"/diario/{ajena.id}/editar").status_code == 404
    assert cliente.post(f"/diario/{ajena.id}/borrar").status_code == 404
