"""Draws the app icons from the logo in index.html (<symbol id="mark">, 120x120 units) into biblia/app/icons/.

  icon-192.png, icon-512.png   rounded tile on transparent background ("any" purpose)
  maskable-512.png             full-bleed tile, logo inside the 80% safe zone (Android crops it to its own shape)
  apple-touch-icon.png         180x180, opaque square (iOS rounds the corners itself)

Rendered at 4x and downscaled for smooth edges. Usage: python iconos.py
"""
import os
from PIL import Image, ImageDraw

ACCENT, GLOW, PAGE = "#2E5B4E", "#C9A44C", "#F6F7F3"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "biblia", "app", "icons")


def bezier(p0, p1, p2, p3, n=24):
    return [tuple((1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t**2*c + t**3*d for a, b, c, d in zip(p0, p1, p2, p3))
            for t in (i / n for i in range(n + 1))]


# Logo shapes in the symbol's 120-unit space (same paths as index.html).
PAGINA_IZQ = bezier((58, 46), (46, 39), (32, 38), (22, 41)) + [(22, 90)] + bezier((22, 90), (32, 87), (46, 88), (58, 95))
PAGINA_DER = bezier((62, 46), (74, 39), (88, 38), (98, 41)) + [(98, 90)] + bezier((98, 90), (88, 87), (74, 88), (62, 95))
RAYO = [(60, 14), (67, 28), (53, 28)]
FLECHA = [(60, 34), (68, 42), (63, 42), (63, 48), (57, 48), (57, 42), (52, 42)]


def dibujar(size, fondo_redondeado, escala_logo, transparente):
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0) if transparente else ACCENT)
    d = ImageDraw.Draw(img)
    if fondo_redondeado:
        d.rounded_rectangle([0, 0, S - 1, S - 1], radius=S * 30 / 120, fill=ACCENT)
    k = S / 120 * escala_logo
    off = (S - 120 * k) / 2
    pt = lambda pts: [(off + x * k, off + y * k) for x, y in pts]
    for forma, color in [(PAGINA_IZQ, PAGE), (PAGINA_DER, PAGE), (RAYO, GLOW), (FLECHA, GLOW)]:
        d.polygon(pt(forma), fill=color)
    return img.resize((size, size), Image.LANCZOS)


os.makedirs(OUT, exist_ok=True)
dibujar(192, True, 1, True).save(os.path.join(OUT, "icon-192.png"))
dibujar(512, True, 1, True).save(os.path.join(OUT, "icon-512.png"))
dibujar(512, False, 0.8, False).save(os.path.join(OUT, "maskable-512.png"))
dibujar(180, False, 0.86, False).convert("RGB").save(os.path.join(OUT, "apple-touch-icon.png"))
print("Íconos en", OUT, sorted(os.listdir(OUT)))
