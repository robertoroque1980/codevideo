"""Tipos de escena. Cada una maqueta su contenido una vez y lo dibuja animado en cada cuadro."""
import re

from PIL import Image

from .texto import Bloque, fuente, sale, suave


class Contexto:
    def __init__(self, W, H, paleta, tip, marca, subtitulos):
        self.W, self.H = W, H
        self.u = min(W, H) / 1080
        self.p, self.tip, self.marca = paleta, tip, marca
        alto = H / W > 1.5
        mx = W * (0.09 if alto else 0.08)
        y0 = H * (0.14 if alto else 0.10)
        y1 = H * ((0.69 if subtitulos else 0.80) if alto else (0.75 if subtitulos else 0.88))
        self.area = (mx, y0, W - mx, y1)
        self.y_subs = H * (0.755 if alto else 0.84)


class Escena:
    def __init__(self, e, c, dur, t_narr):
        self.e, self.c, self.dur, self.t_narr = e, c, dur, t_narr
        self.u, self.p, self.T = c.u, c.p, c.tip
        if c.p["claro"] and e["fondo"]["tipo"] in ("imagen", "video"):
            # sobre fotos/videos el texto siempre va claro, aunque el estilo sea de fondo claro
            self.p = dict(c.p, texto=(250, 246, 240), suave=(218, 212, 204), acento=(255, 205, 130))
        self.x0, self.y0, self.x1, self.y1 = c.area
        self.aw, self.ah = self.x1 - self.x0, self.y1 - self.y0
        self.pila = []          # [(alto, espacio_despues, fn(lz, y, t))]
        self.armar()
        total = sum(a + g for a, g, _ in self.pila) - (self.pila[-1][1] if self.pila else 0)
        self.y_ini = self.y0 + (self.ah - total) / 2

    def agregar(self, alto, espacio, fn):
        self.pila.append((alto, espacio * self.u, fn))

    def titular(self, texto, tam, alto=None, alinear="centro", ancho=None, escala=None):
        T = self.T
        return Bloque(texto, T["titulo"], tam * self.u * T["escala"] * (escala or self.e.get("tamano", 1.0)),
                      ancho or self.aw, alto=alto, alinear=alinear, tracking=T["tracking"], mayus=T["mayus"],
                      interlinea=1.0 if T["mayus"] else 1.1)

    def dibujar(self, lz, t):
        y = self.y_ini
        for alto, esp, fn in self.pila:
            fn(lz, y, t)
            y += alto + esp

    def armar(self):
        raise NotImplementedError

    # piezas reutilizables
    def _ante(self, texto, t0):
        b = Bloque(texto, self.T["fuerte"], 30 * self.u, self.aw, tracking=0.2, mayus=True)
        self.agregar(b.h, 40, lambda lz, y, t: b.dibujar(lz, self.x0, y, t, self.p["acento"], self.p["acento"],
                                                         inicio=t0, paso=0.05, subir=0))

    def _linea(self, t0, ancho=110, espacio=44):
        g = max(2, int(3 * self.u))

        def fn(lz, y, t):
            a = sale((t - t0) / 0.7)
            if a > 0:
                w = ancho * self.u * a
                cx = (self.x0 + self.x1) / 2
                lz.capa(self.p["acento"])[1].rectangle((cx - w / 2, y, cx + w / 2, y + g), fill=255)
        self.agregar(g, espacio, fn)


class Titulo(Escena):
    def armar(self):
        e, p = self.e, self.p
        t0 = 0.25
        if e.get("antetitulo"):
            self._ante(e["antetitulo"], t0)
            t0 += 0.3
        tit = self.titular(e.get("texto", ""), 108, alto=self.ah * 0.62)
        fin = tit.fin(t0, 0.09)
        self.agregar(tit.h, 46, lambda lz, y, t: tit.dibujar(lz, self.x0, y, t, p["texto"], p["acento"], inicio=t0, paso=0.09))
        if e.get("subtexto"):
            self._linea(fin - 0.35)
            sub = Bloque(e["subtexto"], self.T["cuerpo"], 44 * self.u, self.aw * 0.92, interlinea=1.32)
            dx = self.x0 + self.aw * 0.04
            self.agregar(sub.h, 0, lambda lz, y, t: sub.dibujar(lz, dx, y, t, p["suave"], p["acento"],
                                                                inicio=fin - 0.1, paso=0.035, subir=14 * self.u))


class Frase(Escena):
    def armar(self):
        e, p = self.e, self.p
        fq = fuente("DMSerifDisplay-Regular.ttf", 210 * self.u)
        bx = fq.getbbox("“", anchor="ls")
        hq = bx[3] - bx[1]

        def comilla(lz, y, t):
            a = sale((t - 0.2) / 0.8)
            if a > 0:
                lz.capa(p["acento"])[1].text(((self.x0 + self.x1) / 2 - (bx[0] + bx[2]) / 2, y - bx[1]), "“",
                                             font=fq, fill=int(255 * a), anchor="ls")
        self.agregar(hq, 38, comilla)
        cita = Bloque(e.get("texto", ""), self.T["cita"], 76 * self.u * e.get("tamano", 1.0), self.aw,
                      alto=self.ah * 0.6, interlinea=1.2)
        fin = cita.fin(0.5, 0.085)
        self.agregar(cita.h, 50, lambda lz, y, t: cita.dibujar(lz, self.x0, y, t, p["texto"], p["acento"], inicio=0.5, paso=0.085))
        if e.get("autor"):
            au = Bloque("— " + e["autor"], self.T["fuerte"], 30 * self.u, self.aw, tracking=0.14, mayus=True)
            self.agregar(au.h, 0, lambda lz, y, t: au.dibujar(lz, self.x0, y, t, p["suave"], p["acento"],
                                                              inicio=fin, paso=0.04, subir=0))


class Lista(Escena):
    def armar(self):
        e, p, u = self.e, self.p, self.u
        t0 = 0.3
        if e.get("titulo"):
            tit = self.titular(e["titulo"], 80, alinear="izq", alto=self.ah * 0.3)
            self.agregar(tit.h, 62, lambda lz, y, t: tit.dibujar(lz, self.x0, y, t, p["texto"], p["acento"], inicio=t0, paso=0.07))
            t0 = tit.fin(t0, 0.07) - 0.2
        items = e.get("items", [])
        n = max(1, len(items))
        libre = max(1.2, min(self.dur - t0 - 1.6, n * 1.6))
        paso = libre / n
        fm = fuente(self.T["fuerte"], 32 * u)
        wm = fm.getlength("00") + 30 * u
        tam = 54 * u * e.get("tamano", 1.0)
        alto_max = (self.ah * 0.68) / n
        for i, it in enumerate(items):
            b = Bloque(it, self.T["cuerpo"], tam, self.aw - wm, alto=alto_max, alinear="izq", interlinea=1.25)
            ti = t0 + i * paso

            def fn(lz, y, t, b=b, ti=ti, i=i):
                a = sale((t - ti) / 0.5)
                if a > 0:
                    lz.capa(p["acento"])[1].text((self.x0, y + b.asc), f"{i + 1:02d}", font=fm, fill=int(255 * a), anchor="ls")
                b.dibujar(lz, self.x0 + wm, y, t, p["texto"], p["acento"], inicio=ti, paso=0.04, subir=18 * u)
            self.agregar(b.h, 44 if i < n - 1 else 0, fn)


class Dato(Escena):
    def armar(self):
        e, p, u = self.e, self.p, self.u
        num = str(e.get("numero", ""))
        m = re.fullmatch(r"(\D*?)(\d+)(\D*)", num)
        tam = 250 * u * self.T["escala"] * e.get("tamano", 1.0)
        f = fuente(self.T["titulo"], tam)
        while f.getlength(num) > self.aw and tam > 60 * u:
            tam *= 0.92
            f = fuente(self.T["titulo"], tam)
        asc = f.getmetrics()[0]
        bb = f.getbbox(num or "0", anchor="ls")
        h = -bb[1]

        def fn(lz, y, t):
            a = sale((t - 0.25) / 0.6)
            if a <= 0:
                return
            s = num
            if m:
                v = int(round(int(m.group(2)) * sale((t - 0.25) / 1.3)))
                s = f"{m.group(1)}{v}{m.group(3)}"
            lz.capa(p["acento"])[1].text(((self.x0 + self.x1) / 2, y + h), s, font=f, fill=int(255 * a), anchor="ms")
        self.agregar(h, 54, fn)
        if e.get("texto"):
            b = Bloque(e["texto"], self.T["cuerpo"], 50 * u, self.aw * 0.92, interlinea=1.28)
            dx = self.x0 + self.aw * 0.04
            self.agregar(b.h, 0, lambda lz, y, t: b.dibujar(lz, dx, y, t, p["texto"], p["acento"], inicio=0.9, paso=0.05))


class Plano(Escena):
    """Solo el fondo (foto/video/aurora) con un texto opcional abajo a la izquierda."""

    def armar(self):
        e, p, u = self.e, self.p, self.u
        self.b = None
        if e.get("texto"):
            self.b = self.titular(e["texto"], 62, alinear="izq", ancho=self.aw * 0.88, alto=self.ah * 0.4)

    def dibujar(self, lz, t):
        if not self.b:
            return
        b, u, p = self.b, self.u, self.p
        y = self.y1 - b.h
        a = sale((t - 0.3) / 0.6)
        if a > 0:
            g = max(3, int(5 * u))
            lz.capa(p["acento"])[1].rectangle((self.x0, y + b.h * (1 - a) * 0.5, self.x0 + g, y + b.h - b.h * (1 - a) * 0.5), fill=255)
        b.dibujar(lz, self.x0 + 30 * u, y, t, p["texto"], p["acento"], inicio=0.45, paso=0.08)


class Cierre(Escena):
    def armar(self):
        e, p, u, marca = self.e, self.p, self.u, self.c.marca
        t0 = 0.25
        if marca.get("logo"):
            logo = Image.open(marca["logo"]).convert("RGBA")
            hl = int(200 * u * e.get("logo_escala", 1.0))
            logo = logo.resize((max(1, int(logo.width * hl / logo.height)), hl), Image.LANCZOS)
            if logo.width > self.aw:
                logo = logo.resize((int(self.aw), max(1, int(logo.height * self.aw / logo.width))), Image.LANCZOS)
            lx = (self.x0 + self.x1) / 2 - logo.width / 2
            self.agregar(logo.height, 56, lambda lz, y, t: lz.imagen(logo, lx, y, opac=sale((t - t0) / 0.8), clave="logo"))
            t0 += 0.3
        elif marca.get("nombre"):
            self._ante(marca["nombre"], t0)
            t0 += 0.3
        tit = self.titular(e.get("texto", ""), 88, alto=self.ah * 0.45)
        fin = tit.fin(t0, 0.085)
        self.agregar(tit.h, 60, lambda lz, y, t: tit.dibujar(lz, self.x0, y, t, p["texto"], p["acento"], inicio=t0, paso=0.085))
        if e.get("boton"):
            fb = fuente(self.T["fuerte"], 40 * u)
            wb = fb.getlength(e["boton"]) + 110 * u
            hb = 104 * u
            oscuro = p["fondo"][0] if not p["claro"] else (255, 252, 246)

            def boton(lz, y, t):
                a = sale((t - fin + 0.1) / 0.6)
                if a <= 0:
                    return
                cx = (self.x0 + self.x1) / 2
                w = wb * (0.86 + 0.14 * a)
                yy = y + (1 - a) * 20 * u
                lz.pildora(p["acento"], (cx - w / 2, yy, cx + w / 2, yy + hb), hb / 2, fill=255 * a, clave="boton", sombra=True)
                lz.capa(oscuro, clave="boton_txt", sombra=False)[1].text((cx, yy + hb / 2), e["boton"], font=fb,
                                                                         fill=int(255 * a), anchor="mm")
            self.agregar(hb, 46, boton)
        usuario = e.get("usuario", marca.get("usuario"))
        if usuario:
            b = Bloque(usuario, self.T["fuerte"], 38 * u, self.aw)
            self.agregar(b.h, 0, lambda lz, y, t: b.dibujar(lz, self.x0, y, t, p["suave"], p["acento"],
                                                            inicio=fin + 0.4, paso=0.05, subir=0))


CLASES = {"titulo": Titulo, "frase": Frase, "lista": Lista, "dato": Dato, "plano": Plano, "cierre": Cierre}
MINIMOS = {"titulo": 3.2, "frase": 4.0, "lista": 4.5, "dato": 3.5, "plano": 3.0, "cierre": 4.0}


def crear(e, ctx, dur, t_narr):
    return CLASES[e["tipo"]](e, ctx, dur, t_narr)
