"""Música y efectos generados por síntesis (numpy). Sin samples ni librerías de terceros:
todo lo que suena se calcula acá, así que no hay licencias ni suscripciones de por medio."""
import numpy as np

SR = 44100
TAU = 2 * np.pi
INTERVALOS = {"M": [0, 4, 7], "m": [0, 3, 7], "M7": [0, 4, 7, 11], "m7": [0, 3, 7, 10]}
MODOS = {
    # acordes: (nota MIDI fundamental, tipo) · pluck: notas por compás · pulso/golpe: percusión grave
    "ambient": dict(bpm=60, acordes=[(45, "m"), (41, "M"), (48, "M"), (43, "M")], pad=1.0, bajo=0.55, pluck=2, pulso=0, golpe=0),
    "esperanza": dict(bpm=72, acordes=[(48, "M"), (43, "M"), (45, "m"), (41, "M")], pad=0.8, bajo=0.55, pluck=8, pulso=0, golpe=0),
    "intimo": dict(bpm=56, acordes=[(41, "M7"), (45, "m7"), (38, "m7"), (48, "M7")], pad=0.45, bajo=0.3, pluck=4, pulso=0, golpe=0),
    "tension": dict(bpm=80, acordes=[(38, "m"), (46, "M"), (43, "m"), (45, "M")], pad=0.85, bajo=0.8, pluck=0, pulso=1, golpe=0),
    "epico": dict(bpm=84, acordes=[(38, "m"), (46, "M"), (41, "M"), (48, "M")], pad=1.0, bajo=0.8, pluck=4, pulso=1, golpe=1),
}


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _sumar(buf, ini, sig):
    ini = int(ini)
    if ini < 0:
        sig, ini = sig[-ini:], 0
    n = min(len(sig), len(buf) - ini)
    if n > 0:
        buf[ini:ini + n] += sig[:n]


def _filtro(x, lo=None, hi=None):
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    f[0] = 1e-6
    m = np.ones_like(f)
    if lo:
        m *= 1 / (1 + (lo / f) ** 4)
    if hi:
        m *= 1 / (1 + (f / hi) ** 4)
    if X.ndim == 2:
        m = m[:, None]
    return np.fft.irfft(X * m, len(x), axis=0).astype(np.float32)


def _env(n, ataque, cola):
    e = np.ones(n, np.float32)
    a, c = min(int(ataque * SR), n // 2), min(int(cola * SR), n // 2)
    if a:
        e[:a] = np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    if c:
        e[-c:] = np.cos(np.linspace(0, np.pi / 2, c)) ** 2
    return e


def _pad(f, dur, rng):
    n = int((dur + 2.2) * SR)
    t = np.arange(n, dtype=np.float32) / SR
    lados = []
    for det in (-1, 1):
        fd = f * 2 ** (det * 5 / 1200)
        s = np.zeros(n, np.float32)
        for h in range(1, 6):
            s += np.sin(TAU * fd * h * t + rng.uniform(0, TAU)).astype(np.float32) / h ** 1.7
        lados.append(s)
    trem = 1 + 0.14 * np.sin(TAU * rng.uniform(0.12, 0.3) * t + rng.uniform(0, TAU))
    e = _env(n, min(1.6, 0.4 * dur), 2.2) * trem
    L, R = lados
    return np.stack([(0.8 * L + 0.2 * R) * e, (0.2 * L + 0.8 * R) * e], 1).astype(np.float32)


def _pluck(f, vel, pan):
    n = int(3.2 * SR)
    t = np.arange(n, dtype=np.float32) / SR
    s = np.zeros(n, np.float32)
    for h in range(1, 7):
        s += np.sin(TAU * f * h * (1 + 0.0004 * h * h) * t) * np.exp(-t * (1.1 + 0.9 * h)) / h ** 1.5
    s[:180] *= np.linspace(0, 1, 180)
    s *= vel
    return np.stack([s * (1 - pan), s * pan], 1).astype(np.float32)


def _bajo(f, dur):
    n = int((dur + 1.0) * SR)
    t = np.arange(n, dtype=np.float32) / SR
    s = (np.sin(TAU * f * t) + 0.28 * np.sin(TAU * 2 * f * t)) * _env(n, 0.35, 1.0)
    return np.stack([s, s], 1).astype(np.float32)


def _golpe(fuerza=1.0, rng=None):
    n = int(1.8 * SR)
    t = np.arange(n, dtype=np.float32) / SR
    fr = 38 + 36 * np.exp(-t * 9)
    s = np.sin(TAU * np.cumsum(fr) / SR) * np.exp(-t * 3.0)
    if rng is not None:
        r = _filtro(rng.standard_normal(n).astype(np.float32), hi=320) * np.exp(-t * 8) * 0.9
        s = s + r
    s[:60] *= np.linspace(0, 1, 60)
    s *= fuerza
    return np.stack([s, s], 1).astype(np.float32)


def _soplo(rng, fuerza=1.0):
    """Barrido de aire que llega a su pico justo en el corte."""
    n = int(1.1 * SR)
    t = np.arange(n, dtype=np.float32) / SR
    r = _filtro(rng.standard_normal(n).astype(np.float32), lo=350, hi=4200)
    pico = 0.62
    e = np.where(t < pico, (t / pico) ** 2.6, np.exp(-(t - pico) * 7))
    r = r / (np.abs(r).max() + 1e-9) * e * fuerza
    pan = np.clip(t / 1.1, 0, 1)
    return np.stack([r * (1 - 0.6 * pan), r * (0.4 + 0.6 * pan)], 1).astype(np.float32), int(pico * SR)


def _reverb(x, rng, mezcla=0.38, largo=2.8):
    n = int(largo * SR)
    t = np.arange(n, dtype=np.float32) / SR
    ir = rng.standard_normal((n, 2)).astype(np.float32) * np.exp(-t * 2.3)[:, None]
    ir = _filtro(ir, lo=150, hi=4500)
    ir /= np.sqrt((ir ** 2).sum(0)) + 1e-9
    N = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, N, axis=0) * np.fft.rfft(ir, N, axis=0), N, axis=0)[:len(x)]
    return (x * (1 - mezcla * 0.4) + y.astype(np.float32) * mezcla).astype(np.float32)


def generar(total, tipo="ambient", semilla=7, cortes=(), efectos=True):
    """Devuelve (musica, efectos): dos pistas estéreo float32 de `total` segundos."""
    m = MODOS[tipo]
    rng = np.random.default_rng(semilla)
    n = int(total * SR)
    buf = np.zeros((n + 4 * SR, 2), np.float32)
    perc = np.zeros_like(buf)
    pulso = 60.0 / m["bpm"]
    compas = 4 * pulso
    k, t = 0, 0.0
    while t < total + 1:
        raiz, tipo_ac = m["acordes"][k % len(m["acordes"])]
        ints = INTERVALOS[tipo_ac]
        i0 = t * SR
        notas = [raiz] + [raiz + 12 + i for i in ints] + [raiz + 24]
        pesos = [0.7] + [0.55] * len(ints) + [0.22]
        for nota, p in zip(notas, pesos):
            _sumar(buf, i0, _pad(hz(nota), compas, rng) * (p * m["pad"] * 0.16))
        fb = hz(raiz - 12 if raiz > 43 else raiz)
        _sumar(buf, i0, _bajo(fb, compas) * (m["bajo"] * 0.3))
        if m["pluck"]:
            paso = compas / m["pluck"]
            tonos = [raiz + 24 + i for i in ints] + [raiz + 36, raiz + 36 + ints[1]]
            for j in range(m["pluck"]):
                if m["pluck"] <= 2 and rng.random() < 0.25:
                    continue
                nota = tonos[j % len(tonos)] if m["pluck"] >= 8 else int(rng.choice(tonos))
                vel = rng.uniform(0.5, 1.0) * (1.0 if j % 2 == 0 else 0.7)
                desv = rng.uniform(-0.012, 0.012)
                _sumar(buf, (t + j * paso + desv) * SR, _pluck(hz(nota), vel * 0.11, rng.uniform(0.25, 0.75)))
        if m["pulso"]:
            nn = int(0.32 * SR)
            tt = np.arange(nn, dtype=np.float32) / SR
            for j in range(8):
                amp = 0.42 if j % 2 == 0 else 0.16
                s = np.sin(TAU * fb * 2 * tt) * np.exp(-tt * 15) * amp
                _sumar(perc, (t + j * pulso / 2) * SR, np.stack([s, s], 1).astype(np.float32))
        if m["golpe"] and k % 2 == 0:
            _sumar(perc, i0, _golpe(0.55, rng))
        t += compas
        k += 1
    buf = _reverb(buf[:n + 2 * SR], rng)[:n] + perc[:n] * 0.8
    tt = np.arange(n, dtype=np.float32) / SR
    arco = 0.72 + 0.28 * np.clip(tt / max(1.0, 0.7 * total), 0, 1)
    arco *= np.clip(tt / 1.5, 0, 1) * np.clip((total - tt) / 3.0, 0, 1) ** 1.5
    buf *= arco[:, None]
    buf *= 0.7 / (np.abs(buf).max() + 1e-9)

    fx = np.zeros((n, 2), np.float32)
    if efectos:
        k_fx = 0.55 if tipo == "intimo" else 1.0
        _sumar(fx, 0.05 * SR, _golpe(0.5 * k_fx, rng))
        for c in cortes:
            s, pico = _soplo(rng, 0.2 * k_fx)
            _sumar(fx, c * SR - pico, s)
            _sumar(fx, c * SR, _golpe(0.34 * k_fx, rng))
        fx = _reverb(fx, rng, mezcla=0.25, largo=1.8)
        fx *= np.clip((total - tt) / 1.0, 0, 1)[:, None]
    return buf, fx
