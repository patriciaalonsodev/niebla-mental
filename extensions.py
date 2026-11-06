# ══════════════════════════════════════════════════════════════
#  App de organización · extensions.py
#  Extensiones de Flask compartidas por toda la aplicación
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect


# ──────────────────────────────────────────────────────────────
# Instancias (se enlazan a la app en create_app con init_app)
# ──────────────────────────────────────────────────────────────

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()  # protege todos los formularios POST frente a CSRF