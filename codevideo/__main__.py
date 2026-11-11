"""codevideo — generador de reels y publicidades con look de cine, 100 % local.

  python -m codevideo render guiones/demo.json          → salida/demo.mp4
  python -m codevideo render guiones/demo.json --borrador   (rápido, media resolución)
  python -m codevideo hoja   guiones/demo.json          → una imagen con un cuadro por escena
  python -m codevideo cuadro guiones/demo.json -t 3.5   → un cuadro suelto
  python -m codevideo nuevo  mi-reel                    → guiones/mi-reel.json desde la plantilla
  python -m codevideo voces  daniela                    → instala una voz (una sola vez)
  python -m codevideo opciones                          → estilos, formatos, tipos de escena…
"""
import argparse
import os
import shutil
import sys

from . import guion as G
from . import voz

RAIZ = voz.RAIZ


def _salida(args, ext):
    if args.salida:
        return args.salida
    nombre = os.path.splitext(os.path.basename(args.guion))[0]
    if getattr(args, "borrador", False):
        nombre += "-borrador"
    return os.path.join(RAIZ, "salida", nombre + ext)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="codevideo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="genera el video MP4")
    r.add_argument("guion")
    r.add_argument("-o", "--salida")
    r.add_argument("--borrador", action="store_true", help="media resolución, para revisar rápido")
    r.add_argument("--procesos", type=int)
    h = sub.add_parser("hoja", help="hoja de contacto: un cuadro por escena")
    h.add_argument("guion")
    h.add_argument("-o", "--salida")
    c = sub.add_parser("cuadro", help="exporta un cuadro en el segundo indicado")
    c.add_argument("guion")
    c.add_argument("-t", type=float, default=2.0)
    c.add_argument("-o", "--salida")
    n = sub.add_parser("nuevo", help="crea un guion a partir de la plantilla")
    n.add_argument("nombre")
    v = sub.add_parser("voces", help="instala voces para la narración")
    v.add_argument("nombres", nargs="*")
    sub.add_parser("opciones", help="lista estilos, formatos y tipos disponibles")
    args = ap.parse_args(argv)

    if args.cmd == "opciones":
        from .fondos import MOVIMIENTOS
        print("formatos:     ", ", ".join(f"{k} {v[0]}x{v[1]}" for k, v in G.FORMATOS.items()))
        print("estilos:      ", ", ".join(G.ESTILOS))
        print("tipografías:  ", ", ".join(G.TIPOGRAFIAS))
        print("escenas:      ", ", ".join(G.TIPOS_ESCENA))
        print("transiciones: ", ", ".join(G.TRANSICIONES))
        print("fondos:        aurora, gradiente, color, imagen, video")
        print("movimientos:   auto,", ", ".join(MOVIMIENTOS))
        print("música:       ", ", ".join(G.MUSICAS), "(o un archivo propio)")
        print("voces:        ", ", ".join(f"{k} ({d[1]})" for k, d in voz.VOCES.items()))
        return 0
    if args.cmd == "voces":
        if not args.nombres:
            for k, d in voz.VOCES.items():
                print(f"  {k:<8} {d[1]:<32} licencia: {d[2]:<28} {'instalada' if voz.buscar_modelo(k) else 'no instalada'}")
            return 0
        voz.descargar(args.nombres)
        return 0
    if args.cmd == "nuevo":
        destino = os.path.join(RAIZ, "guiones", args.nombre + ".json")
        if os.path.exists(destino):
            print(f"Ya existe {destino}")
            return 1
        shutil.copy(os.path.join(RAIZ, "guiones", "plantilla.json"), destino)
        print(f"Creado {destino}. Editalo y después:  python -m codevideo render {os.path.relpath(destino)}")
        return 0

    from .render import Proyecto
    try:
        p = Proyecto(args.guion, borrador=getattr(args, "borrador", False))
    except G.ErrorGuion as e:
        print(f"Error en el guion: {e}", file=sys.stderr)
        return 2
    try:
        if args.cmd == "render":
            p.preparar()
            p.resumen()
            p.render(_salida(args, ".mp4"), procesos=args.procesos)
        else:
            p.preparar(con_audio=False)
            if args.cmd == "hoja":
                p.resumen()
                out = _salida(args, "-hoja.png")
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                print("  →", p.hoja(out))
            else:
                out = _salida(args, f"-{args.t:.1f}s.png")
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                p.imagen(args.t).save(out)
                print("  →", out)
    finally:
        p.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
