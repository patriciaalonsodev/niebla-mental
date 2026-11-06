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

import logging

import anthropic
from flask import current_app
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


SISTEMA = """Eres el asistente de cocina de una app de organización pensada para personas con \
fibromialgia, fatiga crónica o niebla mental. Propones recetas caseras:
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
