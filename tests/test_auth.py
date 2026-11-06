# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_auth.py
#  Registro, inicio y cierre de sesión
# ══════════════════════════════════════════════════════════════

import os
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CLAVE_CIFRADO_DATOS", Fernet.generate_key().decode())

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import Usuario  # noqa: E402

DATOS_REGISTRO = {
    "nombre": "Patz",
    "email": "Patz@Example.com ",
    "password": "contraseña-larga",
    "password2": "contraseña-larga",
    "acepta_privacidad": "y",
    "consiente_salud": "y",
}


@pytest.fixture
def app():
    app = create_app("test")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def cliente(app):
    return app.test_client()


def registrar(cliente, **cambios):
    return cliente.post("/registro", data={**DATOS_REGISTRO, **cambios}, follow_redirects=True)


def test_paginas_cargan(cliente):
    for ruta in ("/registro", "/entrar", "/privacidad"):
        assert cliente.get(ruta).status_code == 200


def test_registro_crea_cuenta_y_entra(cliente):
    respuesta = registrar(cliente)
    texto = respuesta.get_data(as_text=True)
    assert "Hola, Patz" in texto

    usuario = Usuario.query.one()
    assert usuario.email == "patz@example.com"        # normalizado
    assert usuario.comprobar_password("contraseña-larga")
    assert usuario.privacidad_aceptada_en is not None
    assert usuario.consentimiento_salud_en is not None


def test_registro_exige_consentimientos(cliente):
    respuesta = registrar(cliente, consiente_salud="")
    assert "Sin este consentimiento" in respuesta.get_data(as_text=True)
    assert Usuario.query.count() == 0


def test_registro_contrasenas_distintas(cliente):
    respuesta = registrar(cliente, password2="otra-cosa-larga")
    assert "no coinciden" in respuesta.get_data(as_text=True)
    assert Usuario.query.count() == 0


def test_registro_email_repetido(cliente):
    registrar(cliente)
    cliente.post("/salir")
    respuesta = registrar(cliente)
    assert "Ya hay una cuenta" in respuesta.get_data(as_text=True)
    assert Usuario.query.count() == 1


def test_login_y_logout(cliente):
    registrar(cliente)
    cliente.post("/salir")
    assert cliente.get("/").status_code == 302            # fuera

    respuesta = cliente.post(
        "/entrar",
        data={"email": "patz@example.com", "password": "contraseña-larga"},
        follow_redirects=True,
    )
    assert "Hola, Patz" in respuesta.get_data(as_text=True)


def test_login_incorrecto(cliente):
    registrar(cliente)
    cliente.post("/salir")
    respuesta = cliente.post(
        "/entrar", data={"email": "patz@example.com", "password": "mal"}, follow_redirects=True
    )
    assert "no son correctos" in respuesta.get_data(as_text=True)


def test_login_no_redirige_fuera(cliente):
    registrar(cliente)
    cliente.post("/salir")
    respuesta = cliente.post(
        "/entrar?next=//web-maliciosa.com",
        data={"email": "patz@example.com", "password": "contraseña-larga"},
    )
    assert respuesta.headers["Location"] == "/"
