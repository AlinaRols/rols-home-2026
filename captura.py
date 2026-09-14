"""Volca la home de localhost:3000 a un HTML autonomo listo para publicar.

Vive aqui, en el repo del enlace publico, y no en la carpeta temporal de la
sesion: esa se vacia sola y ya hubo que reescribir el script tres veces.

Uso:
    python3 captura.py salida.html artefacto   # para el visor de Claude
    python3 captura.py salida.html publico     # para GitHub Pages

Sale como fragmento (sin html/head/body): el envoltorio de publicacion del
artefacto aporta el resto. Para Pages hay que envolverlo (ver envuelve.py).
"""
import base64, html as ihtml, mimetypes, re, sys, urllib.request, urllib.parse, pathlib

BASE = "http://localhost:3000"
DEST = pathlib.Path(sys.argv[1])
# "publico" = pagina de GitHub Pages, con el mp4 al lado: Safari lo reproduce.
# "artefacto" = HTML suelto en el visor de Claude, que bloquea media de fuera
# y donde Safari tampoco sabe reproducir un data: URI, asi que ahi cada bloque
# de video se queda con su fotograma.
DESTINO = sys.argv[2] if len(sys.argv) > 2 else "publico"


def get(u):
    return urllib.request.urlopen(BASE + u if u.startswith("/") else u, timeout=180).read()


page = get("/").decode()

# El CSS se mete dentro, con sus fuentes y sus imagenes como data URI.
css = []
for href in re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', page):
    hoja = ihtml.unescape(href)
    t = get(hoja).decode("utf-8", "replace")

    # Las url() del CSS se resuelven contra la hoja, no contra la pagina: las
    # de Next vienen como "../media/xxx.woff2" y sin esto se quedaban sin
    # embeber -y la pagina publicada perdia Montserrat y League Spartan-.
    def inline(m, hoja=hoja):
        raw = m.group(1).strip("'\"")
        if raw.startswith(("data:", "http")):
            return m.group(0)
        absoluta = urllib.parse.urljoin(BASE + hoja if hoja.startswith("/") else hoja, raw)
        try:
            blob = get(absoluta)
        except Exception:
            return m.group(0)
        mime = "font/woff2" if raw.endswith(".woff2") else (mimetypes.guess_type(raw)[0] or "application/octet-stream")
        return f'url("data:{mime};base64,{base64.b64encode(blob).decode()}")'

    css.append(re.sub(r'url\(([^)]+)\)', inline, t))
page = re.sub(r'<link[^>]+rel="stylesheet"[^>]*>', "", page)

# Cada <img> se queda con una sola fuente, embebida.
cache = {}


def pick(ss):
    best, bw = None, -1
    for part in ihtml.unescape(ss).split(","):
        bits = part.strip().split(" ")
        if len(bits) < 2:
            continue
        try:
            w = int(bits[-1].rstrip("w"))
        except ValueError:
            continue
        if bw < w <= 1600:
            best, bw = bits[0], w
    return best


def mete(url, mime=None):
    if url in cache:
        return cache[url]
    blob = get(url)
    if mime is None:
        mime = "image/webp" if b"WEBP" in blob[:20] else "image/jpeg"
    cache[url] = f"data:{mime};base64,{base64.b64encode(blob).decode()}"
    return cache[url]


def fix(m):
    tag = m.group(0)
    ss = re.search(r'srcSet="([^"]+)"', tag) or re.search(r'srcset="([^"]+)"', tag)
    sr = re.search(r'\ssrc="([^"]+)"', tag)
    url = pick(ss.group(1)) if ss else (ihtml.unescape(sr.group(1)) if sr else None)
    if not url:
        return tag
    dato = mete(url)
    tag = re.sub(r'\s(?:srcSet|srcset)="[^"]*"', "", tag)
    tag = re.sub(r'\ssrc="[^"]*"', "", tag)
    tag = re.sub(r'\sloading="lazy"', "", tag)
    return tag[:-1].rstrip("/") + ' src="%s">' % dato


page = re.sub(r'<img[^>]*>', fix, page)


def video(m):
    """Deja el <video> apuntando al mp4 que va junto al HTML en Pages."""
    tag = m.group(0)
    cartel = re.search(r'poster="([^"]+)"', tag)
    if cartel and not cartel.group(1).startswith("data:"):
        tag = tag.replace(cartel.group(1), mete(ihtml.unescape(cartel.group(1)), "image/webp"))
    # El video NO se embebe como data: URI. Safari no puede reproducir video en
    # data: -necesita peticiones por rango, que un data: no admite-, asi que se
    # apunta al fichero suelto que va junto al HTML.
    src = re.search(r'<video[^>]*\ssrc="([^"]+)"', tag)
    if src and not src.group(1).startswith("data:"):
        tag = tag.replace(src.group(1), "hero-fabrica-movil.mp4", 1)
    return tag


def a_cartel(m):
    """Cambia un <video> por su fotograma, conservando las clases."""
    tag = m.group(0)
    clases = re.search(r'className="([^"]*)"', tag) or re.search(r'class="([^"]*)"', tag)
    cartel = re.search(r'poster="([^"]+)"', tag)
    if not cartel:
        return ""
    src = cartel.group(1)
    if not src.startswith("data:"):
        src = mete(ihtml.unescape(src), "image/webp")
    cl = (clases.group(1) if clases else "").replace("opacity-0", "").replace("motion-reduce:hidden", "")
    return f'<img alt="" src="{src}" class="{cl.strip()}">'


# Cada bloque con video trae DOS <video>: son las dos copias desfasadas del
# bucle cruzado. Y la home lleva dos bloques asi -el hero y la fabrica-, o sea
# cuatro etiquetas: hay que tratarlas todas, no solo la primera.
if DESTINO == "artefacto":
    page = re.sub(r'<video[^>]*opacity-0[\s\S]*?</video>', '', page)
    page = re.sub(r'<video[\s\S]*?</video>', a_cartel, page)
    page = page.replace("hidden size-full object-cover", "size-full object-cover")
    page = page.replace(
        "absolute inset-x-0 bottom-0 hidden h-[120%]",
        "absolute inset-x-0 bottom-0 h-[120%]")
else:
    page = re.sub(r'<video[^>]*opacity-0[\s\S]*?</video>', '', page)
    page = re.sub(r'<video[\s\S]*?</video>', video, page)

page = re.sub(r'<script[\s\S]*?</script>', "", page)
page = re.sub(r'<link[^>]+rel="preload"[^>]*>', "", page)

# Sin el runtime de Next hay que reconectar a mano lo que se mueve.
reconecta = """
<script>
// No se cuelga de DOMContentLoaded a secas: el visor del artefacto inyecta el
// HTML por trozos y ese evento puede haber pasado ya cuando llega este script,
// y entonces no se ejecutaba nunca -era lo que dejaba el cajon muerto en el
// artefacto mientras en Pages funcionaba-.
(function (arranca) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', arranca);
  } else {
    arranca();
  }
})(function () {
  // Flechas de las tiras.
  var tiras = Array.prototype.filter.call(document.querySelectorAll('main ul'), function (u) {
    return getComputedStyle(u).overflowX === 'auto';
  });
  var botones = Array.prototype.slice.call(document.querySelectorAll('main button[aria-label]'));
  tiras.forEach(function (tira, i) {
    var par = botones.slice(i * 2, i * 2 + 2);
    if (par.length < 2) return;
    function mueve(dir) {
      var desde = tira.scrollLeft;
      var hasta = Math.max(0, Math.min(desde + dir * tira.clientWidth * 0.8, tira.scrollWidth - tira.clientWidth));
      var t0 = performance.now();
      function paso(now) {
        var t = Math.min(1, (now - t0) / 420);
        tira.scrollLeft = desde + (hasta - desde) * (1 - Math.pow(1 - t, 3));
        if (t < 1) requestAnimationFrame(paso);
      }
      requestAnimationFrame(paso);
    }
    par[0].addEventListener('click', function () { mueve(-1); });
    par[1].addEventListener('click', function () { mueve(1); });
  });

  // Cajon lateral: abre, cierra y despliega niveles.
  var abierto = false;
  var boton = Array.prototype.filter.call(
    document.querySelectorAll('header button[aria-controls]'),
    function (b) { return /men/i.test(b.getAttribute('aria-label') || ''); })[0];
  var cajon = boton && document.getElementById(boton.getAttribute('aria-controls'));
  if (boton && cajon) {
    var velo = cajon.previousElementSibling;
    var reloj = null;

    // El fondo y el filete van por estilo en linea y no fiados a la clase.
    // En Safari el panel se abria transparente -se veia el video detras- y
    // con esto se pinta si o si. El color se lee de la variable del sitio,
    // con blanco de respaldo.
    // Capa propia tambien en reposo, y aislada del resto de la pagina.
    cajon.style.isolation = 'isolate';
    var raiz = getComputedStyle(document.documentElement);
    var fondo = (raiz.getPropertyValue('--background') || '').trim() || '#ffffff';
    var linea = (raiz.getPropertyValue('--line') || '').trim() || 'rgba(0,0,0,.12)';
    cajon.style.backgroundColor = fondo;
    cajon.style.borderRight = '1px solid ' + linea;
    if (velo) velo.style.backgroundColor = 'rgba(0,0,0,.18)';

    // Esconder con translate a secas es fragil: si el navegador no aplica esa
    // propiedad, el panel se queda a la vista encima de la pagina. Asi que
    // manda visibility, que la entiende cualquiera, y translate solo anima.
    var pinta = function (abre) {
      cajon.setAttribute('aria-hidden', abre ? 'false' : 'true');
      if (reloj) { clearTimeout(reloj); reloj = null; }
      if (abre) {
        cajon.style.visibility = 'visible';
        cajon.style.translate = '0';
        // translateZ(0) y no 'none': obliga a Safari a darle capa propia al
        // panel. Sin capa, un <video> acelerado se pinta por encima y el
        // cajon aparecia sin su fondo, con la pagina viendose detras.
        cajon.style.transform = 'translateZ(0)';
      } else {
        cajon.style.translate = '-100%';
        cajon.style.transform = '';
        reloj = setTimeout(function () {
          if (!abierto) cajon.style.visibility = 'hidden';
        }, 340);
      }
      cajon.style.pointerEvents = abre ? 'auto' : 'none';
      if (velo) {
        velo.style.opacity = abre ? '1' : '0';
        velo.style.visibility = abre ? 'visible' : 'hidden';
        velo.style.pointerEvents = abre ? 'auto' : 'none';
      }
      boton.setAttribute('aria-expanded', abre ? 'true' : 'false');
      var cabecera = document.querySelector('header');
      if (cabecera) {
        cabecera.style.backgroundColor = abre ? fondo : '';
        cabecera.style.color = abre ? 'var(--foreground)' : '';
      }
    };
    pinta(false);
    cajon.style.visibility = 'hidden';
    boton.addEventListener('click', function () { abierto = !abierto; pinta(abierto); });
    if (velo) velo.addEventListener('click', function () { abierto = false; pinta(false); });
    Array.prototype.forEach.call(cajon.querySelectorAll('button[aria-expanded]'), function (b) {
      b.addEventListener('click', function () {
        var lista = b.nextElementSibling;
        if (!lista) return;
        var abre = lista.classList.contains('hidden');
        lista.classList.toggle('hidden', !abre);
        b.setAttribute('aria-expanded', abre ? 'true' : 'false');
        var galon = b.querySelector('svg');
        if (galon) galon.style.rotate = abre ? '180deg' : '0deg';
      });
    });
  }

  // La barra se esconde al bajar y vuelve al subir, como en la web viva. No se
  // esconde con el cajon abierto: el cajon vive dentro del <header> y se iria
  // con el.
  var cabecera = document.querySelector('header');
  if (cabecera) {
    var retirada = false;
    var ultimoY = window.scrollY;
    var mira = function () {
      var y = window.scrollY;
      var avance = y - ultimoY;
      ultimoY = y;
      var fuera;
      if (y <= 120 || abierto) {
        fuera = false;
      } else if (Math.abs(avance) < 6) {
        return;
      } else {
        fuera = avance > 0;
      }
      if (fuera === retirada) return;
      retirada = fuera;
      cabecera.style.transition = 'translate .3s ease-out, height .2s ease-out, background-color .2s ease-out';
      cabecera.style.translate = fuera ? '0 -100%' : '0 0';
      cabecera.style.pointerEvents = fuera ? 'none' : '';
    };
    window.addEventListener('scroll', mira, { passive: true });
    window.addEventListener('resize', mira);
    mira();
  }
});
</script>
"""

# Sale como fragmento: fuera el envoltorio de documento. El (?=[\s>]) es
# imprescindible: sin el, "head" tambien casaba con <header> y la captura se
# quedaba sin cabecera -y sin cajon-.
page = re.sub(r'<!DOCTYPE[^>]*>', "", page, flags=re.I)
page = re.sub(r'</?(?:html|head|body)(?=[\s>])[^>]*>', "", page, flags=re.I)
page = "<style>%s</style>%s%s" % ("\n".join(css), page.strip(), reconecta)
DEST.write_text(page)
print("imagenes:", len(cache), "| tamano:", len(page) // 1024, "KB")
