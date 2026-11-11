"""Proyecto: arma la línea de tiempo, el audio y renderiza los cuadros en paralelo hacia ffmpeg."""
import bisect
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image

from . import audio, escenas, guion as G
from .fondos import Fondo
from .post import Post
from .texto import Lienzo, fuente, sale, suave
from .voz import SR as SR_VOZ, Narrador, RAIZ

DUR_TRANS = {"disolver": 0.6, "corte": 0.0, "negro": 0.9, "destello": 0.5, "deslizar": 0.55}


class Proyecto:
    def __init__(self, ruta, borrador=False, log=print):
        self.g = G.cargar(ruta)
        self.log = log
        W, H = G.FORMATOS[self.g["formato"]]
        if borrador:
            W, H = W // 2, H // 2
        self.W, self.H = W - W % 2, H - H % 2
        self.fps = int(self.g["fps"]) if not borrador else min(int(self.g["fps"]), 24)
        self.p = self.g["_paleta"]
        self.tmp = tempfile.mkdtemp(prefix="codevideo_")
        self.listo = False

    # ------------------------------------------------------------ preparación
    def preparar(self, con_audio=True):
        g, es = self.g, self.g["escenas"]
        self.ctx = escenas.Contexto(self.W, self.H, self.p, G.TIPOGRAFIAS[g["tipografia"]], g["marca"], bool(g["subtitulos"]))
        narr = Narrador(g["voz"], os.path.join(RAIZ, ".cache", "voz"))
        self.inicios, self.durs, self.trans, voces, self.palabras = [], [], [], [], []
        t = 0.0
        for i, e in enumerate(es):
            a, pal = narr.narrar(e.get("narracion", ""))
            dn = len(a) / SR_VOZ
            retraso = 0.6 if i == 0 else 0.45
            minimo = dn + retraso + 0.55 if dn else 0.0
            d = e.get("duracion")
            if d is None:
                d = max(escenas.MINIMOS[e["tipo"]], minimo)
            elif d < minimo:
                self.log(f"  ! escena {i + 1}: la narración dura {dn:.1f}s; alargo la escena de {d}s a {minimo:.1f}s")
                d = minimo
            self.inicios.append(t)
            self.durs.append(float(d))
            self.trans.append(0.0 if i == 0 else DUR_TRANS[e["transicion"]])
            if dn:
                voces.append((t + retraso, a))
                grupo = [(w, t + retraso + a0, t + retraso + a1) for w, a0, a1 in pal]
                if e.get("subtitulos", True):
                    self.palabras.append(grupo)
            e["_narr"] = dn
            t += d
        self.total = t
        self.n = int(round(self.total * self.fps))
        self.hay_voz = bool(voces)

        self.fondos, self.esc = [], []
        for i, e in enumerate(es):
            cola = self.trans[i + 1] if i + 1 < len(es) else 0.0
            self.fondos.append(Fondo(e["fondo"], self.W, self.H, self.p, self.fps, self.durs[i] + cola, i, self.tmp))
            self.esc.append(escenas.crear(e, self.ctx, self.durs[i], e["_narr"]))
        self.post = Post(self.W, self.H, g.get("look", self.p["look"]), g["grano"], g["vineta"], g["barras"], self.p["claro"])
        self._armar_subtitulos()
        self.wav = None
        if con_audio:
            self.wav = audio.mezclar(self.total, voces, g["musica"], self.inicios[1:], self.tmp,
                                     os.path.join(self.tmp, "mezcla.wav"))
        self.listo = True

    def resumen(self):
        self.log(f"  {self.W}x{self.H} · {self.fps} fps · {self.total:.1f} s · {len(self.esc)} escenas"
                 f" · voz: {'sí' if self.hay_voz else 'no'} · música: "
                 f"{self.g['musica'].get('archivo') or self.g['musica']['tipo'] if self.g['musica']['activa'] else 'no'}")
        for i, e in enumerate(self.g["escenas"]):
            txt = (e.get("texto") or e.get("titulo") or e.get("numero") or "").replace("\n", " ")
            self.log(f"   {i + 1:>2}. {self.inicios[i]:5.1f}s  {self.durs[i]:4.1f}s  {e['tipo']:<7} {txt[:48]}")

    # ------------------------------------------------------------ subtítulos
    def _armar_subtitulos(self):
        self.subs = []
        if not self.g["subtitulos"]:
            return
        for grupo in self.palabras:
            act = []
            for w, a, b in grupo:
                act.append((w, a, b))
                largo = sum(len(x[0]) for x in act)
                if len(act) >= 4 or largo >= 22 or w[-1] in ".,;:!?…":
                    self.subs.append(act)
                    act = []
            if act:
                self.subs.append(act)
        unidos = []                      # no dejar una palabra suelta colgando
        for c in self.subs:
            if (unidos and len(c) == 1 and unidos[-1][-1][0][-1] not in ".!?…" and c[0][1] - unidos[-1][-1][2] < 0.3
                    and sum(len(x[0]) for x in unidos[-1]) + len(c[0][0]) <= 30):
                unidos[-1] = unidos[-1] + c
            else:
                unidos.append(c)
        self.subs = unidos
        self.subs_ini = [c[0][1] for c in self.subs]
        u = self.ctx.u
        self.f_sub = fuente("Inter-ExtraBold.otf", 54 * u)

    def _subtitulo(self, lz, t):
        if not self.subs:
            return
        k = bisect.bisect_right(self.subs_ini, t + 0.06) - 1
        if k < 0:
            return
        c = self.subs[k]
        fin = c[-1][2] + 0.4
        if k + 1 < len(self.subs):
            fin = min(fin, self.subs_ini[k + 1] - 0.06)
        if t > fin:
            return
        u, f = self.ctx.u, self.f_sub
        ws = [w.strip(".,;:…") for w, _, _ in c]
        esp = f.getlength(" ")
        anchos = [f.getlength(w) for w in ws]
        total = sum(anchos) + esp * (len(ws) - 1)
        maxw = self.W * 0.84
        if total > maxw:
            f = fuente("Inter-ExtraBold.otf", 54 * u * maxw / total)
            esp = f.getlength(" ")
            anchos = [f.getlength(w) for w in ws]
            total = sum(anchos) + esp * (len(ws) - 1)
        a = sale((t - c[0][1] + 0.06) / 0.14)
        cy = self.ctx.y_subs + (1 - a) * 10 * u
        px, py = 30 * u, 20 * u
        asc, desc = f.getmetrics()
        x = (self.W - total) / 2
        lz.pildora((0, 0, 0), (x - px, cy - asc / 2 - py - desc / 4, x + total + px, cy + asc / 2 + py + desc / 4),
                   22 * u, fill=255 * a, clave="sub_caja")
        lz.capas["sub_caja"]["opac"] = 0.56
        d_b = lz.capa((255, 255, 255), clave="sub_b", sombra=False)[1]
        d_a = lz.capa(self.p["acento"] if not self.p["claro"] else (255, 205, 130), clave="sub_a", sombra=False)[1]
        actual = max((j for j, x in enumerate(c) if x[1] <= t), default=0)
        for j, (w, an) in enumerate(zip(ws, anchos)):
            activa = j == actual
            (d_a if activa else d_b).text((x, cy), w, font=f, fill=int(255 * a), anchor="lm")
            x += an + esp

    def _firma(self, lz, k):
        m = self.g["marca"]
        if not m.get("firma") or not m.get("usuario") or self.g["escenas"][k]["tipo"] == "cierre":
            return
        f = fuente("Inter-SemiBold.otf", 28 * self.ctx.u)
        lz.capa(self.p["suave"], clave="firma", sombra=False, opac=0.75)[1].text(
            (self.W / 2, self.ctx.area[1] * 0.62), m["usuario"], font=f, fill=255, anchor="mm")

    # ------------------------------------------------------------ cuadros
    def _escena(self, k, tl):
        f = self.fondos[k].cuadro(tl)
        lz = Lienzo(f, self.ctx.u, sombra=not self.p["claro"] or self.fondos[k].medio)
        self.esc[k].dibujar(lz, tl)
        return lz.componer()

    def cuadro(self, i, t=None):
        t = i / self.fps if t is None else t
        k = max(0, bisect.bisect_right(self.inicios, t) - 1)
        tl = t - self.inicios[k]
        f = self._escena(k, tl)
        T = self.trans[k]
        if k > 0 and tl < T:
            a = tl / T
            tipo = self.g["escenas"][k]["transicion"]
            prev = self._escena(k - 1, t - self.inicios[k - 1])
            if tipo == "negro":
                f = prev * (1 - suave(a * 2)) if a < 0.5 else f * suave(a * 2 - 1)
            elif tipo == "deslizar":
                off = int(self.H * suave(a))
                out = np.empty_like(f)
                out[:self.H - off] = prev[off:]
                out[self.H - off:] = f[:off]
                f = out
            else:
                s = suave(a)
                f = prev + (f - prev) * s
                if tipo == "destello":
                    c = np.asarray(self.p["acento"], np.float32)
                    f += (c + (255 - c) * 0.5) * (np.sin(np.pi * a) ** 2 * 0.26)
        lz = Lienzo(f, self.ctx.u, sombra=False)
        self._subtitulo(lz, t)
        self._firma(lz, k)
        f = lz.componer()
        fundido = suave(min(1.0, t / 0.6, (self.total - t) / 0.8))
        return self.post.aplicar(f, i, max(0.0, fundido))

    def imagen(self, t):
        return Image.fromarray(self.cuadro(int(t * self.fps), t))

    def hoja(self, salida, ancho=360):
        """Hoja de contacto: un cuadro representativo por escena (para revisar antes de renderizar)."""
        ims = []
        for i in range(len(self.esc)):
            tl = min(self.durs[i] - 0.25, max(2.4, self.durs[i] * 0.72))
            im = self.imagen(self.inicios[i] + tl)
            ims.append(im.resize((ancho, int(ancho * self.H / self.W)), Image.LANCZOS))
        cols = min(len(ims), 4 if self.H > self.W else 3)
        filas = (len(ims) + cols - 1) // cols
        w, h, s = ims[0].width, ims[0].height, 12
        hoja = Image.new("RGB", (cols * w + (cols + 1) * s, filas * h + (filas + 1) * s), (18, 18, 20))
        for j, im in enumerate(ims):
            hoja.paste(im, (s + (j % cols) * (w + s), s + (j // cols) * (h + s)))
        hoja.save(salida)
        return salida

    # ------------------------------------------------------------ render
    def render(self, salida, procesos=None, crf=19):
        global _P
        if not self.listo:
            self.preparar()
        os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.W}x{self.H}",
               "-r", str(self.fps), "-i", "-"]
        if self.wav:
            cmd += ["-i", self.wav, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-maxrate", "9M", "-bufsize", "18M",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", "-t", f"{self.total:.3f}", salida]
        ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        procesos = procesos or max(1, (os.cpu_count() or 2))
        t0 = time.time()
        _P = self
        try:
            if procesos > 1 and "fork" in mp.get_all_start_methods():
                with mp.get_context("fork").Pool(procesos) as pool:
                    for i, datos in enumerate(pool.imap(_trabajo, range(self.n), chunksize=2)):
                        ff.stdin.write(datos)
                        self._progreso(i, t0)
            else:
                for i in range(self.n):
                    ff.stdin.write(self.cuadro(i).tobytes())
                    self._progreso(i, t0)
        finally:
            ff.stdin.close()
            cod = ff.wait()
        if cod != 0:
            raise RuntimeError("ffmpeg falló al codificar el video")
        self.log(f"\r  listo en {time.time() - t0:.0f} s → {salida}            ")
        return salida

    def _progreso(self, i, t0):
        paso = 50 if sys.stdout.isatty() else 5
        if i % max(1, self.n // paso) == 0 or i == self.n - 1:
            pct = (i + 1) / self.n
            resta = (time.time() - t0) / pct * (1 - pct)
            fin = "" if sys.stdout.isatty() else "\n"
            sys.stdout.write(f"\r  renderizando {pct * 100:3.0f}%  (faltan ~{resta:.0f} s) {fin}")
            sys.stdout.flush()

    def cerrar(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


_P = None


def _trabajo(i):
    return _P.cuadro(i).tobytes()
