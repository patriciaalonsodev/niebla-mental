# ══════════════════════════════════════════════════════════════
#  App de organización · compra.py
#  Lista de la compra: compacta, por pasillos, con productos
#  preparados, lo que sueles comprar, voz y escáner
#  Patricia Alonso · patriciaalonso.es
# ══════════════════════════════════════════════════════════════

import re
import unicodedata

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from formularios import FormularioCompra
from models import ItemCompra, ProductoFrecuente, ahora_utc
from utilidades import obtener_propio

bp = Blueprint("compra", __name__, url_prefix="/compra")

# Productos preparados, ordenados por pasillo del súper
CATALOGO = {
    "🥦 Fruta y verdura": ["Plátanos", "Manzanas", "Naranjas", "Limones", "Tomates", "Lechuga",
                          "Cebollas", "Patatas", "Zanahorias", "Ajos", "Pimientos", "Aguacates"],
    "🥛 Lácteos y huevos": ["Leche", "Leche sin lactosa", "Yogures", "Queso", "Mantequilla", "Huevos"],
    "🍞 Pan y desayuno": ["Pan", "Pan de molde", "Galletas", "Cereales", "Café", "Infusiones"],
    "🍗 Carne y pescado": ["Pollo", "Carne picada", "Jamón", "Pavo", "Merluza", "Salmón"],
    "🥫 Despensa": ["Arroz", "Pasta", "Legumbres", "Aceite de oliva", "Atún en lata", "Tomate frito",
                   "Sal", "Azúcar", "Harina", "Caldo"],
    "🧊 Congelados": ["Verduras congeladas", "Pescado congelado", "Helado"],
    "🥤 Bebidas": ["Agua", "Zumo", "Bebida vegetal"],
    "🧽 Limpieza": ["Lavavajillas", "Detergente", "Suavizante", "Papel de cocina", "Bolsas de basura",
                   "Lejía", "Fregasuelos"],
    "🧴 Higiene": ["Papel higiénico", "Gel de ducha", "Champú", "Pasta de dientes", "Desodorante",
                  "Compresas"],
    "💊 Farmacia": ["Paracetamol", "Ibuprofeno", "Tiritas", "Crema hidratante"],
}
OTROS = "🛒 Otros"
MAX_FRECUENTES = 12

# «2 leches», «1 kg patatas», «500 g de queso» → cantidad + producto
_CANTIDAD_DELANTE = re.compile(
    r"^(\d+(?:[.,]\d+)?\s*(?:kg|g|gr|l|litros?|ml|uds?|unidades|paquetes?|botes?|latas?|docenas?)?)"
    r"\s+(?:de\s+)?(.+)$",
    re.IGNORECASE,
)


def normalizar(texto):
    """Minúsculas, sin tildes ni espacios de más: «Plátanos » → «platanos»."""
    sin_tildes = unicodedata.normalize("NFD", texto.strip().lower())
    return " ".join("".join(c for c in sin_tildes if unicodedata.category(c) != "Mn").split())


def _variantes(palabra):
    """Formas con y sin plural: «tomates» → tomates, tomate, tomat;
    «limones» → limones, limone, limon."""
    formas = [palabra]
    if palabra.endswith("s") and len(palabra) > 3:
        formas.append(palabra[:-1])
    if palabra.endswith("es") and len(palabra) > 4:
        formas.append(palabra[:-2])
    return formas


# Índice para adivinar el pasillo de un producto escrito a mano
_PASILLO_DE = {normalizar(p): pasillo for pasillo, productos in CATALOGO.items() for p in productos}
_PALABRAS_PASILLO = {}
for _nombre, _pasillo in _PASILLO_DE.items():
    for _palabra in _nombre.split():
        if len(_palabra) > 3:
            for _forma in _variantes(_palabra):
                _PALABRAS_PASILLO.setdefault(_forma, _pasillo)


def pasillo_de(nombre):
    """«Leche entera» → «🥛 Lácteos y huevos»; si no se sabe, «🛒 Otros»."""
    clave = normalizar(nombre)
    if clave in _PASILLO_DE:
        return _PASILLO_DE[clave]
    for palabra in clave.split():
        for forma in _variantes(palabra):
            if forma in _PALABRAS_PASILLO:
                return _PALABRAS_PASILLO[forma]
    return OTROS


def separar_cantidad(texto):
    """«2 leches» → ("Leches", "2"); «pan» → ("Pan", None)."""
    texto = texto.strip()
    encontrado = _CANTIDAD_DELANTE.match(texto)
    if encontrado:
        cantidad, nombre = encontrado.group(1).strip(), encontrado.group(2).strip()
    else:
        cantidad, nombre = None, texto
    return nombre[:1].upper() + nombre[1:], cantidad


def _recordar_frecuente(nombre, contar=True):
    clave = normalizar(nombre)[:120]
    frecuente = db.session.scalar(
        db.select(ProductoFrecuente).filter_by(usuario_id=current_user.id, clave=clave)
    )
    if frecuente is None:
        db.session.add(ProductoFrecuente(usuario_id=current_user.id, clave=clave, nombre=nombre[:120]))
    else:
        if contar:
            frecuente.veces += 1
        frecuente.ultima_vez = ahora_utc()


def _anadir(texto, cantidad=None):
    """Añade un producto si no está ya pendiente. Devuelve True si lo añadió."""
    nombre, cantidad_escrita = separar_cantidad(texto)
    nombre = nombre[:120]
    if not nombre:
        return False
    pendientes = db.session.scalars(
        db.select(ItemCompra).filter_by(usuario_id=current_user.id, comprado=False)
    )
    if any(normalizar(i.nombre) == normalizar(nombre) for i in pendientes):
        return False                     # ya estaba en la lista
    db.session.add(ItemCompra(
        usuario_id=current_user.id, nombre=nombre, cantidad=(cantidad or cantidad_escrita or None),
    ))
    _recordar_frecuente(nombre)
    return True


@bp.before_request
@login_required
def _requiere_sesion():
    """Todas las páginas de la compra necesitan haber iniciado sesión."""


def _pintar_listado(form):
    items = db.session.scalars(
        db.select(ItemCompra).filter_by(usuario_id=current_user.id).order_by(ItemCompra.creado_en)
    ).all()
    # Lo pendiente, ordenado por pasillo (así lo de la fruta queda junto);
    # lo tachado, al final de la misma lista
    orden = list(CATALOGO) + [OTROS]
    pendientes = sorted((i for i in items if not i.comprado), key=lambda i: orden.index(pasillo_de(i.nombre)))
    tachados = [i for i in items if i.comprado]

    en_lista = {normalizar(i.nombre) for i in items if not i.comprado}
    # «Para la próxima»: lo que has comprado antes y ahora no está en la lista
    frecuentes = [
        f for f in db.session.scalars(
            db.select(ProductoFrecuente)
            .filter_by(usuario_id=current_user.id)
            .order_by(ProductoFrecuente.ultima_vez.desc(), ProductoFrecuente.veces.desc())
            .limit(MAX_FRECUENTES * 2)
        )
        if f.clave not in en_lista
    ][:MAX_FRECUENTES]

    return render_template(
        "compra/listado.html",
        form=form,
        lista=pendientes + tachados,
        num_pendientes=len(pendientes),
        num_tachados=len(tachados),
        frecuentes=frecuentes,
        catalogo=CATALOGO,
        en_lista=en_lista,
        normalizar=normalizar,
    )


@bp.get("/")
def listado():
    return _pintar_listado(FormularioCompra())


@bp.post("/nuevo")
def nuevo():
    # Varios de golpe (dictado por voz o escáner): uno por línea
    varios = [linea for linea in request.form.get("varios", "").splitlines() if linea.strip()]
    if varios:
        anadidos = sum(_anadir(linea) for linea in varios[:30])
        db.session.commit()
        flash(f"Añadidos {anadidos} productos 🛒" if anadidos != 1 else "Añadido 1 producto 🛒", "exito")
        return redirect(url_for("compra.listado"))

    form = FormularioCompra()
    if not form.validate_on_submit():
        return _pintar_listado(form), 400
    _anadir(form.nombre.data, form.cantidad.data)
    db.session.commit()
    # Sin mensaje: se suelen apuntar varias cosas seguidas
    return redirect(url_for("compra.listado"))


@bp.post("/<int:item_id>/marcar")
def marcar(item_id):
    item = obtener_propio(ItemCompra, item_id)
    item.comprado = not item.comprado
    if item.comprado:
        _recordar_frecuente(item.nombre, contar=False)   # se guarda para la próxima compra
    db.session.commit()
    return redirect(url_for("compra.listado"))


@bp.post("/<int:item_id>/borrar")
def borrar(item_id):
    item = obtener_propio(ItemCompra, item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("compra.listado"))


@bp.post("/vaciar-comprados")
def vaciar_comprados():
    borrados = db.session.execute(
        db.delete(ItemCompra).where(
            ItemCompra.usuario_id == current_user.id, ItemCompra.comprado.is_(True)
        )
    ).rowcount
    db.session.commit()
    if borrados:
        flash(f"Quitados {borrados} productos tachados. Los tienes en «Para la próxima» 🛒", "info")
    return redirect(url_for("compra.listado"))


@bp.post("/frecuentes/<int:frecuente_id>/olvidar")
def olvidar_frecuente(frecuente_id):
    """Quitar algo de «lo que sueles comprar»."""
    frecuente = obtener_propio(ProductoFrecuente, frecuente_id)
    db.session.delete(frecuente)
    db.session.commit()
    return redirect(url_for("compra.listado"))
