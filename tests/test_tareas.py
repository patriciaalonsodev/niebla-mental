# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_tareas.py
#  Sección de tareas
# ══════════════════════════════════════════════════════════════

from datetime import timedelta

from conftest import crear_usuario, entrar
from extensions import db
from models import Tarea, Usuario


def _patz():
    return db.session.scalar(db.select(Usuario).filter_by(email="patz@example.com"))


def _apuntar(cliente, **datos):
    datos.setdefault("titulo", "Llamar al médico")
    return cliente.post("/tareas/nueva", data=datos, follow_redirects=True)


def test_tareas_pide_sesion(cliente):
    respuesta = cliente.get("/tareas/")
    assert respuesta.status_code == 302
    assert "/entrar" in respuesta.headers["Location"]


def test_listado_vacio(cliente_con_sesion):
    texto = cliente_con_sesion.get("/tareas/").get_data(as_text=True)
    assert "No tienes tareas pendientes" in texto


def test_apuntar_tarea_con_cucharas(cliente_con_sesion):
    hoy = _patz().hoy()
    respuesta = _apuntar(cliente_con_sesion, fecha=hoy.isoformat(), coste_energia="3")
    texto = respuesta.get_data(as_text=True)

    tarea = Tarea.query.one()
    assert tarea.titulo == "Llamar al médico"
    assert tarea.coste_energia == 3
    assert tarea.fecha == hoy
    assert "Llamar al médico" in texto
    assert "Hoy: <strong>3</strong>" in texto


def test_apuntar_sin_cucharas_ni_fecha(cliente_con_sesion):
    _apuntar(cliente_con_sesion, coste_energia="", fecha="")
    tarea = Tarea.query.one()
    assert tarea.coste_energia is None
    assert tarea.fecha is None


def test_titulo_obligatorio(cliente_con_sesion):
    respuesta = _apuntar(cliente_con_sesion, titulo="   ")
    assert respuesta.status_code == 400
    assert "Escribe la tarea" in respuesta.get_data(as_text=True)
    assert Tarea.query.count() == 0


def test_cucharas_fuera_de_rango(cliente_con_sesion):
    respuesta = _apuntar(cliente_con_sesion, coste_energia="9")
    assert respuesta.status_code == 400
    assert Tarea.query.count() == 0


def test_grupos_por_fecha(cliente_con_sesion):
    hoy = _patz().hoy()
    _apuntar(cliente_con_sesion, titulo="Ayer", fecha=(hoy - timedelta(days=1)).isoformat(), coste_energia="2")
    _apuntar(cliente_con_sesion, titulo="Mañana", fecha=(hoy + timedelta(days=1)).isoformat(), coste_energia="4")
    texto = cliente_con_sesion.get("/tareas/").get_data(as_text=True)
    assert "De días anteriores" in texto
    assert "Próximos días" in texto
    assert "Hoy: <strong>2</strong>" in texto   # lo de ayer cuenta para hoy; lo de mañana, no


def test_completar_y_desmarcar(cliente_con_sesion):
    _apuntar(cliente_con_sesion)
    tarea = Tarea.query.one()

    cliente_con_sesion.post(f"/tareas/{tarea.id}/completar")
    db.session.refresh(tarea)
    assert tarea.completada and tarea.completada_en is not None

    cliente_con_sesion.post(f"/tareas/{tarea.id}/completar")
    db.session.refresh(tarea)
    assert not tarea.completada and tarea.completada_en is None


def test_editar(cliente_con_sesion):
    _apuntar(cliente_con_sesion)
    tarea = Tarea.query.one()
    assert cliente_con_sesion.get(f"/tareas/{tarea.id}/editar").status_code == 200

    cliente_con_sesion.post(
        f"/tareas/{tarea.id}/editar",
        data={"titulo": "Pedir cita", "coste_energia": "1", "notas": "Por la mañana"},
    )
    db.session.refresh(tarea)
    assert tarea.titulo == "Pedir cita"
    assert tarea.coste_energia == 1
    assert tarea.notas == "Por la mañana"


def test_borrar(cliente_con_sesion):
    _apuntar(cliente_con_sesion)
    tarea = Tarea.query.one()
    cliente_con_sesion.post(f"/tareas/{tarea.id}/borrar")
    assert Tarea.query.count() == 0


def test_no_se_ven_ni_tocan_tareas_ajenas(app):
    otra = crear_usuario(email="otra@example.com", nombre="Otra")
    ajena = Tarea(usuario=otra, titulo="Secreto")
    db.session.add(ajena)
    db.session.commit()

    crear_usuario()
    cliente = app.test_client()
    entrar(cliente)

    assert "Secreto" not in cliente.get("/tareas/").get_data(as_text=True)
    assert cliente.get(f"/tareas/{ajena.id}/editar").status_code == 404
    assert cliente.post(f"/tareas/{ajena.id}/completar").status_code == 404
    assert cliente.post(f"/tareas/{ajena.id}/borrar").status_code == 404
    assert db.session.get(Tarea, ajena.id) is not None
