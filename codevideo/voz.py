"""Narración con voz sintética 100 % local (Piper). Sin internet ni cuentas al renderizar."""
import hashlib
import io
import os
import re
import sys
import tarfile
import urllib.request
import wave

import numpy as np

SR = 22050
VOCES = {
    # nombre: (carpeta del modelo, descripción, licencia del dataset)
    "daniela": ("es_AR-daniela-high", "Español rioplatense, femenina", "CC BY-SA 4.0 (OpenSLR 61)"),
    "claude": ("es_MX-claude-high", "Español mexicano", "Apache-2.0"),
    "davefx": ("es_ES-davefx-medium", "Español de España, masculina", "CC0"),
}
URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-{}.tar.bz2"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dirs_voces():
    ds = []
    if os.environ.get("CODEVIDEO_VOCES"):
        ds.append(os.environ["CODEVIDEO_VOCES"])
    ds += [os.path.join(RAIZ, "voces"), os.path.join(os.path.expanduser("~"), ".codevideo", "voces")]
    return ds


def buscar_modelo(nombre):
    if nombre.endswith(".onnx") and os.path.exists(nombre):
        return nombre
    archivo = VOCES.get(nombre, (nombre,))[0] + ".onnx"
    for d in dirs_voces():
        p = os.path.join(d, archivo)
        if os.path.exists(p) and os.path.exists(p + ".json"):
            return p
    return None


def descargar(nombres, destino=None):
    destino = destino or os.path.join(RAIZ, "voces")
    os.makedirs(destino, exist_ok=True)
    for n in nombres:
        if n not in VOCES:
            print(f"  voz desconocida: {n}. Disponibles: {', '.join(VOCES)}")
            continue
        modelo = VOCES[n][0]
        if os.path.exists(os.path.join(destino, modelo + ".onnx")):
            print(f"  {n}: ya instalada")
            continue
        print(f"  {n}: descargando {modelo} …", flush=True)
        with urllib.request.urlopen(URL.format(modelo)) as r:
            datos = r.read()
        with tarfile.open(fileobj=io.BytesIO(datos), mode="r:bz2") as tf:
            for m in tf.getmembers():
                base = os.path.basename(m.name)
                if m.isfile() and (base.endswith(".onnx") or base.endswith(".onnx.json") or base == "MODEL_CARD"):
                    salida = base if base != "MODEL_CARD" else modelo + ".MODEL_CARD"
                    with open(os.path.join(destino, salida), "wb") as f:
                        f.write(tf.extractfile(m).read())
        print(f"  {n}: lista ({VOCES[n][1]}; licencia {VOCES[n][2]})")


def oraciones(texto):
    partes = re.split(r"(?<=[.!?…])\s+", texto.strip())
    return [p for p in partes if p.strip()]


def _palabras(oracion, t0, t1):
    """Reparte el tiempo de la oración entre sus palabras según su largo (aprox. para subtítulos)."""
    ws = oracion.split()
    pesos = [len(re.sub(r"\W", "", w)) + 1.5 + (2.5 if w[-1] in ",;:" else 0) for w in ws]
    tot = sum(pesos)
    out, t = [], t0
    for w, p in zip(ws, pesos):
        d = (t1 - t0) * p / tot
        out.append((w, t, t + d))
        t += d
    return out


class Narrador:
    def __init__(self, cfg, cache):
        self.cfg = cfg
        self.cache = cache
        self.voz = None
        self.ok = False
        if not cfg.get("activa", True):
            return
        modelo = buscar_modelo(cfg["modelo"])
        if not modelo:
            print(f"  ! No encontré la voz '{cfg['modelo']}'. Instalala con:  python -m codevideo voces {cfg['modelo']}\n"
                  f"    Sigo sin narración.", file=sys.stderr)
            return
        try:
            from piper import PiperVoice, SynthesisConfig
        except ImportError:
            print("  ! Falta el motor de voz. Instalalo con:  pip install piper-tts\n    Sigo sin narración.", file=sys.stderr)
            return
        self.modelo = modelo
        self._PiperVoice, self._Cfg = PiperVoice, SynthesisConfig
        self.ok = True
        os.makedirs(cache, exist_ok=True)

    def _sintetizar(self, texto):
        vel = float(self.cfg.get("velocidad", 1.0))
        clave = hashlib.sha1(f"{os.path.basename(self.modelo)}|{vel}|{texto}".encode()).hexdigest()[:20]
        ruta = os.path.join(self.cache, clave + ".wav")
        if not os.path.exists(ruta):
            if self.voz is None:
                self.voz = self._PiperVoice.load(self.modelo)
            sc = self._Cfg(length_scale=1.0 / vel, noise_scale=0.6, noise_w_scale=0.8)
            with wave.open(ruta, "wb") as w:
                self.voz.synthesize_wav(texto, w, syn_config=sc)
        with wave.open(ruta, "rb") as w:
            sr = w.getframerate()
            a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        if sr != SR:
            a = np.interp(np.arange(0, len(a), sr / SR), np.arange(len(a)), a).astype(np.float32)
        # recortar silencios de los extremos
        idx = np.nonzero(np.abs(a) > 0.012)[0]
        if len(idx):
            a = a[max(0, idx[0] - 400):idx[-1] + 1800]
        return a

    def narrar(self, texto):
        """Devuelve (audio mono float32 a SR, [(palabra, t_ini, t_fin)])."""
        if not self.ok or not texto or not texto.strip():
            return np.zeros(0, np.float32), []
        pausa = float(self.cfg.get("pausa", 0.32))
        trozos, palabras, t = [], [], 0.0
        ors = oraciones(texto)
        for i, o in enumerate(ors):
            a = self._sintetizar(o)
            d = len(a) / SR
            palabras += _palabras(o, t, t + max(0.1, d - 0.08))
            trozos.append(a)
            t += d
            if i < len(ors) - 1:
                trozos.append(np.zeros(int(pausa * SR), np.float32))
                t += pausa
        return np.concatenate(trozos), palabras
