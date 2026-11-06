# ══════════════════════════════════════════════════════════════
#  App de organización · auth.py
#  Registro, inicio y cierre de sesión
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db
from formularios import FormularioLogin, FormularioRegistro
from models import Usuario, ahora_utc

bp = Blueprint("auth", __name__)


def _buscar_por_email(email):
    return db.session.scalar(db.select(Usuario).filter_by(email=email))


def _destino_seguro(siguiente):
    """Solo permite volver a páginas de esta misma app (evita que un
    enlace malicioso redirija a otra web tras iniciar sesión)."""
    if siguiente and siguiente.startswith("/") and not urlsplit(siguiente).netloc:
        return siguiente
    return url_for("inicio")


# ──────────────────────────────────────────────────────────────
# Registro
# ──────────────────────────────────────────────────────────────

@bp.route("/registro", methods=["GET", "POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("inicio"))

    form = FormularioRegistro()
    if form.validate_on_submit():
        email = form.email.data
        if _buscar_por_email(email):
            form.email.errors.append("Ya hay una cuenta con este email. ¿Quieres iniciar sesión?")
        else:
            ahora = ahora_utc()
            usuario = Usuario(
                email=email,
                nombre=form.nombre.data,
                privacidad_aceptada_en=ahora,
                consentimiento_salud_en=ahora,
            )
            usuario.establecer_password(form.password.data)
            db.session.add(usuario)
            db.session.commit()

            login_user(usuario, remember=True)
            flash(f"¡Hola, {usuario.nombre}! Tu cuenta ya está lista 💜", "exito")
            return redirect(url_for("inicio"))

    return render_template("auth/registro.html", form=form)


# ──────────────────────────────────────────────────────────────
# Inicio y cierre de sesión
# ──────────────────────────────────────────────────────────────

@bp.route("/entrar", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("inicio"))

    form = FormularioLogin()
    if form.validate_on_submit():
        usuario = _buscar_por_email(form.email.data)
        if usuario and usuario.comprobar_password(form.password.data):
            login_user(usuario, remember=form.recordar.data)
            return redirect(_destino_seguro(request.args.get("next")))
        # Mismo mensaje en ambos casos: no revela qué emails existen
        flash("El email o la contraseña no son correctos.", "error")

    return render_template("auth/login.html", form=form)


@bp.post("/salir")
@login_required
def logout():
    logout_user()
    flash("Has cerrado la sesión. ¡Hasta pronto!", "info")
    return redirect(url_for("auth.login"))
