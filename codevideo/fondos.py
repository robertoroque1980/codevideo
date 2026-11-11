"""Fondos: procedurales (aurora, gradiente, color) o con material propio (imagen, video)."""
import glob
import os
import subprocess

import numpy as np
from PIL import Image, ImageFilter, ImageOps

MOVIMIENTOS = ("zoom-in", "zoom-out", "pan-izq", "pan-der", "pan-arriba", "pan-abajo")


def _ampliar(arr, W, H):
    """Escala un campo float de baja resolución a WxH sin bandas (canales en modo F)."""
    out = np.empty((H, W, arr.shape[2]), np.float32)
    for c in range(arr.shape[2]):
        out[..., c] = np.asarray(Image.fromarray(arr[..., c], "F").resize((W, H), Image.BICUBIC))
    return out


class Fondo:
    def __init__(self, spec, W, H, paleta, fps, dur, idx, tmp):
        self.s, self.W, self.H, self.p, self.fps, self.dur, self.idx = spec, W, H, paleta, fps, max(dur, 0.1), idx
        self.tipo = spec["tipo"]
        self.medio = self.tipo in ("imagen", "video")
        rng = np.random.default_rng(spec.get("semilla", 11 + idx * 7))
        if self.tipo in ("aurora", "gradiente"):
            self._init_aurora(rng)
        elif self.tipo == "color":
            c = spec.get("color", paleta["fondo"][0])
            if isinstance(c, str):
                c = tuple(int(c.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
            self.color = np.asarray(c, np.float32)
        elif self.tipo == "imagen":
            self._init_imagen()
        elif self.tipo == "video":
            self._init_video(tmp)
        else:
            raise ValueError(f"fondo desconocido: {self.tipo}")
        part = spec.get("particulas", self.tipo == "aurora" and not paleta["claro"])
        self.part = None
        if part:
            self._init_particulas(rng)
        if self.medio:
            self._init_velo()

    # ---------- aurora / gradiente
    def _init_aurora(self, rng):
        self.gw, self.gh = max(24, self.W // 10), max(24, self.H // 10)
        yy, xx = np.mgrid[0:self.gh, 0:self.gw].astype(np.float32)
        self.xx, self.yy = xx / (self.gw - 1), yy / (self.gh - 1)
        a, b = [np.asarray(c, np.float32) for c in self.p["fondo"][:2]]
        k = np.clip(self.yy * 0.85 + self.xx * 0.15, 0, 1)[..., None]
        self.base = a + (b - a) * k
        self.blobs = []
        if self.tipo == "aurora":
            inten = self.s.get("intensidad", 1.0) * (0.55 if not self.p["claro"] else 0.8)
            for i, col in enumerate(self.p["luces"]):
                self.blobs.append(dict(
                    col=np.asarray(col, np.float32), cx=rng.uniform(0.2, 0.8), cy=rng.uniform(0.15, 0.85),
                    ax=rng.uniform(0.15, 0.35), ay=rng.uniform(0.12, 0.3),
                    wx=rng.uniform(0.10, 0.22), wy=rng.uniform(0.08, 0.18),
                    px=rng.uniform(0, 6.28), py=rng.uniform(0, 6.28),
                    s=rng.uniform(0.26, 0.42), k=inten * rng.uniform(0.75, 1.0)))

    def _aurora(self, t):
        f = self.base.copy()
        asp = self.H / self.W
        for b in self.blobs:
            cx = b["cx"] + b["ax"] * np.sin(b["wx"] * t + b["px"])
            cy = b["cy"] + b["ay"] * np.cos(b["wy"] * t + b["py"])
            d2 = (self.xx - cx) ** 2 + ((self.yy - cy) * asp) ** 2
            g = np.exp(-d2 / (2 * b["s"] ** 2))[..., None] * b["k"]
            f += (b["col"] - f) * g
        return _ampliar(f, self.W, self.H)

    # ---------- partículas (polvo de luz)
    def _init_particulas(self, rng):
        n = int(self.s.get("cantidad", 34))
        self.pw, self.ph = max(16, self.W // 4), max(16, self.H // 4)
        self.part = dict(
            x=rng.uniform(0, 1, n), y=rng.uniform(0, 1, n), vy=rng.uniform(0.008, 0.035, n),
            sw=rng.uniform(0.01, 0.04, n), fw=rng.uniform(0.2, 0.7, n), ph=rng.uniform(0, 6.28, n),
            r=rng.uniform(0.9, 3.6, n) * self.pw / 270, b=rng.uniform(0.25, 1.0, n), tw=rng.uniform(0.4, 1.4, n))
        c = np.asarray(self.p["acento"], np.float32)
        self.part_col = (c + (255 - c) * 0.35) * 0.55

    def _particulas(self, f, t):
        p = self.part
        campo = np.zeros((self.ph, self.pw), np.float32)
        xs = (p["x"] + p["sw"] * np.sin(p["fw"] * t + p["ph"])) % 1.0 * self.pw
        ys = (p["y"] - p["vy"] * t) % 1.0 * self.ph
        br = p["b"] * (0.55 + 0.45 * np.sin(p["tw"] * t + p["ph"]))
        for x, y, r, b in zip(xs, ys, p["r"], br):
            R = int(r * 3) + 1
            x0, x1 = int(x) - R, int(x) + R + 1
            y0, y1 = int(y) - R, int(y) + R + 1
            cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(self.pw, x1), min(self.ph, y1)
            if cx1 <= cx0 or cy1 <= cy0:
                continue
            gy, gx = np.mgrid[cy0:cy1, cx0:cx1].astype(np.float32)
            campo[cy0:cy1, cx0:cx1] += b * np.exp(-((gx - x) ** 2 + (gy - y) ** 2) / (2 * r * r))
        g = np.asarray(Image.fromarray(campo, "F").resize((self.W, self.H), Image.BILINEAR))
        f += g[..., None] * self.part_col

    # ---------- imagen con movimiento de cámara (Ken Burns)
    def _init_imagen(self):
        img = ImageOps.exif_transpose(Image.open(self.s["imagen"])).convert("RGB")
        foco = self.s.get("foco", [0.5, 0.5])
        img = ImageOps.fit(img, (int(self.W * 1.2), int(self.H * 1.2)), Image.LANCZOS, centering=tuple(foco))
        if self.s.get("desenfoque"):
            img = img.filter(ImageFilter.GaussianBlur(self.s["desenfoque"] * self.W / 1080))
        self.img = img
        mov = self.s.get("movimiento", "auto")
        if mov == "auto":
            mov = MOVIMIENTOS[self.idx % len(MOVIMIENTOS)]
        self.mov = mov

    def _imagen(self, t):
        p = min(1.0, max(0.0, t / self.dur))
        zmax = 1.0 + 0.16 * self.s.get("fuerza", 1.0)
        z, cx, cy = zmax, 0.5, 0.5
        d = (1 - 1 / zmax) / 2
        m = self.mov
        if m == "zoom-in":
            z = 1 + (zmax - 1) * p
        elif m == "zoom-out":
            z = zmax - (zmax - 1) * p
        elif m == "pan-izq":
            cx = 0.5 + d - 2 * d * p
        elif m == "pan-der":
            cx = 0.5 - d + 2 * d * p
        elif m == "pan-arriba":
            cy = 0.5 + d - 2 * d * p
        elif m == "pan-abajo":
            cy = 0.5 - d + 2 * d * p
        sw, sh = self.img.size
        w, h = sw / z, sh / z
        x0, y0 = cx * sw - w / 2, cy * sh - h / 2
        fr = self.img.resize((self.W, self.H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))
        return np.asarray(fr, np.float32).copy()

    # ---------- video propio
    def _init_video(self, tmp):
        d = os.path.join(tmp, f"vid{self.idx:03d}")
        os.makedirs(d, exist_ok=True)
        vf = (f"scale={self.W}:{self.H}:force_original_aspect_ratio=increase,"
              f"crop={self.W}:{self.H},fps={self.fps}")
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(self.s.get("inicio", 0)), "-t", f"{self.dur + 0.2:.3f}",
               "-i", self.s["video"], "-an", "-vf", vf, "-q:v", "3", os.path.join(d, "%05d.jpg")]
        subprocess.run(cmd, check=True)
        self.cuadros = sorted(glob.glob(os.path.join(d, "*.jpg")))
        if not self.cuadros:
            raise RuntimeError(f"No se pudieron leer cuadros de {self.s['video']}")

    def _video(self, t):
        n = len(self.cuadros)
        i = int(t * self.fps)
        i = i % n if self.s.get("bucle", True) else min(i, n - 1)
        return np.asarray(Image.open(self.cuadros[i]).convert("RGB"), np.float32).copy()

    def _init_velo(self):
        """Oscurecido para que el texto se lea sobre fotos/videos."""
        osc = self.s.get("oscurecer", 0.35)
        y = np.linspace(0, 1, self.H, dtype=np.float32)
        borde = 0.28 * np.clip((y - 0.45) / 0.55, 0, 1) ** 1.5 + 0.12 * np.clip((0.3 - y) / 0.3, 0, 1)
        self.velo = ((1 - osc) * (1 - borde * (1 if osc > 0 else 0)))[:, None, None]

    # ---------- API
    def cuadro(self, t):
        if self.tipo in ("aurora", "gradiente"):
            f = self._aurora(t)
        elif self.tipo == "color":
            f = np.empty((self.H, self.W, 3), np.float32)
            f[:] = self.color
        elif self.tipo == "imagen":
            f = self._imagen(t)
        else:
            f = self._video(t)
        if self.medio:
            f *= self.velo
        if self.part is not None:
            self._particulas(f, t)
        return f
