# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_captura.py
#  Captura rápida y bandeja de apuntes
# ══════════════════════════════════════════════════════════════

from conftest import crear_usuario, entrar
from extensions import db
from models import Apunte, ItemCompra, Nota, Tarea


def _apuntar(cliente, texto="Llamar al reumatólogo", **extra):
    return cliente.post("/apuntar/", data={"texto": texto, **extra}, follow_redirects=True)


def test_captura_pide_sesion(cliente):
    assert cliente.get("/apuntar/").status_code == 302


def test_inicio_tiene_captura(cliente_con_sesion):
    texto = cliente_con_sesion.get("/").get_data(as_text=True)
    assert "¿Qué no quieres olvidar?" in texto
    assert "sin ordenar" not in texto


def test_apuntar_desde_inicio_vuelve_al_inicio(cliente_con_sesion):
    respuesta = cliente_con_sesion.post("/apuntar/", data={"texto": "Idea", "volver": "/"})
    assert respuesta.status_code == 302 and respuesta.location == "/"
    assert Apunte.query.one().texto == "Idea"

    texto = cliente_con_sesion.get("/").get_data(as_text=True)
    assert "Apuntado ✓" in texto and "Tienes 1" in texto


def test_volver_no_permite_otras_webs(cliente_con_sesion):
    respuesta = cliente_con_sesion.post(
        "/apuntar/", data={"texto": "x", "volver": "https://malo.example.com"}
    )
    assert respuesta.location == "/"


def test_apunte_vacio(cliente_con_sesion):
    respuesta = _apuntar(cliente_con_sesion, "   ")
    assert respuesta.status_code == 400
    assert "Escribe algo" in respuesta.get_data(as_text=True)

    respuesta = _apuntar(cliente_con_sesion, "  ", volver="/")      # desde el inicio
    assert "Escribe algo" in respuesta.get_data(as_text=True)
    assert Apunte.query.count() == 0


def test_bandeja_lista_apuntes(cliente_con_sesion):
    texto = _apuntar(cliente_con_sesion).get_data(as_text=True)
    assert "Llamar al reumatólogo" in texto and "Sin ordenar" in texto


def test_convertir_en_tarea(cliente_con_sesion):
    _apuntar(cliente_con_sesion, "Pedir cita\nPor la mañana, que tengo más energía")
    apunte = Apunte.query.one()
    cliente_con_sesion.post(f"/apuntar/{apunte.id}/a-tarea")

    tarea = Tarea.query.one()
    assert tarea.titulo == "Pedir cita"
    assert tarea.notas == "Por la mañana, que tengo más energía"
    assert Apunte.query.count() == 0


def test_tarea_con_titulo_muy_largo(cliente_con_sesion):
    _apuntar(cliente_con_sesion, "a" * 500)
    cliente_con_sesion.post(f"/apuntar/{Apunte.query.one().id}/a-tarea")
    tarea = Tarea.query.one()
    assert len(tarea.titulo) == 200 and tarea.notas == "a" * 500


def test_convertir_en_nota(cliente_con_sesion):
    _apuntar(cliente_con_sesion, "Idea para el blog")
    cliente_con_sesion.post(f"/apuntar/{Apunte.query.one().id}/a-nota")
    assert Nota.query.one().contenido == "Idea para el blog"
    assert Apunte.query.count() == 0


def test_convertir_en_compra_una_por_linea(cliente_con_sesion):
    _apuntar(cliente_con_sesion, "- leche\n\n• pan\nfruta ")
    cliente_con_sesion.post(f"/apuntar/{Apunte.query.one().id}/a-compra")
    assert [i.nombre for i in ItemCompra.query.order_by(ItemCompra.id)] == ["leche", "pan", "fruta"]
    assert Apunte.query.count() == 0


def test_borrar_apunte(cliente_con_sesion):
    _apuntar(cliente_con_sesion)
    cliente_con_sesion.post(f"/apuntar/{Apunte.query.one().id}/borrar")
    assert Apunte.query.count() == 0


def test_no_se_tocan_apuntes_ajenos(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    ajeno = Apunte(usuario=otra, texto="Secreto")
    db.session.add(ajeno)
    db.session.commit()

    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)

    assert "Secreto" not in cliente.get("/apuntar/").get_data(as_text=True)
    for ruta in ("a-tarea", "a-nota", "a-compra", "borrar"):
        assert cliente.post(f"/apuntar/{ajeno.id}/{ruta}").status_code == 404
    assert db.session.get(Apunte, ajeno.id) is not None
    assert Tarea.query.count() == Nota.query.count() == ItemCompra.query.count() == 0
