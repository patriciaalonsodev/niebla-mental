# ══════════════════════════════════════════════════════════════
#  App de organización · google_calendar.py
#  Conexión con Google Calendar (OAuth 2.0) y sincronización
#  Patricia Alonso · patriciaalonso.es
#
#  Cómo funciona:
#  - Conectar: Google pregunta al usuario si da permiso y nos
#    devuelve un «refresh token» (se guarda cifrado). Con él pedimos
#    «access tokens» de 1 hora cada vez que hacen falta.
#  - App → Google: al crear, editar o borrar un evento en la app,
#    se hace lo mismo en el calendario principal de Google.
#  - Google → App: al sincronizar se traen los eventos de Google de
#    los próximos días (nuevos, cambiados y borrados).
#  - Privacidad: las citas médicas llegan a Google como «🩺 Cita
#    médica», sin detalles, salvo que el usuario diga lo contrario.
# ══════════════════════════════════════════════════════════════

import secrets
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from flask import (
    Blueprint, current_app, flash, redirect, request, session, url_for,
)
from flask_login import current_user, login_required

from extensions import db
from models import ConexionGoogle, Evento, ahora_utc

bp = Blueprint("google", __name__, url_prefix="/google")

URL_AUTORIZACION = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_REVOCAR = "https://oauth2.googleapis.com/revoke"
URL_USUARIO = "https://openidconnect.googleapis.com/v1/userinfo"
URL_EVENTOS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
PERMISOS = "openid email https://www.googleapis.com/auth/calendar.events"

DIAS_A_TRAER = 60                       # ventana de eventos que se traen de Google
SINCRONIZAR_CADA = timedelta(minutes=15)
TITULO_CITA_PRIVADA = "🩺 Cita médica"


class ErrorGoogle(Exception):
    """Google no ha respondido bien (sin conexión, caído, etc.)."""


class PermisoRetirado(ErrorGoogle):
    """El usuario quitó el permiso desde su cuenta de Google."""


# ──────────────────────────────────────────────────────────────
# Peticiones HTTP (una sola función: en los tests se sustituye)
# ──────────────────────────────────────────────────────────────

def _http(metodo, url, **opciones):
    try:
        return requests.request(metodo, url, timeout=15, **opciones)
    except requests.RequestException as error:
        raise ErrorGoogle(str(error)) from error


def configurado():
    return bool(current_app.config.get("GOOGLE_CLIENT_ID") and current_app.config.get("GOOGLE_CLIENT_SECRET"))


def _url_vuelta():
    return url_for("google.vuelta", _external=True)


# ──────────────────────────────────────────────────────────────
# Tokens
# ──────────────────────────────────────────────────────────────

def _pedir_token(datos):
    respuesta = _http("POST", URL_TOKEN, data={
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
        **datos,
    })
    cuerpo = respuesta.json() if respuesta.content else {}
    if respuesta.status_code == 400 and cuerpo.get("error") == "invalid_grant":
        raise PermisoRetirado("Google ya no acepta el permiso")
    if respuesta.status_code != 200:
        raise ErrorGoogle(f"Token: {respuesta.status_code} {cuerpo.get('error')}")
    return cuerpo


def _guardar_access_token(conexion, cuerpo):
    conexion.access_token = cuerpo["access_token"]
    conexion.caduca_en = ahora_utc() + timedelta(seconds=int(cuerpo.get("expires_in", 3600)) - 60)


def _en_utc(momento):
    """SQLite devuelve las fechas sin zona: son UTC."""
    return momento.replace(tzinfo=timezone.utc) if momento.tzinfo is None else momento


def _access_token(conexion):
    if conexion.access_token and conexion.caduca_en and _en_utc(conexion.caduca_en) > ahora_utc():
        return conexion.access_token
    cuerpo = _pedir_token({"grant_type": "refresh_token", "refresh_token": conexion.refresh_token})
    _guardar_access_token(conexion, cuerpo)
    return conexion.access_token


def _api(conexion, metodo, url, **opciones):
    """Llama a la API de Calendar. Si el token ha caducado antes de
    tiempo, lo renueva y lo intenta otra vez."""
    for intento in range(2):
        cabeceras = {"Authorization": f"Bearer {_access_token(conexion)}"}
        respuesta = _http(metodo, url, headers=cabeceras, **opciones)
        if respuesta.status_code == 401 and intento == 0:
            conexion.access_token = None
            continue
        return respuesta
    raise PermisoRetirado("Google rechaza el permiso")


def _conexion_de(usuario):
    return db.session.scalar(db.select(ConexionGoogle).filter_by(usuario_id=usuario.id))


def _olvidar_conexion(conexion):
    """El permiso ya no vale: se borra la conexión, pero los eventos se quedan."""
    db.session.execute(
        db.update(Evento).where(Evento.usuario_id == conexion.usuario_id).values(google_id=None)
    )
    db.session.delete(conexion)
    db.session.commit()


# ──────────────────────────────────────────────────────────────
# Convertir eventos de la app ↔ Google
# ──────────────────────────────────────────────────────────────

def a_google(evento, conexion):
    """Evento de la app → formato de Google Calendar."""
    zona = evento.usuario.zona_horaria
    if evento.hora_inicio:
        inicio = datetime.combine(evento.fecha, evento.hora_inicio)
        fin = datetime.combine(evento.fecha, evento.hora_fin) if evento.hora_fin else inicio + timedelta(hours=1)
        cuando = {
            "start": {"dateTime": inicio.isoformat(), "timeZone": zona},
            "end": {"dateTime": fin.isoformat(), "timeZone": zona},
        }
    else:
        cuando = {
            "start": {"date": evento.fecha.isoformat()},
            "end": {"date": (evento.fecha + timedelta(days=1)).isoformat()},  # Google: fin exclusivo
        }

    nombre_app = current_app.config["APP_NOMBRE"]
    if evento.es_cita and not conexion.detalle_citas:
        titulo, lugar, descripcion = TITULO_CITA_PRIVADA, None, f"Los detalles están en {nombre_app}."
    elif evento.es_cita:
        titulo = f"🩺 {evento.titulo}"
        lugar = evento.lugar
        descripcion = "\n\n".join(t for t in (evento.profesional, evento.notas) if t) or None
    else:
        titulo, lugar, descripcion = evento.titulo, evento.lugar, evento.notas

    return {
        "summary": titulo,
        "location": lugar,
        "description": descripcion,
        **cuando,
        "extendedProperties": {"private": {"niebla_id": str(evento.id)}},
    }


def _momento_google(dato, zona):
    """{"date": ...} o {"dateTime": ...} → (fecha, hora o None) en la zona del usuario."""
    if "date" in dato:
        return datetime.fromisoformat(dato["date"]).date(), None
    momento = datetime.fromisoformat(dato["dateTime"]).astimezone(ZoneInfo(zona))
    return momento.date(), momento.time().replace(second=0, microsecond=0)


def _aplicar_de_google(evento, item, zona):
    """Copia lo de Google en el evento local. A los eventos creados en
    la app solo se les cambia el día y la hora (si no, el título
    privado «Cita médica» pisaría el de verdad)."""
    fecha, hora_inicio = _momento_google(item["start"], zona)
    fecha_fin, hora_fin = _momento_google(item.get("end", item["start"]), zona)
    evento.fecha = fecha
    evento.hora_inicio = hora_inicio
    evento.hora_fin = hora_fin if hora_inicio and fecha_fin == fecha and hora_fin > hora_inicio else None
    if evento.origen == "google":
        evento.titulo = (item.get("summary") or "(Sin título)")[:200]
        evento.lugar = item.get("location") or None
        evento.notas = item.get("description") or None


# ──────────────────────────────────────────────────────────────
# Sincronizar
# ──────────────────────────────────────────────────────────────

def enviar(evento):
    """Crea o actualiza el evento en Google. Devuelve False si no se
    pudo (se reintentará en la próxima sincronización)."""
    conexion = _conexion_de(evento.usuario)
    if conexion is None:
        return True
    try:
        cuerpo = a_google(evento, conexion)
        if evento.google_id:
            respuesta = _api(conexion, "PATCH", f"{URL_EVENTOS}/{evento.google_id}", json=cuerpo)
            if respuesta.status_code in (404, 410):          # lo borraron en Google: crearlo otra vez
                evento.google_id = None
        if not evento.google_id:
            respuesta = _api(conexion, "POST", URL_EVENTOS, json=cuerpo)
        if respuesta.status_code not in (200, 201):
            raise ErrorGoogle(f"Guardar evento: {respuesta.status_code}")
        evento.google_id = respuesta.json()["id"]
        db.session.commit()
        return True
    except PermisoRetirado:
        _olvidar_conexion(conexion)
        flash("Google ha retirado el permiso del calendario. Vuelve a conectarlo desde tu perfil.", "error")
        return False
    except ErrorGoogle:
        db.session.commit()
        return False


def borrar_en_google(evento):
    conexion = _conexion_de(evento.usuario)
    if conexion is None or not evento.google_id:
        return True
    try:
        respuesta = _api(conexion, "DELETE", f"{URL_EVENTOS}/{evento.google_id}")
        return respuesta.status_code in (200, 204, 404, 410)
    except PermisoRetirado:
        _olvidar_conexion(conexion)
        return False
    except ErrorGoogle:
        return False


def traer_de_google(conexion):
    """Trae los eventos de Google de los próximos días. Devuelve
    cuántos eventos nuevos han llegado."""
    usuario = conexion.usuario
    zona = usuario.zona_horaria
    hoy = usuario.hoy()
    desde = datetime.combine(hoy - timedelta(days=1), time.min, tzinfo=ZoneInfo(zona))
    parametros = {
        "timeMin": desde.isoformat(),
        "timeMax": (desde + timedelta(days=DIAS_A_TRAER + 1)).isoformat(),
        "singleEvents": "true",          # las repeticiones, una a una
        "showDeleted": "true",           # para enterarnos de lo borrado
        "maxResults": "250",
    }
    locales = {
        e.google_id: e
        for e in db.session.scalars(
            db.select(Evento).where(Evento.usuario_id == usuario.id, Evento.google_id.is_not(None))
        )
    }

    nuevos = 0
    pagina = None
    while True:
        respuesta = _api(conexion, "GET", URL_EVENTOS, params={**parametros, **({"pageToken": pagina} if pagina else {})})
        if respuesta.status_code != 200:
            raise ErrorGoogle(f"Listar eventos: {respuesta.status_code}")
        cuerpo = respuesta.json()
        for item in cuerpo.get("items", []):
            local = locales.get(item["id"])
            if item.get("status") == "cancelled":
                if local is not None:
                    db.session.delete(local)
                continue
            if "start" not in item:
                continue
            if local is None:
                local = Evento(usuario_id=usuario.id, origen="google", google_id=item["id"], tipo="evento")
                db.session.add(local)
                nuevos += 1
            elif item.get("updated") and local.actualizado_en and \
                    datetime.fromisoformat(item["updated"]) <= _en_utc(local.actualizado_en):
                continue                                     # lo de la app es más reciente
            _aplicar_de_google(local, item, zona)
        pagina = cuerpo.get("nextPageToken")
        if not pagina:
            break
    return nuevos


def sincronizar(conexion):
    """Manda a Google lo que falte y trae lo de Google."""
    pendientes = db.session.scalars(
        db.select(Evento).where(
            Evento.usuario_id == conexion.usuario_id,
            Evento.google_id.is_(None),
            Evento.fecha >= conexion.usuario.hoy() - timedelta(days=1),
        )
    ).all()
    for evento in pendientes:
        cuerpo = a_google(evento, conexion)
        respuesta = _api(conexion, "POST", URL_EVENTOS, json=cuerpo)
        if respuesta.status_code in (200, 201):
            evento.google_id = respuesta.json()["id"]
    nuevos = traer_de_google(conexion)
    conexion.ultima_sincronizacion = ahora_utc()
    db.session.commit()
    return len(pendientes), nuevos


def sincronizar_si_toca(usuario):
    """Sincroniza en silencio si hace rato que no se hace (al abrir la agenda)."""
    conexion = _conexion_de(usuario)
    if conexion is None:
        return
    if conexion.ultima_sincronizacion and ahora_utc() - _en_utc(conexion.ultima_sincronizacion) < SINCRONIZAR_CADA:
        return
    try:
        sincronizar(conexion)
    except PermisoRetirado:
        _olvidar_conexion(conexion)
        flash("Google ha retirado el permiso del calendario. Vuelve a conectarlo desde tu perfil.", "error")
    except ErrorGoogle:
        db.session.rollback()          # sin conexión: ya se hará la próxima vez


def estado_conexion(usuario):
    """Para pintar el panel de la agenda."""
    return {"disponible": configurado(), "conexion": _conexion_de(usuario)}


# ──────────────────────────────────────────────────────────────
# Páginas: conectar, volver de Google, sincronizar, desconectar
# ──────────────────────────────────────────────────────────────

@bp.before_request
@login_required
def _requiere_sesion():
    """Hay que haber iniciado sesión."""


@bp.post("/conectar")
def conectar():
    if not configurado():
        flash("Falta configurar las claves de Google en el servidor.", "error")
        return redirect(url_for("perfil.inicio"))
    # «state» evita que otra web nos cuele una respuesta de Google
    session["google_state"] = secrets.token_urlsafe(24)
    parametros = {
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "redirect_uri": _url_vuelta(),
        "response_type": "code",
        "scope": PERMISOS,
        "access_type": "offline",        # para recibir el refresh token
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": session["google_state"],
    }
    return redirect(f"{URL_AUTORIZACION}?{urlencode(parametros)}")


@bp.get("/vuelta")
def vuelta():
    esperado = session.pop("google_state", None)
    if not esperado or request.args.get("state") != esperado:
        flash("No se ha podido conectar con Google. Inténtalo otra vez.", "error")
        return redirect(url_for("perfil.inicio"))
    if request.args.get("error"):
        flash("Has cancelado la conexión con Google. Puedes conectarlo cuando quieras.", "info")
        return redirect(url_for("perfil.inicio"))

    try:
        cuerpo = _pedir_token({
            "grant_type": "authorization_code",
            "code": request.args.get("code", ""),
            "redirect_uri": _url_vuelta(),
        })
        if "refresh_token" not in cuerpo:
            raise ErrorGoogle("Google no ha enviado refresh token")
        if "calendar.events" not in cuerpo.get("scope", ""):
            flash("Para sincronizar hay que marcar la casilla del calendario en la pantalla de Google.", "error")
            return redirect(url_for("perfil.inicio"))

        conexion = _conexion_de(current_user) or ConexionGoogle(usuario_id=current_user.id)
        conexion.refresh_token = cuerpo["refresh_token"]
        _guardar_access_token(conexion, cuerpo)
        db.session.add(conexion)
        info = _http("GET", URL_USUARIO, headers={"Authorization": f"Bearer {conexion.access_token}"})
        if info.status_code == 200:
            conexion.email = info.json().get("email")
        db.session.commit()

        enviados, nuevos = sincronizar(conexion)
    except ErrorGoogle:
        db.session.rollback()
        flash("Google no ha respondido bien. Inténtalo de nuevo en un rato.", "error")
        return redirect(url_for("perfil.inicio"))

    flash(f"¡Conectado con Google Calendar! 🎉 Enviados {enviados} eventos y traídos {nuevos}.", "exito")
    return redirect(url_for("perfil.inicio"))


@bp.post("/sincronizar")
def sincronizar_ahora():
    conexion = _conexion_de(current_user)
    if conexion is None:
        return redirect(url_for("perfil.inicio"))
    try:
        enviados, nuevos = sincronizar(conexion)
        flash(f"Sincronizado ✓ Enviados {enviados}, nuevos de Google {nuevos}.", "exito")
    except PermisoRetirado:
        _olvidar_conexion(conexion)
        flash("Google ha retirado el permiso. Vuelve a conectarlo desde tu perfil.", "error")
    except ErrorGoogle:
        db.session.rollback()
        flash("No se ha podido hablar con Google. Inténtalo en un rato.", "error")
    return redirect(url_for("perfil.inicio"))


@bp.post("/privacidad")
def privacidad():
    conexion = _conexion_de(current_user)
    if conexion is not None:
        conexion.detalle_citas = request.form.get("detalle_citas") == "si"
        db.session.commit()
        # Actualizar en Google las citas que ya estaban enviadas
        citas = db.session.scalars(
            db.select(Evento).where(
                Evento.usuario_id == current_user.id, Evento.tipo == "cita",
                Evento.google_id.is_not(None), Evento.origen == "app",
            )
        ).all()
        fallos = sum(not enviar(cita) for cita in citas)
        if fallos:
            flash("Algunas citas no se han podido actualizar en Google; se reintentará.", "info")
        flash("Preferencia guardada ✓", "exito")
    return redirect(url_for("perfil.inicio"))


@bp.post("/desconectar")
def desconectar():
    conexion = _conexion_de(current_user)
    if conexion is not None:
        try:
            _http("POST", URL_REVOCAR, data={"token": conexion.refresh_token})
        except ErrorGoogle:
            pass                         # aunque falle, aquí se olvida igualmente
        _olvidar_conexion(conexion)
        flash("Google Calendar desconectado. Tus eventos siguen aquí y en Google.", "info")
    return redirect(url_for("perfil.inicio"))
