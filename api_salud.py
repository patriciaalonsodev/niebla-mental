# ══════════════════════════════════════════════════════════════
#  App de organización · api_salud.py
#  Entrada de datos del reloj: pasos, actividad, ejercicio y sueño.
#
#  - iPhone + Apple Watch: una automatización de Atajos lee Apple
#    Salud y llama aquí cada día (docs/apple-salud.md).
#  - Android: cualquier app que lea Health Connect y pueda enviar
#    datos a una dirección web (p. ej. con Tasker o similares).
#
#  Se identifica con una clave personal («Bearer») que se crea en el
#  Perfil. De la clave solo se guarda su huella SHA-256.
# ══════════════════════════════════════════════════════════════

import hashlib
import re
import secrets
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, request

from cuerpo import guardar_actividad, guardar_sueno, minutos_entre
from extensions import csrf, db
from models import Ejercicio, Usuario, ahora_utc

bp = Blueprint("api_salud", __name__, url_prefix="/api")
csrf.exempt(bp)          # aquí no hay formulario ni cookie: se entra con la clave


def huella(clave):
    return hashlib.sha256(clave.encode()).hexdigest()


def crear_clave(usuario):
    """Genera una clave nueva (la anterior deja de valer) y la devuelve
    una sola vez para enseñarla."""
    clave = "nm_" + secrets.token_urlsafe(32)
    usuario.api_token_hash = huella(clave)
    usuario.api_token_creado = ahora_utc()
    return clave


def _usuario_de_la_clave():
    cabecera = request.headers.get("Authorization", "")
    if not cabecera.startswith("Bearer "):
        return None
    clave = cabecera[len("Bearer "):].strip()
    if not clave:
        return None
    # Se busca por la huella: la clave nunca se compara ni se guarda en claro
    return db.session.scalar(db.select(Usuario).filter_by(api_token_hash=huella(clave)))


# ──────────────────────────────────────────────────────────────
# Leer números y horas tal y como los manda Atajos
# (puede mandar «8.345», «8345,0», «7,5» o números de verdad)
# ──────────────────────────────────────────────────────────────

_MILES = re.compile(r"^\d{1,3}(\.\d{3})+$")


def _numero(valor, entero=False, maximo=None):
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ValueError("número no válido")
    if isinstance(valor, (int, float)):
        numero = float(valor)
    else:
        texto = str(valor).strip().replace(" ", "").replace(" ", "")
        if _MILES.match(texto):
            texto = texto.replace(".", "")                   # «8.345» → 8345
        elif "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")  # «1.234,5» → 1234.5
        else:
            texto = texto.replace(",", ".")
        numero = float(texto)
    if numero < 0 or (maximo is not None and numero > maximo):
        raise ValueError("fuera de rango")
    return round(numero) if entero else round(numero, 2)


def _hora(valor, zona):
    """«23:40», «23:40:12» o una fecha y hora ISO → time en la zona del usuario."""
    if not valor:
        return None
    texto = str(valor).strip()
    if "T" in texto or "-" in texto[:10]:
        momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        if momento.tzinfo is not None:
            momento = momento.astimezone(zona)
        return momento.time().replace(second=0, microsecond=0)
    partes = texto.split(":")
    return time(int(partes[0]), int(partes[1]))


def _fecha(valor, hoy):
    if not valor:
        return hoy
    texto = str(valor).strip()[:10]
    fecha = date.fromisoformat(texto)
    if fecha > hoy:
        raise ValueError("fecha futura")
    return fecha


# ──────────────────────────────────────────────────────────────
# La entrada
# ──────────────────────────────────────────────────────────────

@bp.post("/salud")
def recibir():
    """JSON con lo que se tenga (todo es opcional):
    {
      "fecha": "2026-11-06",                 # día de la actividad (hoy si falta)
      "pasos": 8345, "minutos_activos": 34, "kcal_activas": 320, "distancia_km": 5.2,
      "ejercicios": [{"tipo": "Paseo", "minutos": 30, "kcal": 120}],
      "sueno": {"fecha": "2026-11-06",       # día en que te despertaste (hoy si falta)
                "horas": 7.2, "minutos": 432, "acostarse": "23:40", "levantarse": "07:12",
                "profundo": 60, "rem": 90, "ligero": 250, "despierto": 12}
    }"""
    usuario = _usuario_de_la_clave()
    if usuario is None:
        return {"ok": False, "mensaje": "Clave no válida. Créala de nuevo en el Perfil de la app."}, 401
    zona = ZoneInfo(usuario.zona_horaria)

    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return {"ok": False, "mensaje": "Tiene que llegar un JSON (un «diccionario» en Atajos)."}, 400

    hoy = usuario.hoy()
    guardado = []
    try:
        fecha = _fecha(datos.get("fecha"), hoy)
        actividad = {
            "pasos": _numero(datos.get("pasos"), entero=True, maximo=200000),
            "minutos_activos": _numero(datos.get("minutos_activos"), entero=True, maximo=1440),
            "kcal_activas": _numero(datos.get("kcal_activas"), entero=True, maximo=10000),
            "distancia_km": _numero(datos.get("distancia_km"), maximo=300),
        }
        if any(v is not None for v in actividad.values()):
            guardar_actividad(usuario.id, fecha, "reloj", **actividad)
            if actividad["pasos"] is not None:
                guardado.append(f"{actividad['pasos']} pasos")

        for ejercicio in (datos.get("ejercicios") or [])[:20]:
            minutos = _numero(ejercicio.get("minutos"), entero=True, maximo=1440)
            if not minutos:
                continue
            db.session.add(Ejercicio(
                usuario_id=usuario.id, fecha=_fecha(ejercicio.get("fecha"), hoy) if ejercicio.get("fecha") else fecha,
                tipo=str(ejercicio.get("tipo") or "Ejercicio")[:80], minutos=minutos,
                kcal=_numero(ejercicio.get("kcal"), entero=True, maximo=5000), origen="reloj",
            ))
            guardado.append(f"{ejercicio.get('tipo') or 'ejercicio'} {minutos} min")

        sueno = datos.get("sueno")
        if isinstance(sueno, dict):
            acostarse, levantarse = _hora(sueno.get("acostarse"), zona), _hora(sueno.get("levantarse"), zona)
            minutos = _numero(sueno.get("minutos"), entero=True, maximo=1440)
            if minutos is None and sueno.get("horas") not in (None, ""):
                minutos = round(_numero(sueno.get("horas"), maximo=24) * 60)
            if minutos is None and acostarse and levantarse:
                minutos = minutos_entre(acostarse, levantarse)
            fases = {f"minutos_{f}": _numero(sueno.get(f), entero=True, maximo=1440)
                     for f in ("profundo", "rem", "ligero", "despierto")}
            if minutos is not None or any(v is not None for v in fases.values()):
                guardar_sueno(usuario.id, _fecha(sueno.get("fecha"), hoy), "reloj",
                              minutos_dormido=minutos, hora_acostarse=acostarse,
                              hora_levantarse=levantarse, **fases)
                if minutos is not None:
                    guardado.append(f"sueño {minutos // 60} h {minutos % 60} min")
    except (ValueError, TypeError, AttributeError, IndexError) as error:
        db.session.rollback()
        return {"ok": False, "mensaje": f"Algún dato no se entiende ({error})."}, 400

    db.session.commit()
    if not guardado:
        return {"ok": True, "mensaje": "Ha llegado, pero no traía datos nuevos."}
    return {"ok": True, "mensaje": f"Guardado en {current_app.config['APP_NOMBRE']}: " + ", ".join(guardado) + " ✓"}
