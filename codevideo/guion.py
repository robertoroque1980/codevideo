"""Carga y normalización del guion (JSON) + catálogos de formatos, estilos y tipografías."""
import json
import os

FORMATOS = {
    "reel": (1080, 1920),
    "historia": (1080, 1920),
    "vertical": (1080, 1350),
    "cuadrado": (1080, 1080),
    "horizontal": (1920, 1080),
}

# fondo: degradé base (arriba, abajo) · luces: manchas de color en movimiento
ESTILOS = {
    "noche": dict(
        fondo=[(7, 11, 22), (13, 27, 46)],
        luces=[(22, 92, 122), (128, 72, 30), (44, 50, 124)],
        texto=(246, 241, 231), suave=(186, 192, 204), acento=(233, 181, 92),
        look="cine", claro=False),
    "calido": dict(
        fondo=[(26, 13, 9), (62, 28, 17)],
        luces=[(186, 86, 38), (132, 46, 40), (214, 146, 66)],
        texto=(253, 245, 233), suave=(222, 200, 180), acento=(255, 198, 112),
        look="calido", claro=False),
    "bosque": dict(
        fondo=[(7, 18, 15), (15, 40, 32)],
        luces=[(38, 118, 80), (118, 128, 48), (18, 80, 92)],
        texto=(240, 245, 235), suave=(186, 202, 190), acento=(196, 222, 132),
        look="cine", claro=False),
    "violeta": dict(
        fondo=[(12, 8, 24), (30, 16, 52)],
        luces=[(96, 48, 150), (160, 60, 110), (40, 60, 140)],
        texto=(246, 240, 250), suave=(200, 190, 214), acento=(244, 170, 200),
        look="cine", claro=False),
    "noir": dict(
        fondo=[(5, 5, 7), (22, 22, 26)],
        luces=[(72, 72, 82), (40, 40, 50), (92, 92, 102)],
        texto=(246, 246, 246), suave=(180, 180, 184), acento=(222, 62, 50),
        look="noir", claro=False),
    "claro": dict(
        fondo=[(246, 240, 230), (229, 217, 201)],
        luces=[(255, 228, 188), (232, 200, 180), (252, 247, 238)],
        texto=(30, 27, 24), suave=(96, 88, 80), acento=(176, 90, 46),
        look="suave", claro=True),
}

TIPOGRAFIAS = {
    "serif": dict(titulo="DMSerifDisplay-Regular.ttf", cita="DMSerifDisplay-Italic.ttf",
                  cuerpo="Inter-Medium.otf", fuerte="Inter-SemiBold.otf",
                  mayus=False, tracking=0.0, escala=1.0),
    "sans": dict(titulo="Inter-ExtraBold.otf", cita="Inter-SemiBold.otf",
                 cuerpo="Inter-Medium.otf", fuerte="Inter-Bold.otf",
                 mayus=False, tracking=-0.02, escala=0.9),
    "trailer": dict(titulo="BebasNeue-Regular.ttf", cita="DMSerifDisplay-Italic.ttf",
                    cuerpo="Inter-Medium.otf", fuerte="Inter-SemiBold.otf",
                    mayus=True, tracking=0.05, escala=1.25),
}

TIPOS_ESCENA = ("titulo", "frase", "lista", "dato", "plano", "cierre")
TRANSICIONES = ("disolver", "corte", "negro", "destello", "deslizar")
MUSICAS = ("ambient", "esperanza", "intimo", "tension", "epico")


class ErrorGuion(Exception):
    pass


def _color(v):
    if isinstance(v, str):
        s = v.lstrip("#")
        if len(s) != 6:
            raise ErrorGuion(f"Color inválido: {v!r} (usar #RRGGBB)")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(int(x) for x in v)


def cargar(ruta):
    with open(ruta, encoding="utf-8") as f:
        try:
            g = json.load(f)
        except json.JSONDecodeError as e:
            raise ErrorGuion(f"El guion no es JSON válido: {e}")
    base = os.path.dirname(os.path.abspath(ruta))
    g["_base"] = base
    g["_nombre"] = os.path.splitext(os.path.basename(ruta))[0]

    fmt = g.setdefault("formato", "reel")
    if fmt not in FORMATOS:
        raise ErrorGuion(f"formato desconocido: {fmt}. Opciones: {', '.join(FORMATOS)}")
    g.setdefault("fps", 30)

    est = g.setdefault("estilo", "noche")
    if est not in ESTILOS:
        raise ErrorGuion(f"estilo desconocido: {est}. Opciones: {', '.join(ESTILOS)}")
    paleta = dict(ESTILOS[est])
    for k, v in (g.get("colores") or {}).items():   # sobreescribir colores de marca
        if k in ("texto", "suave", "acento"):
            paleta[k] = _color(v)
        elif k in ("fondo", "luces"):
            paleta[k] = [_color(c) for c in v]
    g["_paleta"] = paleta

    tip = g.setdefault("tipografia", "serif")
    if tip not in TIPOGRAFIAS:
        raise ErrorGuion(f"tipografia desconocida: {tip}. Opciones: {', '.join(TIPOGRAFIAS)}")

    g.setdefault("marca", {})
    g.setdefault("subtitulos", True)
    g.setdefault("transicion", "disolver")
    g.setdefault("grano", 1.0)
    g.setdefault("vineta", 1.0)
    g.setdefault("barras", 0.0)

    voz = g.get("voz", {})
    if voz is False or voz is None:
        voz = {"activa": False}
    voz.setdefault("activa", True)
    voz.setdefault("modelo", "daniela")
    voz.setdefault("velocidad", 0.95)
    g["voz"] = voz

    mus = g.get("musica", {})
    if mus is False or mus is None:
        mus = {"activa": False}
    mus.setdefault("activa", True)
    mus.setdefault("tipo", "ambient")
    mus.setdefault("volumen", 0.6)
    mus.setdefault("efectos", True)
    mus.setdefault("semilla", 7)
    if "archivo" not in mus and mus["tipo"] not in MUSICAS:
        raise ErrorGuion(f"musica.tipo desconocido: {mus['tipo']}. Opciones: {', '.join(MUSICAS)}")
    g["musica"] = mus

    esc = g.get("escenas")
    if not esc:
        raise ErrorGuion("El guion no tiene escenas.")
    for i, e in enumerate(esc):
        t = e.setdefault("tipo", "titulo")
        if t not in TIPOS_ESCENA:
            raise ErrorGuion(f"escena {i + 1}: tipo desconocido {t!r}. Opciones: {', '.join(TIPOS_ESCENA)}")
        tr = e.setdefault("transicion", g["transicion"])
        if tr not in TRANSICIONES:
            raise ErrorGuion(f"escena {i + 1}: transicion desconocida {tr!r}. Opciones: {', '.join(TRANSICIONES)}")
        f = e.get("fondo", g.get("fondo", {"tipo": "aurora"}))
        if isinstance(f, str):
            f = {"tipo": f}
        f = dict(f)
        for clave in ("imagen", "video"):
            if clave in f:
                f["tipo"] = clave
                p = f[clave] if os.path.isabs(f[clave]) else os.path.join(base, f[clave])
                if not os.path.exists(p):
                    raise ErrorGuion(f"escena {i + 1}: no existe el archivo {f[clave]!r} (buscado en {p})")
                f[clave] = p
        f.setdefault("tipo", "aurora")
        e["fondo"] = f
    logo = g["marca"].get("logo")
    if logo:
        p = logo if os.path.isabs(logo) else os.path.join(base, logo)
        if not os.path.exists(p):
            raise ErrorGuion(f"marca.logo: no existe {logo!r}")
        g["marca"]["logo"] = p
    return g
