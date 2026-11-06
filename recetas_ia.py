# ══════════════════════════════════════════════════════════════
#  App de organización · recetas_ia.py
#  Recetas sugeridas por la IA (Claude), con sus macros
#  Patricia Alonso · patriciaalonso.es
#
#  - Usa el SDK oficial de Anthropic con «salida estructurada»: Claude
#    devuelve las recetas ya en el formato de abajo (validado), así no
#    hay que interpretar texto libre.
#  - Si el modelo principal rechaza la petición, la API la reintenta
#    sola con otro modelo («fallbacks»).
#  - Coste orientativo: unos céntimos por búsqueda. Hay un límite de
#    búsquedas al día por persona (RECETAS_IA_AL_DIA).
# ══════════════════════════════════════════════════════════════

import base64
import logging
from io import BytesIO
from typing import Literal, Optional

import anthropic
import requests
from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

MODELO = "claude-opus-5-5"
log = logging.getLogger(__name__)


class Ingrediente(BaseModel):
    nombre: str
    cantidad: str = Field(description="Cantidad para todas las raciones, p. ej. «200 g» o «1 cucharada»")


class Receta(BaseModel):
    titulo: str
    descripcion: str = Field(description="Una frase que la haga apetecible")
    raciones: int
    tiempo_minutos: int
    esfuerzo: str = Field(description="«muy poco», «poco» o «medio»")
    ingredientes: list[Ingrediente]
    pasos: list[str] = Field(description="Pasos cortos y claros, en orden")
    kcal: float = Field(description="Calorías por ración (aproximadas)")
    proteinas: float = Field(description="Gramos de proteína por ración")
    hidratos: float = Field(description="Gramos de hidratos por ración")
    grasas: float = Field(description="Gramos de grasa por ración")
    truco: str = Field(description="Un consejo para ahorrar energía al cocinarla (preparar de más, congelar, etc.)")


class Sugerencias(BaseModel):
    recetas: list[Receta]


SISTEMA = """Eres el asistente de cocina de una app de organización pensada para personas que \
muchos días tienen poca energía (por cansancio, dolor, una enfermedad o mucho lío). \
Propones recetas caseras:
- Fáciles y de poco esfuerzo: pocos pasos, pocos cacharros, nada de estar mucho rato de pie.
- Con ingredientes que se encuentran en un supermercado normal de España.
- Equilibradas, con raciones realistas y macros por ración aproximados pero sensatos.
- Si te piden ajustarte a unas calorías y macros, que cada ración encaje en lo que queda.
No des consejos médicos ni prometas efectos sobre la salud. Escribe en español de España, \
con un tono cálido y sencillo."""


class ErrorRecetas(Exception):
    """Algo ha fallado al pedir las recetas; el mensaje es para mostrarlo."""


def disponible():
    return bool(current_app.config.get("ANTHROPIC_API_KEY"))


def _cliente():
    return anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"], timeout=90.0)


def pedir_recetas(peticion, restante=None):
    """Devuelve una lista de Receta. `restante`: lo que le queda hoy
    ({"kcal": …, "proteinas": …, …}) o None para no ajustarse."""
    texto = f"Lo que me apetece o tengo en casa: {peticion}\n\nPropón 3 recetas distintas."
    if restante:
        texto += (
            "\n\nAjusta cada ración a lo que me queda hoy: "
            f"{max(restante['kcal'], 0):.0f} kcal, {max(restante['proteinas'], 0):.0f} g de proteínas, "
            f"{max(restante['hidratos'], 0):.0f} g de hidratos y {max(restante['grasas'], 0):.0f} g de grasas "
            "(puede ser una parte de eso si es para una sola comida)."
        )

    try:
        respuesta = _cliente().beta.messages.parse(
            model=MODELO,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",              # si el modelo rechaza la petición, prueba con otro
            output_config={"effort": "medium"},
            system=SISTEMA,
            messages=[{"role": "user", "content": texto}],
            output_format=Sugerencias,
        )
    except anthropic.AuthenticationError as error:
        log.error("Clave de la API de Claude no válida: %s", error)
        raise ErrorRecetas("La clave de la IA no es válida. Revisa ANTHROPIC_API_KEY en el .env.") from error
    except anthropic.RateLimitError as error:
        raise ErrorRecetas("La IA está muy solicitada ahora mismo. Prueba en un minuto.") from error
    except anthropic.APIStatusError as error:
        log.error("Error de la API de Claude (%s): %s", error.status_code, error)
        raise ErrorRecetas("La IA no ha podido responder. Inténtalo de nuevo en un rato.") from error
    except anthropic.APIConnectionError as error:
        raise ErrorRecetas("No hay conexión con la IA. Revisa internet e inténtalo otra vez.") from error

    if respuesta.stop_reason == "refusal":
        raise ErrorRecetas("La IA no ha querido responder a eso. Prueba a pedirlo de otra forma.")
    if respuesta.parsed_output is None or not respuesta.parsed_output.recetas:
        raise ErrorRecetas("La respuesta de la IA ha llegado incompleta. Inténtalo otra vez.")
    return respuesta.parsed_output.recetas[:3]


# ══════════════════════════════════════════════════════════════
#  Calcular las calorías y macros de lo que se ha comido
#  (con lo escrito, o con una foto del plato, del envase o de la
#  etiqueta de información nutricional)
# ══════════════════════════════════════════════════════════════


LADO_MAXIMO_FOTO = 1568          # más grande no mejora la lectura y cuesta más


class EstimacionComida(BaseModel):
    nombre: str = Field(description="Nombre corto y claro de lo comido, p. ej. «Yogur griego natural»")
    gramos_totales: Optional[float] = Field(description="Gramos totales comidos (estimados si no se dicen)")
    kcal: float = Field(description="Calorías TOTALES de todo lo comido")
    proteinas: float = Field(description="Gramos de proteína TOTALES")
    hidratos: float = Field(description="Gramos de hidratos TOTALES")
    grasas: float = Field(description="Gramos de grasa TOTALES")
    codigo_barras: Optional[str] = Field(description="Los números del código de barras si se ven en la foto; si no, null")
    fuente: Literal["etiqueta", "estimacion"] = Field(
        description="«etiqueta» si has leído la tabla nutricional de la foto; si no, «estimacion»")
    confianza: Literal["alta", "media", "baja"]
    nota: str = Field(description="Una frase corta para la persona, p. ej. «Calculado para una ración de 200 g»")


SISTEMA_COMIDAS = """Calculas las calorías y los macronutrientes de lo que alguien ha comido, \
para una app de seguimiento de comidas en España.
- Devuelve siempre los valores TOTALES de todo lo comido (cantidad × ración), no por 100 g.
- Si hay una foto con la tabla de información nutricional, úsala: valores por 100 g × gramos comidos.
- Si no se dicen los gramos, usa una ración normal en España para ese alimento o el tamaño del envase.
- Si la descripción es vaga, haz la estimación más razonable y dilo en la nota.
- Si se ve un código de barras, copia sus números.
No des consejos de salud."""


def preparar_foto(archivo):
    """Comprueba que es una imagen, la gira según el móvil y la reduce.
    Devuelve (bytes JPEG, "image/jpeg") o None."""
    try:
        with Image.open(archivo) as imagen:
            imagen.verify()
        archivo.seek(0)
        with Image.open(archivo) as imagen:
            if imagen.width * imagen.height > 60_000_000:
                return None
            imagen = ImageOps.exif_transpose(imagen).convert("RGB")
            imagen.thumbnail((LADO_MAXIMO_FOTO, LADO_MAXIMO_FOTO))
            salida = BytesIO()
            imagen.save(salida, "JPEG", quality=85)      # sin datos EXIF (ni GPS)
            return salida.getvalue(), "image/jpeg"
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


def _open_food_facts(codigo):
    """Valores por 100 g de un producto (base de datos libre). Solo se envía el código."""
    if not codigo or not codigo.isdigit() or not 8 <= len(codigo) <= 14:
        return None
    try:
        respuesta = requests.get(
            f"https://world.openfoodfacts.org/api/v2/product/{codigo}.json",
            params={"fields": "product_name_es,product_name,nutriments"},
            headers={"User-Agent": "NieblaMental/1.0 (app de organizacion personal)"},
            timeout=6,
        )
        if respuesta.status_code != 200:
            return None
        producto = respuesta.json().get("product") or {}
        n = producto.get("nutriments") or {}
        if n.get("energy-kcal_100g") is None:
            return None
        return {
            "nombre": producto.get("product_name_es") or producto.get("product_name"),
            "kcal": float(n.get("energy-kcal_100g") or 0),
            "proteinas": float(n.get("proteins_100g") or 0),
            "hidratos": float(n.get("carbohydrates_100g") or 0),
            "grasas": float(n.get("fat_100g") or 0),
        }
    except (requests.RequestException, ValueError, TypeError):
        return None


def estimar_comida(descripcion, cantidad=None, gramos=None, foto=None):
    """Devuelve (EstimacionComida, origen) con los valores TOTALES.
    origen: «etiqueta» (tabla nutricional o código de barras) o «ia»/«foto»."""
    texto = f"Lo que he comido: {descripcion or '(mira la foto)'}"
    if cantidad:
        texto += f"\nCantidad: {cantidad:g} (unidades o raciones)"
    if gramos:
        texto += f"\nGramos en total: {gramos:g} g"

    contenido = []
    if foto:
        datos, tipo = foto
        contenido.append({"type": "image", "source": {
            "type": "base64", "media_type": tipo, "data": base64.standard_b64encode(datos).decode("ascii"),
        }})
    contenido.append({"type": "text", "text": texto})

    try:
        respuesta = _cliente().beta.messages.parse(
            model=MODELO,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},        # es un cálculo sencillo: rápido y barato
            system=SISTEMA_COMIDAS,
            messages=[{"role": "user", "content": contenido}],
            output_format=EstimacionComida,
        )
    except anthropic.AuthenticationError as error:
        log.error("Clave de la API de Claude no válida: %s", error)
        raise ErrorRecetas("La clave de la IA no es válida. Revísala en Railway → Variables.") from error
    except anthropic.RateLimitError as error:
        raise ErrorRecetas("La IA está muy solicitada ahora mismo. Prueba en un minuto.") from error
    except anthropic.APIStatusError as error:
        log.error("Error de la API de Claude (%s): %s", error.status_code, error)
        raise ErrorRecetas("La IA no ha podido calcularlo. Inténtalo de nuevo en un rato.") from error
    except anthropic.APIConnectionError as error:
        raise ErrorRecetas("No hay conexión con la IA. Inténtalo otra vez.") from error

    if respuesta.stop_reason == "refusal" or respuesta.parsed_output is None:
        raise ErrorRecetas("La IA no ha podido calcularlo. Prueba a escribirlo de otra forma.")
    estimacion = respuesta.parsed_output
    origen = "etiqueta" if estimacion.fuente == "etiqueta" else ("foto" if foto else "ia")

    # Si se ve un código de barras, los valores reales del producto mandan
    producto = _open_food_facts(estimacion.codigo_barras)
    total_g = gramos or estimacion.gramos_totales
    if producto and total_g:
        factor = total_g / 100
        estimacion.kcal = producto["kcal"] * factor
        estimacion.proteinas = producto["proteinas"] * factor
        estimacion.hidratos = producto["hidratos"] * factor
        estimacion.grasas = producto["grasas"] * factor
        estimacion.gramos_totales = total_g
        if producto["nombre"] and not descripcion:
            estimacion.nombre = producto["nombre"]
        estimacion.nota = f"Valores del envase (Open Food Facts) para {total_g:g} g."
        origen = "etiqueta"
    return estimacion, origen
