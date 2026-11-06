# ══════════════════════════════════════════════════════════════
#  App de organización · tests/conftest.py
#  Piezas comunes para los tests (pytest las carga solo)
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


def crear_usuario(email="patz@example.com", nombre="Patz", password="contraseña-larga"):
    usuario = Usuario(email=email, nombre=nombre)
    usuario.establecer_password(password)
    db.session.add(usuario)
    db.session.commit()
    return usuario


def entrar(cliente, email="patz@example.com", password="contraseña-larga"):
    return cliente.post("/entrar", data={"email": email, "password": password})


@pytest.fixture
def cliente_con_sesion(app, cliente):
    """Cliente que ya ha iniciado sesión como Patz."""
    crear_usuario()
    entrar(cliente)
    return cliente
