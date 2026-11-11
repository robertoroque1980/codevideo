"""Mezcla final: voz procesada + música (generada o propia) con atenuación automática bajo la voz."""
import os
import subprocess
import wave

import numpy as np

from . import musica
from .voz import SR as SR_VOZ

SR = musica.SR
CADENA_VOZ = ("highpass=f=75,equalizer=f=180:t=q:w=1:g=1.5,equalizer=f=3200:t=q:w=1.2:g=2,"
              "acompressor=threshold=-20dB:ratio=3:attack=8:release=160:makeup=3,"
              "aecho=0.8:0.6:38|71:0.10|0.06")


def _guardar(ruta, a, sr):
    a = np.clip(a, -1, 1)
    with wave.open(ruta, "wb") as w:
        w.setnchannels(1 if a.ndim == 1 else a.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((a * 32767).astype(np.int16).tobytes())


def _decodificar(args):
    crudo = subprocess.run(["ffmpeg", "-v", "error", *args, "-f", "s16le", "-ac", "2", "-ar", str(SR), "-"],
                           check=True, capture_output=True).stdout
    return np.frombuffer(crudo, np.int16).reshape(-1, 2).astype(np.float32) / 32768


def _ajustar(a, n):
    if len(a) >= n:
        return a[:n]
    return np.concatenate([a, np.zeros((n - len(a),) + a.shape[1:], np.float32)])


def _media(x, ventana):
    v = max(1, int(ventana))
    c = np.cumsum(np.concatenate([np.zeros(v, np.float32), x, np.zeros(v, np.float32)]).astype(np.float64))
    return ((c[v:] - c[:-v]) / v)[v // 2: v // 2 + len(x)].astype(np.float32)


def mezclar(total, voces, cfg_mus, cortes, tmp, salida):
    """voces: [(t_inicio, audio mono a SR_VOZ)]. Escribe `salida` (wav estéreo) y la devuelve."""
    n = int(total * SR)
    voz = np.zeros((n, 2), np.float32)
    hay_voz = any(len(a) for _, a in voces)
    if hay_voz:
        mono = np.zeros(int(total * SR_VOZ) + SR_VOZ, np.float32)
        for t0, a in voces:
            i = int(t0 * SR_VOZ)
            mono[i:i + len(a)] += a[:len(mono) - i]
        mono *= 0.85 / (np.abs(mono).max() + 1e-9)
        cruda = os.path.join(tmp, "voz_cruda.wav")
        _guardar(cruda, mono, SR_VOZ)
        voz = _ajustar(_decodificar(["-i", cruda, "-af", CADENA_VOZ]), n)
        voz *= 0.85 / (np.abs(voz).max() + 1e-9)

    mus = np.zeros((n, 2), np.float32)
    fx = np.zeros((n, 2), np.float32)
    if cfg_mus.get("activa", True):
        if cfg_mus.get("archivo"):
            a = _decodificar(["-i", cfg_mus["archivo"]])
            if len(a) == 0:
                raise RuntimeError(f"No pude leer la música: {cfg_mus['archivo']}")
            a = np.tile(a, (int(np.ceil(n / len(a))), 1))[:n]
            t = np.arange(n, dtype=np.float32) / SR
            a *= (np.clip(t / 1.0, 0, 1) * np.clip((total - t) / 2.5, 0, 1))[:, None]
            mus = a * (0.7 / (np.abs(a).max() + 1e-9))
        else:
            mus, fx = musica.generar(total, cfg_mus["tipo"], cfg_mus.get("semilla", 7), cortes, cfg_mus.get("efectos", True))
        vol = float(cfg_mus.get("volumen", 0.6))
        if hay_voz:
            env = _media(np.abs(voz).mean(1), 0.03 * SR)
            hablando = (env > 0.02).astype(np.float32)
            g = _media(_media(hablando, 0.35 * SR), 0.35 * SR)
            mus = mus * (vol * 0.62) * (1 - float(cfg_mus.get("atenuar", 0.6)) * g)[:, None]
            fx = fx * vol * (1 - 0.35 * g)[:, None]
        else:
            mus = mus * vol * 1.1
            fx = fx * vol
    mix = voz + mus + fx
    pico = np.abs(mix).max()
    if pico > 0.95:
        mix = np.tanh(mix / pico * 1.6) / np.tanh(1.6) * 0.95
    _guardar(salida, mix, SR)
    return salida
