# ══════════════════════════════════════════════════════════════
#  App de organización · main.py
#  Punto de entrada en el servidor (Railway): gunicorn arranca
#  «main:app». Antes de servir, pone la base de datos al día
#  (migraciones), así no hay que hacerlo a mano en cada despliegue.
#  En tu PC se sigue usando «flask run» o app.py.
# ══════════════════════════════════════════════════════════════

import logging
import os

from flask_migrate import upgrade

from app import create_app
from extensions import db

os.environ.setdefault("APP_CONFIG", "produccion")
app = create_app()
log = logging.getLogger("arranque")

# Un candado en PostgreSQL para que, si hay varios procesos arrancando
# a la vez, solo uno aplique las migraciones (los demás esperan).
CANDADO_MIGRACIONES = 7_734_201

with app.app_context():
    es_postgres = db.engine.dialect.name == "postgresql"
    with db.engine.connect() as conexion:
        if es_postgres:
            conexion.execute(db.text(f"SELECT pg_advisory_lock({CANDADO_MIGRACIONES})"))
        try:
            upgrade()
            log.warning("Base de datos al día ✓")
        finally:
            if es_postgres:
                conexion.execute(db.text(f"SELECT pg_advisory_unlock({CANDADO_MIGRACIONES})"))
