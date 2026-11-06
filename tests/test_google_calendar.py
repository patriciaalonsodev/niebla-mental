# ══════════════════════════════════════════════════════════════
#  App de organización · tests/test_google_calendar.py
#  Sincronización con Google Calendar, con un Google simulado
#  (los tests no salen a internet ni necesitan claves reales)
# ══════════════════════════════════════════════════════════════

import itertools
from datetime import datetime, time, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest
from flask import g

import google_calendar as gc
from conftest import crear_usuario, entrar
from extensions import db
from models import ConexionGoogle, Evento, Usuario

AHORA = datetime(2026, 11, 6, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
HOY = AHORA.date()


class Respuesta:
    def __init__(self, status_code=200, datos=None):
        self.status_code = status_code
        self._datos = datos
        self.content = b"{}" if datos is not None else b""

    def json(self):
        return self._datos


class GoogleFalso:
    """Imita lo justo de Google: tokens, userinfo y la API de eventos."""

    def __init__(self):
        self.eventos = {}
        self.peticiones = []
        self.ids = itertools.count(1)
        self.permiso_retirado = False
        self.caido = False
        self.scope = gc.PERMISOS

    def __call__(self, metodo, url, **opciones):
        self.peticiones.append((metodo, url, opciones))
        if self.caido:
            raise gc.ErrorGoogle("sin conexión")
        if url == gc.URL_TOKEN:
            if self.permiso_retirado:
                return Respuesta(400, {"error": "invalid_grant"})
            datos = {"access_token": f"acceso-{next(self.ids)}", "expires_in": 3599, "scope": self.scope}
            if opciones["data"]["grant_type"] == "authorization_code":
                datos["refresh_token"] = "refresco-secreto"
            return Respuesta(200, datos)
        if url == gc.URL_USUARIO:
            return Respuesta(200, {"email": "patz@gmail.com"})
        if url == gc.URL_REVOCAR:
            return Respuesta(200, {})
        if url == gc.URL_EVENTOS and metodo == "POST":
            item = {**opciones["json"], "id": f"g{next(self.ids)}", "status": "confirmed", "updated": self._ahora()}
            self.eventos[item["id"]] = item
            return Respuesta(200, item)
        if url == gc.URL_EVENTOS and metodo == "GET":
            return Respuesta(200, {"items": list(self.eventos.values())})
        id_ = url.rsplit("/", 1)[-1]
        if id_ not in self.eventos:
            return Respuesta(404, {})
        if metodo == "PATCH":
            self.eventos[id_].update({**opciones["json"], "updated": self._ahora()})
            return Respuesta(200, self.eventos[id_])
        if metodo == "DELETE":
            del self.eventos[id_]
            return Respuesta(204)
        raise AssertionError(f"Petición inesperada: {metodo} {url}")

    @staticmethod
    def _ahora():
        return datetime.now(timezone.utc).isoformat()

    def desde_google(self, id_, summary, inicio, fin=None, **extra):
        """Añade un evento «creado en Google» (inicio: dict date/dateTime)."""
        self.eventos[id_] = {
            "id": id_, "summary": summary, "status": "confirmed", "start": inicio,
            "end": fin or inicio, "updated": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(), **extra,
        }

    def ultima(self, metodo):
        return [p for p in self.peticiones if p[0] == metodo][-1]


@pytest.fixture(autouse=True)
def reloj(monkeypatch):
    monkeypatch.setattr(Usuario, "ahora", lambda self: AHORA)


@pytest.fixture
def google(app, monkeypatch):
    app.config.update(GOOGLE_CLIENT_ID="id-de-prueba", GOOGLE_CLIENT_SECRET="secreto-de-prueba")
    falso = GoogleFalso()
    monkeypatch.setattr(gc, "_http", falso)
    return falso


def _conectar(cliente):
    respuesta = cliente.post("/google/conectar")
    state = parse_qs(urlsplit(respuesta.location).query)["state"][0]
    return cliente.get(f"/google/vuelta?state={state}&code=codigo", follow_redirects=True)


def _nuevo(cliente, titulo="Comida con mamá", **extra):
    datos = {"tipo": "evento", "titulo": titulo, "fecha": HOY.isoformat(), **extra}
    return cliente.post("/eventos/nuevo", data=datos, follow_redirects=True)


# ── Conectar ──────────────────────────────────────────────────

def test_sin_claves_se_ve_y_explica_que_falta(cliente_con_sesion):
    texto = cliente_con_sesion.get("/perfil/").get_data(as_text=True)
    assert "Google Calendar" in texto and "Todavía no está activado" in texto
    assert "GOOGLE_CLIENT_ID" in texto and "http://localhost/google/vuelta" in texto
    assert "Conectar con Google Calendar</button>" not in texto
    assert "Conectar con Google Calendar" in cliente_con_sesion.get("/eventos/").get_data(as_text=True)

def test_boton_conectar(cliente_con_sesion, google):
    assert "Conectar con Google Calendar" in cliente_con_sesion.get("/perfil/").get_data(as_text=True)
    respuesta = cliente_con_sesion.post("/google/conectar")
    destino = urlsplit(respuesta.location)
    parametros = parse_qs(destino.query)
    assert destino.netloc == "accounts.google.com"
    assert parametros["access_type"] == ["offline"]
    assert parametros["redirect_uri"] == ["http://localhost/google/vuelta"]
    assert "calendar.events" in parametros["scope"][0]


def test_conectar(cliente_con_sesion, google):
    texto = _conectar(cliente_con_sesion).get_data(as_text=True)
    conexion = ConexionGoogle.query.one()
    assert conexion.email == "patz@gmail.com" and conexion.refresh_token == "refresco-secreto"
    assert "Conectado con Google Calendar" in texto and "patz@gmail.com" in texto
    crudo = db.session.execute(db.text("SELECT refresh_token FROM conexiones_google")).scalar()
    assert "refresco-secreto" not in crudo                    # guardado cifrado


def test_state_incorrecto(cliente_con_sesion, google):
    cliente_con_sesion.post("/google/conectar")
    texto = cliente_con_sesion.get("/google/vuelta?state=falso&code=x", follow_redirects=True).get_data(as_text=True)
    assert ConexionGoogle.query.count() == 0 and "No se ha podido conectar" in texto


def test_cancelar_en_google(cliente_con_sesion, google):
    respuesta = cliente_con_sesion.post("/google/conectar")
    state = parse_qs(urlsplit(respuesta.location).query)["state"][0]
    texto = cliente_con_sesion.get(f"/google/vuelta?state={state}&error=access_denied", follow_redirects=True).get_data(as_text=True)
    assert ConexionGoogle.query.count() == 0 and "Has cancelado" in texto


def test_sin_permiso_de_calendario(cliente_con_sesion, google):
    google.scope = "openid email"                       # desmarcó la casilla del calendario
    texto = _conectar(cliente_con_sesion).get_data(as_text=True)
    assert ConexionGoogle.query.count() == 0 and "marcar la casilla del calendario" in texto


def test_al_conectar_envia_lo_que_ya_habia(cliente_con_sesion, google):
    _nuevo(cliente_con_sesion, "Ya estaba")
    _conectar(cliente_con_sesion)
    evento = Evento.query.one()
    assert evento.google_id and google.eventos[evento.google_id]["summary"] == "Ya estaba"


# ── App → Google ──────────────────────────────────────────────

def test_crear_editar_y_borrar_llega_a_google(cliente_con_sesion, google):
    _conectar(cliente_con_sesion)
    _nuevo(cliente_con_sesion, "Fisio", hora_inicio="17:00", lugar="Centro")
    evento = Evento.query.one()
    enviado = google.eventos[evento.google_id]
    assert enviado["summary"] == "Fisio" and enviado["location"] == "Centro"
    assert enviado["start"] == {"dateTime": "2026-11-06T17:00:00", "timeZone": "Europe/Madrid"}
    assert enviado["end"]["dateTime"] == "2026-11-06T18:00:00"           # 1 hora si no hay fin

    cliente_con_sesion.post(f"/eventos/{evento.id}/editar", data={
        "tipo": "evento", "titulo": "Fisio (cambiada)", "fecha": HOY.isoformat(), "hora_inicio": "",
    })
    assert google.eventos[evento.google_id]["summary"] == "Fisio (cambiada)"
    assert google.eventos[evento.google_id]["start"] == {"date": "2026-11-06"}   # ahora todo el día
    assert google.eventos[evento.google_id]["end"] == {"date": "2026-11-07"}

    google_id = evento.google_id
    cliente_con_sesion.post(f"/eventos/{evento.id}/borrar")
    assert google_id not in google.eventos and Evento.query.count() == 0


def test_citas_privadas_por_defecto(cliente_con_sesion, google):
    _conectar(cliente_con_sesion)
    _nuevo(cliente_con_sesion, "Psiquiatra", tipo="cita", lugar="Hospital", profesional="Dr. Ruiz",
           preguntas="¿Bajo la dosis?")
    enviado = google.eventos[Evento.query.one().google_id]
    assert enviado["summary"] == "🩺 Cita médica" and enviado["location"] is None
    assert "Psiquiatra" not in str(enviado) and "dosis" not in str(enviado)


def test_citas_con_detalle_si_se_elige(cliente_con_sesion, google):
    _conectar(cliente_con_sesion)
    _nuevo(cliente_con_sesion, "Reumatólogo", tipo="cita", profesional="Dra. López", preguntas="¿Pilates?")
    cliente_con_sesion.post("/google/privacidad", data={"detalle_citas": "si"})
    enviado = google.eventos[Evento.query.one().google_id]
    assert enviado["summary"] == "🩺 Reumatólogo" and "Dra. López" in enviado["description"]
    assert "Pilates" not in str(enviado)                # las preguntas nunca salen


def test_google_caido_no_impide_guardar(cliente_con_sesion, google):
    _conectar(cliente_con_sesion)
    google.caido = True
    texto = _nuevo(cliente_con_sesion, "Sin internet").get_data(as_text=True)
    assert Evento.query.one().google_id is None and "no ha llegado a Google" in texto

    google.caido = False
    cliente_con_sesion.post("/google/sincronizar")
    assert Evento.query.one().google_id in google.eventos


# ── Google → App ──────────────────────────────────────────────

def test_trae_eventos_de_google(cliente_con_sesion, google):
    google.desde_google("x1", "Cena con amigas", {"dateTime": "2026-11-07T21:00:00+01:00"},
                        {"dateTime": "2026-11-07T23:00:00+01:00"}, location="Bar Luna")
    google.desde_google("x2", "Puente", {"date": "2026-11-09"}, {"date": "2026-11-10"})
    _conectar(cliente_con_sesion)

    cena = Evento.query.filter_by(google_id="x1").one()
    assert (cena.origen, cena.titulo, cena.lugar) == ("google", "Cena con amigas", "Bar Luna")
    assert (cena.fecha, cena.hora_inicio, cena.hora_fin) == (HOY + timedelta(days=1), time(21), time(23))
    puente = Evento.query.filter_by(google_id="x2").one()
    assert puente.hora_inicio is None

    texto = cliente_con_sesion.get("/eventos/").get_data(as_text=True)
    assert "Cena con amigas" in texto


def test_cambios_y_borrados_en_google(cliente_con_sesion, google):
    google.desde_google("x1", "Cine", {"dateTime": "2026-11-07T18:00:00+01:00"})
    google.desde_google("x2", "Se cancela", {"date": "2026-11-08"})
    _conectar(cliente_con_sesion)

    google.desde_google("x1", "Cine (otra hora)", {"dateTime": "2026-11-07T20:00:00+01:00"})
    google.eventos["x2"]["status"] = "cancelled"
    cliente_con_sesion.post("/google/sincronizar")

    cine = Evento.query.filter_by(google_id="x1").one()
    assert (cine.titulo, cine.hora_inicio) == ("Cine (otra hora)", time(20))
    assert Evento.query.filter_by(google_id="x2").count() == 0


def test_mover_en_google_no_pisa_el_titulo_privado(cliente_con_sesion, google):
    _conectar(cliente_con_sesion)
    _nuevo(cliente_con_sesion, "Neuróloga", tipo="cita", hora_inicio="09:00")
    cita = Evento.query.one()
    # En Google la mueven a las 11 (allí se llama «🩺 Cita médica»)
    google.eventos[cita.google_id].update({
        "start": {"dateTime": "2026-11-06T11:00:00+01:00"},
        "end": {"dateTime": "2026-11-06T12:00:00+01:00"},
        "updated": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    })
    cliente_con_sesion.post("/google/sincronizar")
    db.session.refresh(cita)
    assert (cita.titulo, cita.hora_inicio) == ("Neuróloga", time(11))


# ── Tokens y desconexión ──────────────────────────────────────

def test_renueva_el_token_caducado(cliente_con_sesion, google):
    _conectar(cliente_con_sesion)
    conexion = ConexionGoogle.query.one()
    conexion.caduca_en = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.session.commit()
    _nuevo(cliente_con_sesion, "Después de una hora")
    renovaciones = [p for p in google.peticiones
                    if p[1] == gc.URL_TOKEN and p[2]["data"]["grant_type"] == "refresh_token"]
    assert renovaciones and Evento.query.one().google_id


def test_permiso_retirado_en_google(cliente_con_sesion, google):
    _conectar(cliente_con_sesion)
    conexion = ConexionGoogle.query.one()
    conexion.caduca_en = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.session.commit()
    google.permiso_retirado = True

    texto = _nuevo(cliente_con_sesion, "Sin permiso").get_data(as_text=True)
    assert ConexionGoogle.query.count() == 0 and Evento.query.count() == 1
    assert "Vuelve a conectarlo desde tu perfil" in texto


def test_desconectar(cliente_con_sesion, google):
    _conectar(cliente_con_sesion)
    _nuevo(cliente_con_sesion, "Se queda")
    texto = cliente_con_sesion.post("/google/desconectar", follow_redirects=True).get_data(as_text=True)
    assert google.ultima("POST")[1] == gc.URL_REVOCAR
    assert ConexionGoogle.query.count() == 0
    evento = Evento.query.one()
    assert evento.titulo == "Se queda" and evento.google_id is None
    assert "Conectar con Google Calendar" in texto


def test_cada_cual_con_su_google(app, google):
    crear_usuario(email="otra@example.com", nombre="Otra")
    crear_usuario()
    cliente = app.test_client()
    entrar(cliente, email="otra@example.com")
    _conectar(cliente)

    # Los tests comparten un mismo contexto de Flask y Flask-Login guarda
    # ahí el usuario; en la app real cada petición empieza de cero.
    g.pop("_login_user", None)
    cliente_patz = app.test_client()
    entrar(cliente_patz)
    _nuevo(cliente_patz, "De Patz")
    assert Evento.query.one().google_id is None          # Patz no ha conectado nada
    assert cliente_patz.post("/google/desconectar").status_code == 302
    assert ConexionGoogle.query.count() == 1             # la conexión de la otra sigue
