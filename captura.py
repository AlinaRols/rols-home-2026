"""Volca la home de localhost:3000 a un HTML autonomo listo para publicar.

Vive aqui, en el repo del enlace publico, y no en la carpeta temporal de la
sesion: esa se vacia sola y ya hubo que reescribir el script tres veces.

Uso:
    python3 captura.py salida.html artefacto   # para el visor de Claude
    python3 captura.py salida.html publico     # para GitHub Pages
    python3 captura.py salida.html publico /colecciones

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
RUTA = sys.argv[3] if len(sys.argv) > 3 else "/"


# El Accept importa: el optimizador de Next negocia el formato, y sin esta
# cabecera devuelve JPEG. El JPEG no tiene transparencia, asi que los logos
# de los estudios -PNG con alfa- salian con el fondo en NEGRO en la pagina
# publicada mientras en localhost se veian bien. Pidiendo webp conserva el
# canal alfa. No se pide avif a proposito: asi se sabe que lo que llega es
# webp o el original.
CABECERAS = {"Accept": "image/webp,image/png,image/jpeg,*/*"}


def get(u):
    url = BASE + u if u.startswith("/") else u
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=CABECERAS), timeout=180
    ).read()


page = get(RUTA).decode()

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

# Las fuentes: next/font no las declara en :root, sino en una clase con hash
# que va puesta en el <html> -"montserrat_xxx__variable league_spartan_yyy".
# Y esta captura sale como fragmento, sin <html> ni <body>, asi que esa clase
# se pierde: las variables --font-* quedan sin definir, font-family no resuelve
# y TODA la pagina publicada salia en la tipografia del sistema mientras en
# localhost se veia con League Spartan y Montserrat.
#
# Los woff2 si estaban embebidos desde hace dias; lo que faltaba era quien los
# llamara. Se rescatan los valores del propio CSS y se vuelven a declarar en
# :root, que no depende de ninguna clase.
hoja = "\n".join(css)
declaraciones = []
for var in ("--font-montserrat", "--font-league-spartan"):
    m = re.search(re.escape(var) + r"\s*:\s*([^;}]+)", hoja)
    if m:
        declaraciones.append("%s:%s" % (var, m.group(1).strip()))
    else:
        print("AVISO: no se encuentra", var, "en el CSS; la pagina saldra con la fuente del sistema")
if declaraciones:
    # El body tambien: en la pagina real lleva la clase font-sans, y el body
    # del envoltorio no la tiene, asi que todo lo que hereda se quedaba fuera.
    css.append(":root{%s}\nbody{font-family:var(--font-sans)}" % ";".join(declaraciones))


# Cada <img> se queda con una sola fuente, embebida.
cache = {}


def pick(ss, tope=1600):
    """Elige una fuente del srcset.

    Hay dos clases de srcset y hay que entender las dos. Cuando la imagen
    lleva sizes, Next escribe anchos -"...640w, ...1200w"- y nos quedamos con
    el mayor que no pase del tope. Cuando NO lleva sizes, escribe densidades
    -"...640 1x, ...1200 2x"- y entonces nos quedamos con la mas densa.

    Solo entendia los anchos, y las imagenes sin sizes -los logos de los
    estudios- se quedaban sin candidato: fix() devolvia la etiqueta intacta,
    apuntando a /_next/image, que en una pagina estatica no existe. Alina los
    vio como iconos de imagen rota.
    """
    anchos, densidades = [], []
    for part in ihtml.unescape(ss).split(","):
        bits = part.strip().split(" ")
        if len(bits) < 2:
            continue
        marca = bits[-1]
        if marca.endswith("w"):
            try:
                anchos.append((int(marca[:-1]), bits[0]))
            except ValueError:
                continue
        elif marca.endswith("x"):
            try:
                densidades.append((float(marca[:-1]), bits[0]))
            except ValueError:
                continue
    cabidos = [u for w, u in sorted(anchos) if w <= tope]
    if cabidos:
        return cabidos[-1]
    if densidades:
        return sorted(densidades)[-1][1]
    return None


def tipo(blob):
    """El tipo real, leido de los primeros bytes y no adivinado."""
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp"
    if blob[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if blob[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    # Los SVG son texto: empiezan por "<svg" o por la declaracion XML. Sin este
    # caso salian como application/octet-stream y el navegador no los pintaba
    # -era lo que dejaba en blanco los iconos de pago del pie-.
    cabeza = blob[:200].lstrip()
    if cabeza[:4] == b"<svg" or (cabeza[:5] == b"<?xml" and b"<svg" in blob[:600]):
        return "image/svg+xml"
    return "application/octet-stream"


def mete(url, mime=None):
    if url in cache:
        return cache[url]
    blob = get(url)
    if mime is None:
        mime = tipo(blob)
    cache[url] = f"data:{mime};base64,{base64.b64encode(blob).decode()}"
    return cache[url]


def fix(m):
    tag = m.group(0)
    ss = re.search(r'srcSet="([^"]+)"', tag) or re.search(r'srcset="([^"]+)"', tag)
    sr = re.search(r'\ssrc="([^"]+)"', tag)
    # Las fotos a sangre -sizes="100vw", que hoy solo es el hero- se llevan el
    # tope alto. Con el de 1600 el hero caia en el escalon de 1200 de Next -no
    # hay nada entre 1200 y 1920- y en una ventana de 1920 con retina se
    # estiraba de 1200 a 3840: por eso Alina lo veia "muy mal". No se sube el
    # tope de todas porque son 18 imagenes y la pagina ya pesa 5,6 MB. Al
    # hero le cuesta 260 KB mas y a cambio se ve nitido en una retina de
    # 1920, que es donde lo mira Alina.
    tope = 3840 if 'sizes="100vw"' in tag else 1600
    # Las fichas del archivo de colecciones van a un cuarto de pantalla -433 px
    # en la de 1920-, asi que les basta 828, el doble para retina.
    ficha = '(min-width: 1024px) 25vw' in tag
    if ficha:
        tope = 828
    url = pick(ss.group(1), tope) if ss else (ihtml.unescape(sr.group(1)) if sr else None)
    if not url:
        return tag
    # Y no se embeben: son 76 fotos con las de ambiente y la pagina pesaba
    # 14 MB, que tardaba en pintar nada. En Pages van como ficheros sueltos en
    # img/, junto al index.html de la ruta, y con carga diferida: se bajan
    # segun se llega a ellas.
    if ficha and DESTINO == "publico":
        carpeta = pathlib.Path(RUTA.strip("/") or ".") / "img"
        carpeta.mkdir(parents=True, exist_ok=True)
        nombre = re.sub(r"[^a-z0-9]+", "-", urllib.parse.unquote(url).lower().split("uploads/")[-1].split("&")[0]).strip("-") + ".webp"
        if not (carpeta / nombre).exists():
            (carpeta / nombre).write_bytes(get(url))
        tag = re.sub(r'\s(?:srcSet|srcset)="[^"]*"', "", tag)
        tag = re.sub(r'\ssrc="[^"]*"', "", tag)
        return tag[:-1].rstrip("/") + ' src="img/%s">' % nombre
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
    # Cada video apunta al fichero que va a su lado, deducido del nombre:
    # X-web.mp4 -> X-captura.mp4, y si no existe, X-movil.mp4. Antes estaba
    # escrito a pelo "hero-fabrica-movil.mp4", y en cuanto la home tuvo dos
    # videos distintos el del hero apuntaba al de la fabrica.
    #
    # Se prefiere la copia "captura" porque la de movil ya no vale aqui: desde
    # el 18 sept 2026 la version de telefono del video de fabrica va recortada
    # en vertical -que es lo que se ve en un movil de verdad-, y en el enlace,
    # que se mira en el ordenador, saldria una tira central estirada. La copia
    # "captura" es el mismo plano apaisado a 720p, ligera y con el encuadre
    # bueno.
    src = re.search(r'<video[^>]*\ssrc="([^"]+)"', tag)
    if src and not src.group(1).startswith("data:"):
        nombre = src.group(1).rsplit("/", 1)[-1]
        for sufijo in ("-captura.mp4", "-movil.mp4"):
            candidato = nombre.replace("-web.mp4", sufijo)
            if candidato != nombre and (DEST.parent / candidato).exists():
                nombre = candidato
                break
        tag = tag.replace(src.group(1), nombre, 1)
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

# GitHub Pages publica dentro de /rols-home-2026, no en la raiz del dominio.
# Las rutas internas que salen de Next necesitan ese prefijo en la copia
# estatica: de otro modo el logo y, sobre todo, "Colecciones" llevan a un 404.
if DESTINO == "publico":
    page = page.replace('href="/colecciones"', 'href="/rols-home-2026/colecciones/"')
    page = page.replace('href="/"', 'href="/rols-home-2026/"')

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
  // Solo las flechas: los puntitos del carrusel de proyectos tambien son
  // botones con etiqueta, y si entran aqui descuadran el emparejamiento por
  // orden. Las flechas son las que llevan un svg dentro.
  var botones = Array.prototype.filter.call(
    document.querySelectorAll('main button[aria-label]'),
    function (b) { return !!b.querySelector('svg'); });
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

  // En movil no hay hover: la flecha sutil y un gesto corto sobre la imagen
  // alternan entre el packshot y su foto de ambiente. Un gesto largo o rapido
  // queda libre para desplazar la tira de productos. La captura de Pages no
  // hidrata React, asi que se replica aqui la interaccion de la aplicacion.
  (function () {
    var tarjetas = Array.prototype.slice.call(
      document.querySelectorAll('[data-mobile-image-card]'));

    var pintaTarjeta = function (tarjeta, activa) {
      var boton = tarjeta.querySelector('[data-mobile-image-toggle]');
      var packshot = tarjeta.querySelector('[data-mobile-packshot]');
      var ambiente = tarjeta.querySelector('[data-mobile-ambient]');
      var elegir = tarjeta.querySelector('[data-mobile-choose]');
      var editions = tarjeta.querySelector('[data-mobile-editions]');
      if (!boton || !packshot || !ambiente || !elegir) return;

      packshot.classList.toggle('opacity-0', activa);
      packshot.classList.toggle('opacity-100', !activa);
      ambiente.classList.toggle('opacity-100', activa);
      ambiente.classList.toggle('opacity-0', !activa);
      elegir.classList.toggle('translate-y-0', activa);
      elegir.classList.toggle('opacity-100', activa);
      elegir.classList.toggle('translate-y-1.5', !activa);
      elegir.classList.toggle('opacity-0', !activa);
      if (editions) {
        editions.classList.toggle('opacity-0', activa);
        editions.classList.toggle('opacity-100', !activa);
      }

      boton.setAttribute('aria-pressed', activa ? 'true' : 'false');
      boton.setAttribute('aria-label', activa ? boton.dataset.showProduct : boton.dataset.showAmbient);
      var icono = boton.querySelector('svg');
      if (icono) icono.classList.toggle('rotate-180', activa);
    };

    tarjetas.forEach(function (tarjeta) {
      var boton = tarjeta.querySelector('[data-mobile-image-toggle]');
      var superficie = tarjeta.querySelector('[data-mobile-swipe-surface]');
      if (!boton) return;
      boton.addEventListener('click', function () {
        var activa = boton.getAttribute('aria-pressed') !== 'true';
        tarjetas.forEach(function (otra) {
          pintaTarjeta(otra, activa && otra === tarjeta);
        });
      });

      if (superficie) {
        var gesto = null;
        superficie.addEventListener('touchstart', function (event) {
          var toque = event.touches[0];
          var tira = superficie.closest('ul');
          if (!toque || !tira) return;
          gesto = {
            x: toque.clientX,
            y: toque.clientY,
            at: performance.now(),
            maxDistance: 0,
            scrollLeft: tira.scrollLeft
          };
        }, { passive: true });
        superficie.addEventListener('touchmove', function (event) {
          var toque = event.touches[0];
          if (!gesto || !toque) return;
          gesto.maxDistance = Math.max(gesto.maxDistance, Math.abs(toque.clientX - gesto.x));
        }, { passive: true });
        superficie.addEventListener('touchend', function (event) {
          var inicio = gesto;
          var toque = event.changedTouches[0];
          var tira = superficie.closest('ul');
          gesto = null;
          if (!inicio || !toque || !tira) return;

          var dx = toque.clientX - inicio.x;
          var dy = toque.clientY - inicio.y;
          var distancia = Math.abs(dx);
          var recorrido = Math.max(distancia, inicio.maxDistance);
          var velocidad = distancia / Math.max(performance.now() - inicio.at, 1);
          if (distancia < 18 || recorrido > 72 || velocidad > 0.65 ||
              distancia <= Math.abs(dy) * 1.25) return;

          event.preventDefault();
          event.stopPropagation();
          tira.scrollLeft = inicio.scrollLeft;
          tarjetas.forEach(function (otra) {
            pintaTarjeta(otra, dx < 0 && otra === tarjeta);
          });
        }, { passive: false });
        superficie.addEventListener('touchcancel', function () {
          gesto = null;
        }, { passive: true });
      }
    });
  })();

  // Pequeno vaiven del carrusel de best sellers en movil. Sirve como pista
  // de que la tira continua hacia la derecha: asoma la siguiente ficha y
  // vuelve a su sitio una sola vez cuando el bloque entra en pantalla.
  (function () {
    var tira = document.querySelector('main ul.overflow-x-auto');
    if (!tira || !window.matchMedia('(max-width: 767px)').matches ||
        window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    var frame = 0;
    var reloj = 0;
    var empezado = false;
    var cancela = function () {
      clearTimeout(reloj);
      cancelAnimationFrame(frame);
    };
    tira.addEventListener('pointerdown', cancela, { once: true });

    var arranca = function () {
      if (empezado) return;
      empezado = true;
      reloj = setTimeout(function () {
        if (tira.scrollLeft > 2) return;
        var desde = tira.scrollLeft;
        var distancia = Math.min(26, tira.scrollWidth - tira.clientWidth);
        var inicio = performance.now();
        var duracion = 950;
        var paso = function (ahora) {
          var t = Math.min(1, (ahora - inicio) / duracion);
          var vaiven = Math.pow(Math.sin(Math.PI * t), 2);
          tira.scrollLeft = desde + distancia * vaiven;
          if (t < 1) frame = requestAnimationFrame(paso);
        };
        frame = requestAnimationFrame(paso);
      }, 320);
    };

    if (window.IntersectionObserver) {
      var observador = new IntersectionObserver(function (entradas) {
        if (entradas[0].isIntersecting && entradas[0].intersectionRatio >= 0.45) {
          observador.disconnect();
          arranca();
        }
      }, { threshold: 0.45 });
      observador.observe(tira);
    } else {
      arranca();
    }
  })();

  // Todo esto va en su propia funcion: el guion comparte un solo ambito y
  // mas abajo el cajon declara otro `pinta` y otro `reloj` con var, que
  // pisaban a los de aqui -el reloj del carrusel acababa llamando a la
  // funcion del cajon y no pasaba nada-.
  (function () {
    // Puntitos, gesto tactil y pase automatico del carrusel de proyectos. En
    // la web esto lo lleva React; aqui se reconstruye igual: los proyectos van
    // apilados y solo cambia la opacidad, cada 3 s, parandose con el raton
    // encima, fuera de pantalla o con la pestana de fondo.
    var puntos = Array.prototype.slice.call(
      document.querySelectorAll('main button[aria-label^="Ir al proyecto"]'));
    if (puntos.length) {
      var fila = puntos[0].parentElement;
      var lista = fila.previousElementSibling;
      var diapos = Array.prototype.slice.call(lista.children);
      var bloque = fila.closest('section') || fila.parentElement;
      var beige = getComputedStyle(document.querySelector('header a.bg-beige')).backgroundColor;
      // El activo en tostado oscuro, como en interiors-carousel.tsx: beige
      // sobre beige solo se distinguia por el ancho.
      var tostado = getComputedStyle(document.documentElement).getPropertyValue('--accent-deep').trim() || '#b9906a';
      var cual = 0;

      var pinta = function () {
        diapos.forEach(function (d, j) {
          d.style.opacity = j === cual ? '1' : '0';
          d.style.pointerEvents = j === cual ? '' : 'none';
          d.setAttribute('aria-hidden', j === cual ? 'false' : 'true');
        });
        puntos.forEach(function (p, j) {
          p.style.width = j === cual ? '24px' : '6px';
          p.style.backgroundColor = j === cual ? tostado : beige;
          if (j === cual) p.setAttribute('aria-current', 'true');
          else p.removeAttribute('aria-current');
        });
      };

      var reloj = null;
      var cuenta = function () {
        if (reloj) clearInterval(reloj);
        reloj = setInterval(function () {
          if (quieto || !aLaVista || document.hidden) return;
          cual = (cual + 1) % diapos.length;
          pinta();
        }, 3000);
      };

      puntos.forEach(function (p, j) {
        p.addEventListener('click', function () { cual = j; pinta(); cuenta(); });
      });

      // En movil el carrusel sigue pasando solo, pero tambien responde al
      // dedo. El gesto horizontal cambia un proyecto y `pan-y` deja intacto
      // el desplazamiento vertical de la pagina.
      lista.style.touchAction = 'pan-y';
      var gestoProyecto = null;
      lista.addEventListener('touchstart', function (event) {
        var toque = event.touches[0];
        if (!toque) return;
        gestoProyecto = { x: toque.clientX, y: toque.clientY };
      }, { passive: true });
      lista.addEventListener('touchend', function (event) {
        var inicio = gestoProyecto;
        var toque = event.changedTouches[0];
        gestoProyecto = null;
        if (!inicio || !toque) return;
        var dx = toque.clientX - inicio.x;
        var dy = toque.clientY - inicio.y;
        if (Math.abs(dx) < 36 || Math.abs(dx) <= Math.abs(dy) * 1.2) return;
        event.preventDefault();
        cual = (cual + (dx < 0 ? 1 : -1) + diapos.length) % diapos.length;
        pinta();
        cuenta();
      }, { passive: false });
      lista.addEventListener('touchcancel', function () {
        gestoProyecto = null;
      }, { passive: true });

      var quieto = false;
      var aLaVista = false;
      bloque.addEventListener('pointerenter', function () { quieto = true; });
      bloque.addEventListener('pointerleave', function () { quieto = false; });
      if (window.IntersectionObserver) {
        new IntersectionObserver(function (e) { aLaVista = e[0].isIntersecting; },
          { threshold: 0.5 }).observe(bloque);
      } else {
        aLaVista = true;
      }

      pinta();
      if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) cuenta();
    }
  })();

  // Cajon lateral. No se inventa nada: se ponen y se quitan LAS MISMAS clases
  // que pone y quita React en site-header.tsx, que es la version que funciona.
  // Antes esto se hacia con estilos en linea -visibility, translate, un
  // backgroundColor calculado, un translateZ(0) para Safari- y cada arreglo
  // tapaba el anterior sin tocar la causa.
  var abierto = false;
  var boton = Array.prototype.filter.call(
    document.querySelectorAll('header button[aria-controls]'),
    function (b) { return /men/i.test(b.getAttribute('aria-label') || ''); })[0];
  var cajon = boton && document.getElementById(boton.getAttribute('aria-controls'));
  var cabecera = document.querySelector('header');
  if (boton && cajon) {
    var velo = cajon.previousElementSibling;
    var reloj = null;

    var clases = function (el, quita, pon) {
      if (!el) return;
      quita.forEach(function (c) { el.classList.remove(c); });
      pon.forEach(function (c) { el.classList.add(c); });
    };

    var pinta = function (abre) {
      if (reloj) { clearTimeout(reloj); reloj = null; }
      cajon.setAttribute('aria-hidden', abre ? 'false' : 'true');
      boton.setAttribute('aria-expanded', abre ? 'true' : 'false');
      document.body.style.overflow = abre ? 'hidden' : '';

      if (abre) {
        // Con el cajon abierto la cabecera nunca va desplazada, igual que en
        // el componente: alli "escondida" exige que no haya panel abierto.
        if (cabecera) { cabecera.style.translate = ''; cabecera.style.pointerEvents = ''; }
        clases(cajon, ['pointer-events-none', '-translate-x-full', 'invisible'],
                      ['pointer-events-auto', 'visible', 'translate-x-0']);
        clases(velo, ['pointer-events-none', 'opacity-0', 'invisible'],
                     ['pointer-events-auto', 'visible', 'opacity-100']);
      } else {
        clases(cajon, ['pointer-events-auto', 'translate-x-0'],
                      ['pointer-events-none', '-translate-x-full']);
        clases(velo, ['pointer-events-auto', 'opacity-100'],
                     ['pointer-events-none', 'opacity-0']);
        // El componente devuelve el "invisible" cuando acaba la transicion.
        reloj = setTimeout(function () {
          if (abierto) return;
          clases(cajon, ['visible'], ['invisible']);
          clases(velo, ['visible'], ['invisible']);
        }, 340);
      }
    };

    boton.addEventListener('click', function () { abierto = !abierto; pinta(abierto); });
    if (velo) velo.addEventListener('click', function () { abierto = false; pinta(false); });
    window.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && abierto) { abierto = false; pinta(false); }
    });
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
  //
  // CUIDADO con el translate de reposo: tiene que QUITARSE, no ponerse a cero.
  // El cajon y su velo son position:fixed y viven dentro del <header>; en
  // cuanto el <header> lleva un translate distinto de "none" pasa a ser su
  // bloque contenedor, y entonces el cajon -top:var(--cabecera); bottom:0-
  // se resuelve dentro de una caja de 62 px de alto y se queda en ALTURA CERO.
  // Ese era el fallo que Alina veia como "se abre pero le falta el fondito
  // blanco": bastaba con haber desplazado la pagina una vez. Un translate de
  // '0 0' basta para romperlo, asi que aqui va cadena vacia, que es lo que
  // hace el componente al soltar la clase.
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
      cabecera.style.translate = fuera ? '0 -100%' : '';
      cabecera.style.pointerEvents = fuera ? 'none' : '';
    };
    window.addEventListener('scroll', mira, { passive: true });
    window.addEventListener('resize', mira);
    mira();
  }

  // Filtros del archivo de colecciones. Misma regla que collection-archive-
  // grid.tsx: todo suma -cada casilla es un requisito mas-, cada opcion dice
  // cuantas quedarian y las que vaciarian la pagina se apagan.
  (function () {
    var fichas = Array.prototype.slice.call(document.querySelectorAll('[data-collection]'));
    if (!fichas.length) return;
    var casillas = Array.prototype.slice.call(document.querySelectorAll('input[data-filter-group]'));
    var editions = document.querySelector('[data-filter-editions]');
    var cuentas = Array.prototype.slice.call(document.querySelectorAll('[data-filter-count]'));
    var movil = document.querySelector('[data-filter-mobile]');
    var lista = document.querySelector('[data-filter-list]');
    var vacio = document.querySelector('[data-filter-empty]');
    var borrar = Array.prototype.slice.call(document.querySelectorAll('[data-filter-clear]'));
    var botones = Array.prototype.slice.call(document.querySelectorAll('[data-filter-toggle]'));
    var conEd = false;
    var etiquetas = function (f, g) { return (f.getAttribute('data-' + g) || '').split(' '); };
    var pasa = function (f, marcados, ed) {
      return marcados.every(function (m) { return etiquetas(f, m.g).indexOf(m.v) >= 0; }) &&
        (!ed || f.hasAttribute('data-editions'));
    };
    var marcados = function () {
      return casillas.filter(function (c) { return c.checked; })
        .map(function (c) { return { g: c.getAttribute('data-filter-group'), v: c.value }; });
    };
    var pinta = function () {
      var m = marcados();
      var n = 0;
      fichas.forEach(function (f) { var ok = pasa(f, m, conEd); f.classList.toggle('hidden', !ok); if (ok) n++; });
      casillas.forEach(function (c) {
        var q = c.checked ? n : fichas.filter(function (f) {
          return pasa(f, m.concat([{ g: c.getAttribute('data-filter-group'), v: c.value }]), conEd);
        }).length;
        var fila = c.closest('label');
        var num = fila.querySelector('[data-option-count]');
        if (num) num.textContent = q;
        c.disabled = q === 0 && !c.checked;
        fila.classList.toggle('text-foreground/45', c.disabled);
        fila.classList.toggle('cursor-pointer', !c.disabled);
      });
      botones.forEach(function (b) {
        var g = b.getAttribute('data-filter-toggle');
        var k = m.filter(function (x) { return x.g === g; }).length;
        var marca = b.querySelector('[data-marca]');
        if (!marca) {
          marca = document.createElement('span');
          marca.setAttribute('data-marca', '');
          marca.className = 'text-foreground/70';
          b.insertBefore(marca, b.querySelector('svg'));
        }
        marca.textContent = k ? '(' + k + ')' : '';
      });
      // La casilla de Rols Editions ya no esta -van en su propio bloque-,
      // pero se deja por si vuelve.
      if (editions) {
        editions.setAttribute('aria-pressed', conEd ? 'true' : 'false');
        var caja = editions.querySelector('span');
        ['border-foreground', 'bg-foreground', 'text-background'].forEach(function (c) { caja.classList.toggle(c, conEd); });
        caja.classList.toggle('border-foreground/50', !conEd);
        caja.querySelector('svg').classList.toggle('invisible', !conEd);
      }
      var activos = m.length + (conEd ? 1 : 0);
      borrar[0].classList.toggle('hidden', !activos);
      cuentas.forEach(function (c) { c.textContent = c.getAttribute('data-template').replace('{count}', n); });
      // El titulo "Filtrar" de la columna lleva el numero de filtros puestos.
      if (movil) {
        var marcaM = movil.querySelector('[data-marca]');
        if (!marcaM) {
          marcaM = document.createElement('span');
          marcaM.setAttribute('data-marca', '');
          marcaM.className = 'text-foreground/70';
          movil.insertBefore(marcaM, movil.querySelector('span'));
        }
        marcaM.textContent = activos ? '(' + activos + ')' : '';
      }
      vacio.classList.toggle('hidden', n > 0);
    };
    var abre = function (b, si) {
      var panel = document.getElementById(b.getAttribute('aria-controls'));
      b.setAttribute('aria-expanded', si ? 'true' : 'false');
      panel.classList.toggle('hidden', !si);
      var galon = b.querySelector('svg:last-child');
      if (galon) galon.classList.toggle('rotate-180', si);
    };
    botones.forEach(function (b) {
      b.addEventListener('click', function () {
        var si = b.getAttribute('aria-expanded') !== 'true';
        botones.forEach(function (o) { abre(o, false); });
        abre(b, si);
      });
    });
    // En el movil la columna de filtros se pliega tras "Filtrar".
    if (movil && lista) {
      movil.addEventListener('click', function () {
        var si = movil.getAttribute('aria-expanded') !== 'true';
        movil.setAttribute('aria-expanded', si ? 'true' : 'false');
        lista.classList.toggle('hidden', !si);
        var galon = movil.querySelector('svg');
        if (galon) galon.classList.toggle('rotate-180', si);
      });
    }
    var barra = (botones[0] && botones[0].closest('div.relative')) || document.body;
    if (botones.length) document.addEventListener('pointerdown', function (e) {
      if (!barra.contains(e.target)) botones.forEach(function (o) { abre(o, false); });
    });
    window.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') botones.forEach(function (o) { abre(o, false); });
    });
    casillas.forEach(function (c) { c.addEventListener('change', pinta); });
    if (editions) editions.addEventListener('click', function () { conEd = !conEd; pinta(); });
    borrar.forEach(function (b) {
      b.addEventListener('click', function () {
        casillas.forEach(function (c) { c.checked = false; });
        conEd = false; pinta();
      });
    });
  })();
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

# Red de seguridad: en una pagina estatica no puede quedar nada apuntando al
# optimizador de Next, porque ahi no hay servidor que responda. Si queda,
# sale roto en pantalla -paso con los logos de los estudios-, asi que mejor
# enterarse aqui que en el navegador de Alina.
sueltas = page.count("/_next/image")
if sueltas:
    print("AVISO:", sueltas, "imagenes se han quedado sin embeber (apuntan a /_next/image)")

print("imagenes:", len(cache), "| tamano:", len(page) // 1024, "KB")
