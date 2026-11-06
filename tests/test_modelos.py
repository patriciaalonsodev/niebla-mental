# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_modelos.py
#  Comprobaciones básicas del modelo de datos
# ══════════════════════════════════════════════════════════════

import os
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CLAVE_CIFRADO_DATOS"] = Fernet.generate_key().decode()

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import EntradaDiario, Etiqueta, Nota, Tarea, Usuario  # noqa: E402


@pytest.fixture
def app():
    app = create_app("test")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def usuario(app):
    u = Usuario(email="patz@example.com", nombre="Patz")
    u.establecer_password("secreta")
    db.session.add(u)
    db.session.commit()
    return u


def test_estado(app):
    respuesta = app.test_client().get("/estado")
    assert respuesta.json == {"estado": "ok"}


def test_inicio_pide_sesion(app):
    respuesta = app.test_client().get("/")
    assert respuesta.status_code == 302
    assert "/entrar" in respuesta.headers["Location"]


def test_password_con_hash(usuario):
    assert usuario.password_hash != "secreta"
    assert usuario.comprobar_password("secreta")
    assert not usuario.comprobar_password("otra")


def test_valores_por_defecto(usuario):
    assert usuario.tema == "oscuro"
    assert usuario.zona_horaria == "Europe/Madrid"


def test_diario_se_guarda_cifrado(usuario):
    db.session.add(EntradaDiario(usuario=usuario, contenido="Hoy me duele menos"))
    db.session.commit()

    crudo = db.session.execute(db.text("SELECT contenido FROM entradas_diario")).scalar()
    assert "duele" not in crudo                       # en la BD, ilegible
    db.session.expire_all()
    assert EntradaDiario.query.one().contenido == "Hoy me duele menos"


def test_coste_energia_fuera_de_rango(usuario):
    db.session.add(Tarea(usuario=usuario, titulo="Fregar", coste_energia=7))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_marcar_completada(usuario):
    tarea = Tarea(usuario=usuario, titulo="Llamar al médico")
    tarea.marcar_completada()
    assert tarea.completada and tarea.completada_en is not None
    tarea.marcar_completada(False)
    assert not tarea.completada and tarea.completada_en is None


def test_etiqueta_unica_por_usuario(usuario):
    db.session.add_all([Etiqueta(usuario=usuario, nombre="salud"),
                        Etiqueta(usuario=usuario, nombre="salud")])
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_borrar_usuario_borra_todo(usuario):
    etiqueta = Etiqueta(usuario=usuario, nombre="ideas")
    db.session.add_all([
        Tarea(usuario=usuario, titulo="Comprar pan"),
        Nota(usuario=usuario, contenido="Algo", etiquetas=[etiqueta]),
        EntradaDiario(usuario=usuario, contenido="Reflexión"),
    ])
    db.session.commit()

    db.session.delete(usuario)
    db.session.commit()
    assert Tarea.query.count() == 0
    assert Nota.query.count() == 0
    assert EntradaDiario.query.count() == 0
    assert Etiqueta.query.count() == 0
