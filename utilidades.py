# ══════════════════════════════════════════════════════════════
#  App de organización · utilidades.py
#  Funciones compartidas por las secciones
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

from flask import abort
from flask_login import current_user

from extensions import db
from models import Etiqueta


def obtener_propio(modelo, id_):
    """Devuelve el registro solo si pertenece al usuario; si no, 404.
    Así nadie puede ver o tocar datos ajenos cambiando el número de la URL."""
    objeto = db.session.get(modelo, id_)
    if objeto is None or objeto.usuario_id != current_user.id:
        abort(404)
    return objeto


# ──────────────────────────────────────────────────────────────
# Fechas en español (sin depender del idioma del servidor)
# ──────────────────────────────────────────────────────────────

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def fecha_larga(fecha):
    """date(2026, 11, 6) → "jueves 6 de noviembre"."""
    return f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}"


def fecha_corta(fecha):
    """date(2026, 11, 6) → "jue 6"."""
    return f"{DIAS[fecha.weekday()][:3]} {fecha.day}"


def hora_local(momento):
    """Datetime guardado en UTC → "HH:MM" en la zona del usuario.
    (SQLite devuelve las fechas sin zona: se entiende que son UTC.)"""
    from datetime import timezone
    from zoneinfo import ZoneInfo

    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(ZoneInfo(current_user.zona_horaria)).strftime("%H:%M")


# ──────────────────────────────────────────────────────────────
# Etiquetas (compartidas por notas y diario)
# ──────────────────────────────────────────────────────────────

def etiquetas_desde_texto(texto):
    """"Médico, ideas ,médico" → [Etiqueta('médico'), Etiqueta('ideas')].
    Reutiliza las que ya existen y crea las nuevas."""
    nombres = []
    for trozo in (texto or "").split(","):
        nombre = trozo.strip().lower()[:40]
        if nombre and nombre not in nombres:
            nombres.append(nombre)
    if not nombres:
        return []

    existentes = {
        e.nombre: e
        for e in db.session.scalars(
            db.select(Etiqueta).filter(
                Etiqueta.usuario_id == current_user.id, Etiqueta.nombre.in_(nombres)
            )
        )
    }
    etiquetas = []
    for nombre in nombres:
        etiqueta = existentes.get(nombre)
        if etiqueta is None:
            etiqueta = Etiqueta(usuario_id=current_user.id, nombre=nombre)
            db.session.add(etiqueta)
        etiquetas.append(etiqueta)
    return etiquetas


def kg(numero):
    """65.5 → "65,5"; 70.0 → "70" (números a la española, sin ceros de más)."""
    if numero is None:
        return ""
    return f"{float(numero):.1f}".rstrip("0").rstrip(".").replace(".", ",")


def miles(numero):
    """8345 → "8.345" (separador de miles a la española)."""
    return f"{int(numero or 0):,}".replace(",", ".")


def fecha_larga_dt(momento):
    """Datetime en UTC → "jueves 6 de noviembre" en la zona del usuario."""
    from datetime import timezone
    from zoneinfo import ZoneInfo

    if momento is None:
        return ""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return fecha_larga(momento.astimezone(ZoneInfo(current_user.zona_horaria)).date())
