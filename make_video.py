"""Docu Factory — CLI principal con orquestación completa end-to-end.

Comandos:
  python make_video.py doctor                          # verifica entorno y claves
  python make_video.py nuevo "tema" [--minutos 1.0]    # crea guion y hace pausa para revisión
  python make_video.py continuar <slug>                # corre voz, b-roll, render y empaquetado
  python make_video.py auto "tema" [--minutos 1.0]     # pipeline continuo sin pausas
  python make_video.py estado <slug>                   # ver progreso del proyecto
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src import config
from src.estado import Proyecto

sys.stdout.reconfigure(encoding="utf-8")


def cmd_doctor(_args) -> int:
    ok = True
    print("== Herramientas del Sistema ==")
    for b in ("ffmpeg", "ffprobe"):
        ruta = config.ffmpeg_bin(b)
        print(f"  {'✅' if ruta else '❌'} {b}: {ruta or 'no encontrado'}")
        ok &= bool(ruta)
        
    print("\n== Claves y APIs (.env) ==")
    for nombre, req in [
        ("GEMINI_API_KEY", True),
        ("PIXABAY_API_KEY", True),
        ("PEXELS_API_KEY", False),
        ("GOOGLE_TTS_API_KEY", False),
    ]:
        val = getattr(config, nombre)
        marca = "✅" if val else ("❌" if req else "➖ (opcional / fallback activo)")
        print(f"  {marca} {nombre}")
        ok &= bool(val) or not req
        
    print("\n== Identidad de Marca ==")
    from src.host_anim import asegurar_assets_host_base
    asegurar_assets_host_base()
    poses = [p for p in config.POSES if (config.HOST_DIR / f"{p}_cerrada.png").exists()]
    print(f"  Host: {len(poses)}/{len(config.POSES)} poses generadas y disponibles ✅")
    
    print("\nTodo listo para operar ✅" if ok else "\nFaltan elementos obligatorios ❌")
    return 0 if ok else 1


def cmd_nuevo(args) -> int:
    from src.guion import etapa_guion

    p = Proyecto.crear(args.tema, args.minutos, args.lang)
    print(f"📁 Proyecto inicializado en: {p.carpeta}")
    avisos = etapa_guion(p)
    for a in avisos:
        print(f"  ⚠️  {a}")
    print(
        "\n⏸️  CHECKPOINT EDITORIAL: Revisa el guion en:\n"
        f"   {p.ruta('guion', 'guion_montaje.txt')}  (Lectura rápida)\n"
        f"   {p.ruta('guion', 'guion.json')}         (Estructura editable)\n"
        f"\nPara continuar al render: python make_video.py continuar {p.datos['slug']}"
    )
    return 0


def cmd_continuar(args) -> int:
    from src.voz import etapa_voz
    from src.broll import etapa_broll
    from src.render import etapa_render
    from src.subtitulos import generar_srt
    from src.publicacion import etapa_publicacion

    p = Proyecto.cargar(args.slug)
    print(f"\n🚀 Procesando proyecto: '{p.tema}' ({p.datos['slug']})\n")

    # 1. Voz
    duraciones = etapa_voz(p)

    # 2. B-Roll
    etapa_broll(p)

    # 3. Subtítulos
    generar_srt(p, duraciones)

    # 4. Render 16:9
    video_final = etapa_render(p, duraciones)

    # 5. Publicación
    etapa_publicacion(p, duraciones)

    print("\n" + "=" * 60)
    print("🏆 ¡PRODUCCIÓN COMPLETADA CON ÉXITO!")
    print(f"📹 Video final: {video_final}")
    print(f"📂 Carpeta del proyecto: {p.carpeta}")
    print("=" * 60)
    return 0


def cmd_auto(args) -> int:
    cmd_nuevo(args)
    slug = config.slugify(args.tema)
    args.slug = slug
    return cmd_continuar(args)


def cmd_estado(args) -> int:
    p = Proyecto.cargar(args.slug)
    print(f"Tema: {p.tema}\nUbicación: {p.carpeta}")
    for e, s in p.datos["etapas"].items():
        icono = {"ok": "✅", "revisar": "⏸️", "pendiente": "⬜", "error": "❌"}.get(s, "•")
        print(f"  {icono} {e:12s}: {s}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="make_video", description="Docu Factory - Automatización de Video")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    n = sub.add_parser("nuevo")
    n.add_argument("tema")
    n.add_argument("--minutos", type=float, default=1.0)
    n.add_argument("--lang", default="es")
    n.set_defaults(fn=cmd_nuevo)

    c = sub.add_parser("continuar")
    c.add_argument("slug")
    c.set_defaults(fn=cmd_continuar)

    a = sub.add_parser("auto")
    a.add_argument("tema")
    a.add_argument("--minutos", type=float, default=1.0)
    a.add_argument("--lang", default="es")
    a.set_defaults(fn=cmd_auto)

    s = sub.add_parser("estado")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_estado)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
