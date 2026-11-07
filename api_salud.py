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


# La hora dentro de un texto tal como lo escribe Atajos según el idioma:
# «7 nov 2026, 0:32», «7/11/26 23:40», «11:05 p. m.»…
_HORA_EN_TEXTO = re.compile(r"(\d{1,2}):(\d{2})(?::\d{2})?\s*([ap])?\.?\s*m?\.?", re.IGNORECASE)


def _hora(valor, zona):
    """«23:40», una fecha y hora ISO o una fecha escrita por Atajos → time
    en la zona del usuario."""
    if not valor:
        return None
    texto = str(valor).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", texto):
        momento = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        if momento.tzinfo is not None:
            momento = momento.astimezone(zona)
        return momento.time().replace(second=0, microsecond=0)
    encontrada = _HORA_EN_TEXTO.findall(texto)
    if not encontrada:
        raise ValueError(f"no encuentro la hora en «{texto[:40]}»")
    horas, minutos, ampm = encontrada[-1]
    horas, minutos = int(horas), int(minutos)
    if ampm.lower() == "p" and horas < 12:
        horas += 12
    elif ampm.lower() == "a" and horas == 12:
        horas = 0
    return time(horas, minutos)


def _lineas(valor):
    """Una lista de Atajos llega como texto con un elemento por línea
    (o como lista JSON)."""
    if isinstance(valor, list):
        return [str(v).strip() for v in valor if str(v).strip()]
    return [linea.strip() for linea in str(valor or "").splitlines() if linea.strip()]


_FASES = {   # cómo llama Salud a cada fase (español e inglés) → nuestra fase
    "profundo": "profundo", "deep": "profundo",
    "rem": "rem",
    "principal": "ligero", "básico": "ligero", "basico": "ligero", "esencial": "ligero", "núcleo": "ligero", "nucleo": "ligero", "ligero": "ligero", "core": "ligero",
    "despierto": "despierto", "awake": "despierto",
    "en cama": "cama", "in bed": "cama", "inbed": "cama",
}


_GENERICO = ("dormido", "asleep", "sin especificar", "unspecified")


def _fase(texto):
    texto = texto.lower()
    for nombre, fase in _FASES.items():
        if nombre in texto:
            return fase
    if not texto or any(g in texto for g in _GENERICO):
        return "dormido"      # «Dormido» sin fase (iPhone u otras apps)
    return "ligero"           # otro nombre de fase («Básico», «Esencial»…): es sueño ligero


def _tramos_de_sueno(inicios, finales, zona, valores=None):
    """Con todos los tramos de la noche (inicio y fin de cada muestra)
    calcula el tiempo dormido como Salud: suma los tramos sin contar dos
    veces los que se pisan (reloj + iPhone). Si llegan las fases (Valor)
    y hay fases del reloj, se ignoran los «Dormido» genéricos, los ratos
    despierto y «En cama», igual que hace Salud. Las horas desde las 15:00
    se cuentan como del día anterior.
    Devuelve (acostarse, levantarse, minutos, fases) o None si no hay tramos."""
    inicios, finales = _lineas(inicios), _lineas(finales)
    if len(inicios) < 2 or len(inicios) != len(finales):
        return None
    valores = _lineas(valores)
    fases_muestra = [_fase(v) for v in valores] if len(valores) == len(inicios) else ["dormido"] * len(inicios)

    def minuto(hora):
        m = hora.hour * 60 + hora.minute
        return m - 1440 if hora.hour >= 15 else m

    todos = []
    for ini, fin, fase in zip(inicios, finales, fases_muestra):
        a, b = minuto(_hora(ini, zona)), minuto(_hora(fin, zona))
        if b < a:
            b += 1440
        todos.append((a, b, fase))

    hay_fases = any(f in ("profundo", "rem", "ligero") for *_, f in todos)
    validas = ("profundo", "rem", "ligero") if hay_fases else ("dormido",)
    elegidos = [t for t in todos if t[2] in validas] or todos
    fases = {}
    for a, b, f in todos:
        if f in ("profundo", "rem", "ligero", "despierto") and hay_fases:
            fases[f"minutos_{f}"] = fases.get(f"minutos_{f}", 0) + (b - a)
    tramos = sorted((a, b) for a, b, _ in elegidos)

    total, actual = 0, list(tramos[0])
    for a, b in tramos[1:]:
        if a <= actual[1]:
            actual[1] = max(actual[1], b)
        else:
            total += actual[1] - actual[0]
            actual = [a, b]
    total += actual[1] - actual[0]

    def a_hora(m):
        m %= 1440
        return time(m // 60, m % 60)

    return a_hora(tramos[0][0]), a_hora(max(b for _, b in tramos)), min(total, 1440), fases


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
        # También vale sin «diccionario»: acostarse / levantarse sueltos
        if not isinstance(sueno, dict) and any(datos.get(k) for k in ("acostarse", "levantarse", "horas_sueno")):
            sueno = {"acostarse": datos.get("acostarse"), "levantarse": datos.get("levantarse"),
                     "horas": datos.get("horas_sueno"), "fecha": datos.get("fecha_sueno"),
                     "fases": datos.get("fases")}
        if isinstance(sueno, dict):
            minutos = _numero(sueno.get("minutos"), entero=True, maximo=1440)
            tramos = _tramos_de_sueno(sueno.get("acostarse"), sueno.get("levantarse"), zona, sueno.get("fases"))
            fases_reloj = {}
            if tramos:
                acostarse, levantarse, dormido, fases_reloj = tramos
                if minutos is None:
                    minutos = dormido
            else:
                acostarse, levantarse = _hora(sueno.get("acostarse"), zona), _hora(sueno.get("levantarse"), zona)
            if minutos is None and sueno.get("horas") not in (None, ""):
                minutos = round(_numero(sueno.get("horas"), maximo=24) * 60)
            if minutos is None and acostarse and levantarse:
                minutos = minutos_entre(acostarse, levantarse)
            fases = {f"minutos_{f}": _numero(sueno.get(f), entero=True, maximo=1440)
                     for f in ("profundo", "rem", "ligero", "despierto")}
            for clave, valor in fases_reloj.items():
                if fases[clave] is None:
                    fases[clave] = min(valor, 1440)
            if minutos is not None or any(v is not None for v in fases.values()):
                guardar_sueno(usuario.id, _fecha(sueno.get("fecha"), hoy), "reloj",
                              minutos_dormido=minutos, hora_acostarse=acostarse,
                              hora_levantarse=levantarse, **fases)
                if minutos is not None:
                    texto = f"sueño {minutos // 60} h {minutos % 60} min"
                    if acostarse and levantarse:
                        texto += f" (de {acostarse:%H:%M} a {levantarse:%H:%M})"
                    if datos.get("diagnostico") or request.args.get("diagnostico"):
                        from collections import Counter
                        valores = Counter(_lineas(sueno.get("fases")))
                        texto += (f" [inicios {len(_lineas(sueno.get('acostarse')))}, finales {len(_lineas(sueno.get('levantarse')))},"
                                  f" fases {sum(valores.values())}: "
                                  + ", ".join(f"{v[:25]}×{n}" for v, n in valores.most_common(8))
                                  + f" | primeras: {' / '.join(_lineas(sueno.get('acostarse'))[:2])[:80]}]")
                    guardado.append(texto)
    except (ValueError, TypeError, AttributeError, IndexError) as error:
        db.session.rollback()
        return {"ok": False, "mensaje": f"Algún dato no se entiende ({error})."}, 400

    db.session.commit()
    if not guardado:
        return {"ok": True, "mensaje": "Ha llegado, pero no traía datos nuevos."}
    return {"ok": True, "mensaje": f"Guardado en {current_app.config['APP_NOMBRE']}: " + ", ".join(guardado) + " ✓"}
