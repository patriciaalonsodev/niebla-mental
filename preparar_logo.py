"""Prepara los iconos de la app a partir de static/img/logo.png.

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


def con_fondo(logo, lado, margen=0.12):
    lienzo = Image.new("RGBA", (lado, lado), FONDO)
    hueco = int(lado * (1 - 2 * margen))
    copia = logo.copy()
    copia.thumbnail((hueco, hueco), Image.Resampling.LANCZOS)
    lienzo.alpha_composite(copia, ((lado - copia.width) // 2, (lado - copia.height) // 2))
    return lienzo.convert("RGB")


def main():
    origen = CARPETA / "logo.png"
    logo = Image.open(origen).convert("RGBA")
    # Si el fondo es blanco, quitarlo para que quede bien sobre el morado
    pixeles = logo.get_flattened_data() if hasattr(logo, "get_flattened_data") else logo.getdata()
    logo.putdata([(r, g, b, 0) if r > 245 and g > 245 and b > 245 else (r, g, b, a) for r, g, b, a in pixeles])
    logo = recortar_transparente(logo)

    pequeno = logo.copy()
    pequeno.thumbnail((128, 128), Image.Resampling.LANCZOS)   # 64 px a doble densidad
    pequeno.save(CARPETA / "logo-64.png")
    for lado in (180, 192, 512):
        con_fondo(logo, lado).save(CARPETA / f"icono-{lado}.png")
    print("Iconos creados en", CARPETA)


if __name__ == "__main__":
    main()
