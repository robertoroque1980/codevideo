"""Maquetado y dibujo de texto animado, y el lienzo que compone capas sobre el fondo."""
import os
import re
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DIR_FUENTES = os.path.join(os.path.dirname(__file__), "assets", "fonts")


@lru_cache(maxsize=256)
def fuente(nombre, tam):
    return ImageFont.truetype(os.path.join(DIR_FUENTES, nombre), max(4, int(round(tam))))


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def sale(x):          # ease-out cúbico
    x = clamp(x)
    return 1 - (1 - x) ** 3


def suave(x):         # ease-in-out
    x = clamp(x)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- lienzo

class Lienzo:
    """Fondo (float32 HxWx3, 0-255) + capas de máscara de un color cada una."""

    def __init__(self, base, u, sombra=True):
        self.base = base
        self.H, self.W = base.shape[:2]
        self.u = u
        self.sombra_def = sombra
        self.capas = {}

    def capa(self, color, clave=None, sombra=None, opac=1.0):
        k = clave or tuple(color)
        if k not in self.capas:
            img = Image.new("L", (self.W, self.H), 0)
            self.capas[k] = dict(tipo="mascara", img=img, draw=ImageDraw.Draw(img), color=color,
                                 sombra=self.sombra_def if sombra is None else sombra, opac=opac)
        c = self.capas[k]
        return c["img"], c["draw"]

    def imagen(self, rgba, x, y, opac=1.0, clave=None):
        self.capas[clave or f"img{len(self.capas)}"] = dict(tipo="imagen", img=rgba, x=int(x), y=int(y), opac=opac)

    def pildora(self, color, caja, radio, fill=255, clave=None, sombra=False):
        """Rectángulo redondeado con bordes suavizados (supermuestreo 3x)."""
        img, _ = self.capa(color, clave=clave or ("pild", tuple(color)), sombra=sombra)
        x0, y0, x1, y1 = [int(round(v)) for v in caja]
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        s = 3
        tmp = Image.new("L", (w * s, h * s), 0)
        ImageDraw.Draw(tmp).rounded_rectangle((0, 0, w * s - 1, h * s - 1), radius=int(radio * s), fill=int(fill))
        img.paste(tmp.resize((w, h), Image.LANCZOS), (x0, y0))

    def componer(self):
        b = self.base
        r = max(2, int(9 * self.u))
        dy = max(1, int(4 * self.u))
        for c in self.capas.values():
            if c["tipo"] == "imagen":
                self._pegar(c)
                continue
            caja = c["img"].getbbox()
            if not caja:
                continue
            x0, y0, x1, y1 = caja
            if c["sombra"]:
                p = 3 * r
                sx0, sy0 = max(0, x0 - p), max(0, y0 - p)
                sx1, sy1 = min(self.W, x1 + p), min(self.H - dy, y1 + p)
                if sy1 > sy0:
                    m = c["img"].crop((sx0, sy0, sx1, sy1)).filter(ImageFilter.GaussianBlur(r))
                    k = 1.0 - np.asarray(m, np.float32)[..., None] * (0.5 * c["opac"] / 255.0)
                    b[sy0 + dy:sy1 + dy, sx0:sx1] *= k
            m = np.asarray(c["img"].crop(caja), np.float32)[..., None] * (c["opac"] / 255.0)
            reg = b[y0:y1, x0:x1]
            reg += (np.asarray(c["color"], np.float32) - reg) * m
        return b

    def _pegar(self, c):
        img = c["img"]
        x, y = c["x"], c["y"]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.W, x + img.width), min(self.H, y + img.height)
        if x1 <= x0 or y1 <= y0:
            return
        a = np.asarray(img.crop((x0 - x, y0 - y, x1 - x, y1 - y)), np.float32)
        m = a[..., 3:4] * (c["opac"] / 255.0)
        reg = self.base[y0:y1, x0:x1]
        reg += (a[..., :3] - reg) * m


# ---------------------------------------------------------------- bloques de texto

def _unidades(texto, mayus):
    """Devuelve líneas explícitas; cada línea es una lista de unidades;
    cada unidad es una lista de piezas (texto, enfasis) que no se separan."""
    enf = False
    lineas = []
    for cruda in texto.split("\n"):
        us = []
        partes = re.split(r"(\*)", cruda)
        junto = False            # ¿el texto anterior terminó sin espacio? (para pegar "*énfasis*," sin cortar)
        for parte in partes:
            if parte == "*":
                enf = not enf
                continue
            if not parte:
                continue
            for j, w in enumerate(parte.split()):
                if mayus:
                    w = w.upper()
                if j == 0 and junto and not parte[0].isspace() and us:
                    us[-1].append((w, enf))
                else:
                    us.append([(w, enf)])
            junto = not parte[-1].isspace()
        lineas.append(us)
    return lineas


class Bloque:
    """Texto envuelto, balanceado y auto-ajustado a una caja. *palabra* = énfasis (color de acento)."""

    def __init__(self, texto, fuente_nombre, tam, ancho, alto=None, alinear="centro",
                 interlinea=1.14, tracking=0.0, mayus=False, tam_min=None):
        self.alinear = alinear
        self.ancho = ancho
        self.fuente_nombre = fuente_nombre
        lineas_exp = _unidades(texto, mayus)
        tam_min = tam_min or tam * 0.45
        while True:
            self.tam = tam
            self.f = fuente(fuente_nombre, tam)
            self.track = tracking * tam
            self.esp = self.f.getlength(" ") + self.track
            self._medir(lineas_exp, interlinea)
            if tam <= tam_min or (self.w <= ancho + 1 and (alto is None or self.h <= alto)):
                break
            tam *= 0.94

    def _ancho_txt(self, s):
        if self.track:
            return sum(self.f.getlength(ch) for ch in s) + self.track * (len(s) - 1)
        return self.f.getlength(s)

    def _envolver(self, us, maxw):
        lineas, act, w = [], [], 0.0
        for u, uw in us:
            extra = uw if not act else self.esp + uw
            if act and w + extra > maxw:
                lineas.append((act, w))
                act, w = [(u, uw)], uw
            else:
                act.append((u, uw))
                w += extra
        if act:
            lineas.append((act, w))
        return lineas

    def _medir(self, lineas_exp, interlinea):
        asc, desc = self.f.getmetrics()
        self.asc = asc
        self.alto_linea = self.tam * interlinea
        self.lineas = []
        for us in lineas_exp:
            med = [(u, sum(self._ancho_txt(t) for t, _ in u)) for u in us]
            if not med:
                self.lineas.append(([], 0.0))
                continue
            ls = self._envolver(med, self.ancho)
            if len(ls) > 1:   # balancear: el ancho mínimo que mantiene la cantidad de líneas
                lo, hi = max(w for _, w in med), self.ancho
                for _ in range(12):
                    mid = (lo + hi) / 2
                    if len(self._envolver(med, mid)) <= len(ls):
                        hi = mid
                    else:
                        lo = mid
                ls = self._envolver(med, hi)
            self.lineas.extend(ls)
        self.w = max((w for _, w in self.lineas), default=0)
        self.h = (len(self.lineas) - 1) * self.alto_linea + asc + desc * 0.6
        self.n = sum(len(l) for l, _ in self.lineas)

    def fin(self, inicio=0.0, paso=0.08, dur=0.55):
        return inicio + max(0, self.n - 1) * paso + dur

    def _pieza(self, draw, x, y, s, fill):
        if self.track:
            for ch in s:
                draw.text((x, y), ch, font=self.f, fill=fill, anchor="ls")
                x += self.f.getlength(ch) + self.track
        else:
            draw.text((x, y), s, font=self.f, fill=fill, anchor="ls")

    def dibujar(self, lz, x, y, t, color, acento, inicio=0.0, paso=0.08, dur=0.55, subir=None, opac=1.0):
        """Dibuja en la caja cuya esquina sup-izq es (x, y); las palabras entran escalonadas."""
        subir = self.tam * 0.35 if subir is None else subir
        d_col = lz.capa(color)[1]
        d_ace = lz.capa(acento)[1]
        k = 0
        for i, (linea, lw) in enumerate(self.lineas):
            if self.alinear == "centro":
                px = x + (self.ancho - lw) / 2
            elif self.alinear == "der":
                px = x + self.ancho - lw
            else:
                px = x
            by = y + self.asc + i * self.alto_linea
            for u, uw in linea:
                a = sale((t - inicio - k * paso) / dur) * opac
                k += 1
                if a > 0.004:
                    oy = by + (1 - a / opac) * subir
                    cx = px
                    for s, enf in u:
                        self._pieza(d_ace if enf else d_col, cx, oy, s, int(255 * a))
                        cx += self._ancho_txt(s)
                px += uw + self.esp
