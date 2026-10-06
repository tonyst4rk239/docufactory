"""Docu Factory — CLI principal.

Uso:
  python make_video.py doctor                       # verifica FFmpeg, claves y dependencias
  python make_video.py nuevo "tema" [--minutos 8.5] # investiga y escribe el guion, luego PAUSA para revisión
  python make_video.py continuar <slug>             # tras revisar guion.json: voz, b-roll, render…
  python make_video.py estado <slug>                # muestra el estado de cada etapa
"""
from __future__ import annotations

import argparse
import sys

from src import config
from src.estado import Proyecto

sys.stdout.reconfigure(encoding="utf-8")


def cmd_doctor(_args) -> int:
    ok = True
    print("== Herramientas ==")
    for b in ("ffmpeg", "ffprobe"):
        ruta = config.ffmpeg_bin(b)
        print(f"  {'✅' if ruta else '❌'} {b}: {ruta or 'no encontrado'}")
        ok &= bool(ruta)
    print("== Claves (.env) ==")
    for nombre, req in [("GEMINI_API_KEY", True), ("GOOGLE_TTS_API_KEY", True),
                        ("PEXELS_API_KEY", True), ("PIXABAY_API_KEY", True), ("SERPAPI_KEY", False)]:
        val = getattr(config, nombre)
        marca = "✅" if val else ("❌" if req else "➖ (opcional)")
        print(f"  {marca} {nombre}")
        ok &= bool(val) or not req
    print("== Assets de marca ==")
    poses = [p for p in config.POSES if (config.HOST_DIR / f"{p}_cerrada.png").exists()]
    print(f"  Host: {len(poses)}/{len(config.POSES)} poses listas")
    n_sfx = sum(1 for _ in config.SFX_DIR.glob("*/*.*"))
    n_mus = sum(1 for _ in config.MUSIC_DIR.glob("*/*.*"))
    print(f"  SFX: {n_sfx} archivos | Música: {n_mus} pistas")
    print("\nTodo listo ✅" if ok else "\nFaltan elementos obligatorios ❌")
    return 0 if ok else 1


def cmd_nuevo(args) -> int:
    from src.guion import etapa_guion

    p = Proyecto.crear(args.tema, args.minutos, args.lang)
    print(f"📁 Proyecto: {p.carpeta}")
    avisos = etapa_guion(p)
    for a in avisos:
        print(f"  ⚠️  {a}")
    print(
        "\n⏸️  CHECKPOINT: revisa y edita a tu gusto:\n"
        f"   {p.ruta('guion', 'guion_montaje.txt')}  (lectura rápida)\n"
        f"   {p.ruta('guion', 'guion.json')}         (lo que se usa para producir)\n"
        f"   {p.ruta('guion', 'fuentes.md')}\n"
        f"Cuando esté bien:  python make_video.py continuar {p.datos['slug']}"
    )
    return 0


def cmd_continuar(args) -> int:
    p = Proyecto.cargar(args.slug)
    if p.estado("guion") == "pendiente":
        print("El guion no existe todavía. Usa 'nuevo'.")
        return 1
    p.marcar("guion", "ok")
    pendientes = [e for e, s in p.datos["etapas"].items() if s != "ok"]
    print(f"Etapas pendientes: {', '.join(pendientes)}")
    print("🚧 Las etapas de voz, B-roll y render se implementan en los siguientes pasos del roadmap.")
    return 0


def cmd_estado(args) -> int:
    p = Proyecto.cargar(args.slug)
    print(f"{p.tema}  ({p.carpeta})")
    for e, s in p.datos["etapas"].items():
        icono = {"ok": "✅", "revisar": "⏸️", "pendiente": "⬜", "error": "❌"}.get(s, "•")
        print(f"  {icono} {e}: {s}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="make_video", description="Docu Factory")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    n = sub.add_parser("nuevo")
    n.add_argument("tema")
    n.add_argument("--minutos", type=float, default=config.MINUTOS_DEFAULT)
    n.add_argument("--lang", default="es")
    n.set_defaults(fn=cmd_nuevo)

    c = sub.add_parser("continuar")
    c.add_argument("slug")
    c.set_defaults(fn=cmd_continuar)

    s = sub.add_parser("estado")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_estado)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
