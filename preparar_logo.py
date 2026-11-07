"""Prepara el logo y los iconos de la app.

Uso:  .venv/Scripts/python preparar_logo.py
Crea: logo-64.png (cabecera), icono-180.png (iPhone), icono-192.png e
icono-512.png (Android / PWA), con fondo morado y el logo centrado.
"""
from pathlib import Path

from PIL import Image

CARPETA = Path(__file__).parent / "static" / "img"
FONDO = (34, 26, 58, 255)          # el morado oscuro de la app (#221a3a)


def recortar_transparente(imagen):
    caja = imagen.getbbox()
    return imagen.crop(caja) if caja else imagen


# Degradado del icono (el iPhone no admite iconos transparentes en la pantalla
# de inicio: si lo es, rellena de negro). Lila muy claro arriba → lavanda abajo.
DEGRADADO = ((246, 240, 255), (201, 182, 247), (167, 139, 250))


def degradado(lado):
    """Degradado diagonal suave de tres colores."""
    lienzo = Image.new("RGBA", (lado, lado))
    pixeles = lienzo.load()
    a, b, c = DEGRADADO
    for y in range(lado):
        for x in range(lado):
            t = (x + y) / (2 * (lado - 1))
            if t < 0.5:
                u, desde, hasta = t * 2, a, b
            else:
                u, desde, hasta = (t - 0.5) * 2, b, c
            pixeles[x, y] = tuple(round(desde[i] + (hasta[i] - desde[i]) * u) for i in range(3)) + (255,)
    return lienzo


def con_fondo(logo, lado, margen=0.05):
    lienzo = degradado(lado)
    hueco = int(lado * (1 - 2 * margen))
    copia = logo.copy()
    copia.thumbnail((hueco, hueco), Image.Resampling.LANCZOS)
    lienzo.alpha_composite(copia, ((lado - copia.width) // 2, (lado - copia.height) // 2))
    return lienzo.convert("RGB")


# Iconos de las secciones: archivo original en static/img → nombre en la app
ICONOS = {
    "agenda": "agenda", "compra": "compra", "diario": "diario", "notas": "notas",
    "nutricon": "nutricion", "nutricion": "nutricion", "perfil": "perfil",
    "salud": "salud", "tareas": "tareas", "inicio": "inicio",
    # Pestañas de Salud y de Nutrición
    "sintomas": "sintomas", "medicacion": "medicacion", "actividad": "actividad",
    "sueno": "sueno", "conectar": "conectar",
    "hoy": "hoy", "plan": "plan", "alimentos": "alimentos", "peso": "peso", "recetas": "recetas",
}
LADO_ICONO = 144          # se ven a 48–72 px: así quedan nítidos en pantallas retina


def preparar_iconos():
    """Recorta, centra en un cuadrado y reduce cada icono (PNG transparente)."""
    destino = CARPETA / "iconos"
    destino.mkdir(exist_ok=True)
    for original, nombre in ICONOS.items():
        ruta = CARPETA / f"{original}.png"
        if not ruta.exists():
            continue
        icono = recortar_transparente(Image.open(ruta).convert("RGBA"))
        lado = max(icono.size)
        cuadrado = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
        cuadrado.alpha_composite(icono, ((lado - icono.width) // 2, (lado - icono.height) // 2))
        cuadrado.resize((LADO_ICONO, LADO_ICONO), Image.Resampling.LANCZOS).save(
            destino / f"{nombre}.png", optimize=True)
        print("  icono:", nombre)


def main():
    origen = CARPETA / "logo.png"
    logo = Image.open(origen).convert("RGBA")
    # Si el fondo es blanco (sin transparencia), quitarlo para que quede bien
    # sobre el morado. Si ya es transparente, no se toca: así los brillos
    # blancos del propio logo se conservan.
    if logo.getchannel("A").getextrema()[0] == 255:
        pixeles = logo.get_flattened_data() if hasattr(logo, "get_flattened_data") else logo.getdata()
        logo.putdata([(r, g, b, 0) if r > 245 and g > 245 and b > 245 else (r, g, b, a) for r, g, b, a in pixeles])
    logo = recortar_transparente(logo)

    pequeno = logo.copy()
    pequeno.thumbnail((128, 128), Image.Resampling.LANCZOS)   # 64 px a doble densidad
    pequeno.save(CARPETA / "logo-64.png")
    for lado in (180, 192, 512):
        con_fondo(logo, lado).save(CARPETA / f"icono-{lado}.png")
    print("Logo e iconos de la app creados en", CARPETA)
    preparar_iconos()


if __name__ == "__main__":
    main()
