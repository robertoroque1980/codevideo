"""Acabado cinematográfico: etalonaje (LUT), viñeta, grano de película y barras."""
import numpy as np


def _curva(x, contraste=1.0, negro=0.0, blanco=1.0, gamma=1.0):
    y = np.clip(x, 0, 1) ** gamma
    y = 0.5 + (y - 0.5) * contraste
    s = np.clip(y, 0, 1)
    s = s * s * (3 - 2 * s) * 0.5 + s * 0.5      # hombro y pie suaves
    return negro + s * (blanco - negro)


def _lut(look):
    x = np.linspace(0, 1, 256, dtype=np.float32)
    sombra, luz = (1 - x) ** 2, x ** 2
    sat = 1.0
    if look == "cine":          # sombras azul-verdosas, luces cálidas, negros levantados
        base = _curva(x, 1.12, 0.035, 0.985)
        r = base + 0.035 * luz - 0.020 * sombra
        g = base + 0.006 * luz + 0.006 * sombra
        b = base - 0.045 * luz + 0.040 * sombra
        sat = 0.94
    elif look == "calido":
        base = _curva(x, 1.08, 0.03, 0.99)
        r = base + 0.045 * luz + 0.010 * sombra
        g = base + 0.012 * luz
        b = base - 0.055 * luz - 0.010 * sombra
        sat = 1.02
    elif look == "frio":
        base = _curva(x, 1.1, 0.03, 0.98)
        r = base - 0.035 * luz - 0.01 * sombra
        g = base
        b = base + 0.035 * luz + 0.035 * sombra
        sat = 0.9
    elif look == "noir":
        base = _curva(x, 1.28, 0.02, 0.98)
        r = g = b = base
        sat = 0.0
    elif look == "suave":       # para estilos claros: contraste bajo
        base = _curva(x, 1.02, 0.02, 0.985)
        r = base + 0.012 * luz
        g = base
        b = base - 0.02 * luz
        sat = 0.97
    else:                       # neutro
        r = g = b = x
    return (np.stack([r, g, b], 1) * 255).astype(np.float32), sat


class Post:
    def __init__(self, W, H, look="cine", grano=1.0, vineta=1.0, barras=0.0, claro=False, semilla=3):
        self.W, self.H = W, H
        self.lut, self.sat = _lut(look)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((xx / W - 0.5) * 1.15) ** 2 + ((yy / H - 0.5) * 1.15) ** 2) / 0.72
        fuerza = (0.16 if claro else 0.42) * vineta
        self.vin = (1 - fuerza * np.clip(d - 0.35, 0, 1) ** 1.8)[..., None]
        self.grano = (2.5 if claro else 4.5) * grano
        self.pad = 96
        rng = np.random.default_rng(semilla)
        self.ruido = rng.standard_normal((H + self.pad, W + self.pad)).astype(np.float32) if self.grano > 0 else None
        self.barras = int(H * barras) if barras else 0
        self.idx_r = np.arange(256)

    def aplicar(self, f, i, fundido=1.0):
        """f: float32 HxWx3 (0-255). Devuelve uint8."""
        u = np.clip(f, 0, 255).astype(np.uint8)
        f = np.empty_like(f)
        for c in range(3):
            f[..., c] = self.lut[u[..., c], c]
        if self.sat != 1.0:
            l = (f[..., 0] * 0.299 + f[..., 1] * 0.587 + f[..., 2] * 0.114)[..., None]
            f = l + (f - l) * self.sat
        f *= self.vin * fundido if fundido < 1.0 else self.vin
        if self.ruido is not None:
            rng = np.random.default_rng(i * 7919 + 13)
            oy, ox = rng.integers(0, self.pad, 2)
            g = self.ruido[oy:oy + self.H, ox:ox + self.W]
            if i % 2:
                g = g[:, ::-1]
            f += (g * self.grano)[..., None]
        if self.barras:
            f[:self.barras] = 0
            f[-self.barras:] = 0
        return np.clip(f, 0, 255).astype(np.uint8)
