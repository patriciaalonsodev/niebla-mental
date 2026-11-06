# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_notas.py
#  Sección de notas
# ══════════════════════════════════════════════════════════════

from conftest import crear_usuario, entrar
from extensions import db
from models import Etiqueta, Nota


def _apuntar(cliente, **datos):
    datos.setdefault("contenido", "Preguntar por la dosis de pregabalina")
    return cliente.post("/notas/nueva", data=datos, follow_redirects=True)


def test_notas_pide_sesion(cliente):
    assert cliente.get("/notas/").status_code == 302


def test_crear_nota_con_etiquetas(cliente_con_sesion):
    respuesta = _apuntar(cliente_con_sesion, titulo="Médico", etiquetas="Salud, médico , salud")
    texto = respuesta.get_data(as_text=True)

    nota = Nota.query.one()
    assert nota.titulo == "Médico"
    assert sorted(e.nombre for e in nota.etiquetas) == ["médico", "salud"]   # sin repetir, en minúsculas
    assert "Preguntar por la dosis" in texto
    assert "#salud" in texto


def test_etiquetas_se_reutilizan(cliente_con_sesion):
    _apuntar(cliente_con_sesion, etiquetas="ideas")
    _apuntar(cliente_con_sesion, contenido="Otra", etiquetas="Ideas")
    assert Etiqueta.query.count() == 1


def test_contenido_obligatorio(cliente_con_sesion):
    respuesta = _apuntar(cliente_con_sesion, contenido="  ")
    assert respuesta.status_code == 400
    assert Nota.query.count() == 0


def test_buscar_y_filtrar(cliente_con_sesion):
    _apuntar(cliente_con_sesion, contenido="Comprar regalo para mamá", etiquetas="casa")
    _apuntar(cliente_con_sesion, contenido="Pedir informe al reumatólogo", etiquetas="médico")

    texto = cliente_con_sesion.get("/notas/?q=REGALO").get_data(as_text=True)
    assert "regalo" in texto and "informe" not in texto

    texto = cliente_con_sesion.get("/notas/?etiqueta=médico").get_data(as_text=True)
    assert "informe" in texto and "regalo" not in texto

    texto = cliente_con_sesion.get("/notas/?q=100%").get_data(as_text=True)
    assert "No hay notas que coincidan" in texto       # el % no actúa como comodín


def test_fijadas_primero(cliente_con_sesion):
    _apuntar(cliente_con_sesion, contenido="Normal")
    _apuntar(cliente_con_sesion, contenido="Importante", fijada="y")
    texto = cliente_con_sesion.get("/notas/").get_data(as_text=True)
    assert texto.index("Importante") < texto.index("Normal")


def test_fijar_editar_y_borrar(cliente_con_sesion):
    _apuntar(cliente_con_sesion, etiquetas="uno")
    nota = Nota.query.one()

    cliente_con_sesion.post(f"/notas/{nota.id}/fijar")
    db.session.refresh(nota)
    assert nota.fijada

    texto = cliente_con_sesion.get(f"/notas/{nota.id}/editar").get_data(as_text=True)
    assert 'value="uno"' in texto                       # etiquetas precargadas como texto

    cliente_con_sesion.post(
        f"/notas/{nota.id}/editar", data={"contenido": "Cambiada", "etiquetas": "dos"}
    )
    db.session.refresh(nota)
    assert nota.contenido == "Cambiada"
    assert [e.nombre for e in nota.etiquetas] == ["dos"]
    assert not nota.fijada                              # casilla desmarcada al guardar

    cliente_con_sesion.post(f"/notas/{nota.id}/borrar")
    assert Nota.query.count() == 0


def test_no_se_ven_ni_tocan_notas_ajenas(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    ajena = Nota(usuario=otra, contenido="Secreto")
    db.session.add(ajena)
    db.session.commit()

    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)

    assert "Secreto" not in cliente.get("/notas/").get_data(as_text=True)
    assert "No hay notas que coincidan" in cliente.get("/notas/?q=Secreto").get_data(as_text=True)
    for metodo, ruta in (("get", "editar"), ("post", "fijar"), ("post", "borrar")):
        assert getattr(cliente, metodo)(f"/notas/{ajena.id}/{ruta}").status_code == 404
