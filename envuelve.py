"""Envuelve la captura publica en un documento completo para GitHub Pages.

Uso: python3 envuelve.py fragmento.html mas-imagen/index.html [titulo]
"""
import re, sys, pathlib

frag = pathlib.Path(sys.argv[1]).read_text()
dest = pathlib.Path(sys.argv[2])
titulo = sys.argv[3] if len(sys.argv) > 3 else "Rols Carpets · borrador de la home (más imagen)"

# Los canonical y hreflang apuntan a localhost, asi que fuera.
frag = re.sub(r'<link rel="canonical"[^>]*>', "", frag)
frag = re.sub(r'<link rel="alternate"[^>]*>', "", frag)
frag = re.sub(r"<title>.*?</title>", "", frag, count=1)

doc = (
    '<!doctype html><html lang="es"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<meta name="robots" content="noindex, nofollow">'
    "<title>" + titulo + "</title>"
    # El tope de ancho de img/video va en la capa base: suelto ganaba a todas
    # las utilidades de Tailwind -que van en capas- y anulaba el max-w-none
    # de la alfombra de los proyectos en el movil, que se quedaba pequena.
    "<style>:root{color-scheme:light}body{margin:0}@layer base{img,video{max-width:100%}}</style>"
    "</head><body>" + frag + "</body></html>"
)
dest.write_text(doc)
print(dest, len(doc) // 1024, "KB")
