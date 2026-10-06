"""Docu Factory — CLI principal con orquestación completa y doblaje humano.

Uso:
  python make_video.py doctor                          # verifica entorno y claves
  python make_video.py nuevo "tema" [--minutos 1.0]    # crea guion y guía de doblaje para teleprompter
  python make_video.py continuar <slug>                # corre voz, broll, stems y renders duales
  python make_video.py auto "tema" [--minutos 1.0]     # pipeline continuo sin pausas
  python make_video.py doblar <slug> --audio <wav>     # re-sincroniza con locución humana
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
    ]:
        val = getattr(config, nombre)
        marca = "✅" if val else ("❌" if req else "➖ (opcional / fallback activo)")
        print(f"  {marca} {nombre}")
        ok &= bool(val) or not req
        
    print("\n== Identidad de Marca ==")
    poses = [p for p in config.POSES if (config.HOST_DIR / f"{p}_cerrada.png").exists()]
    print(f"  Host Personalizado: {len(poses)}/{len(config.POSES)} poses activas ✅")
    
    n_sfx = sum(1 for _ in config.SFX_DIR.glob("*/*.*"))
    print(f"  SFX Disponibles: {n_sfx} sonidos (click, teclado, transicion, etc.) ✅")
    
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
        "\n⏸️  CHECKPOINT EDITORIAL & GUÍA DE DOBLAJE:\n"
        f"   📖 Guía para Teleprompter / Doblaje: {p.ruta('guion', 'guion_doblaje.md')}\n"
        f"   📝 Lectura rápida de montaje:        {p.ruta('guion', 'guion_montaje.txt')}\n"
        f"   ⚙️ Estructura técnica de escenas:   {p.ruta('guion', 'guion.json')}\n"
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

    # 1. Voz IA Masterizada
    duraciones = etapa_voz(p)

    # 2. B-Roll
    etapa_broll(p)

    # 3. Subtítulos
    generar_srt(p, duraciones)

    # 4. Render Dual (Stems + Video IA + Video Karaoke)
    salidas = etapa_render(p, duraciones)

    # 5. Publicación
    etapa_publicacion(p, duraciones)

    print("\n" + "=" * 65)
    print("🏆 ¡PRODUCCIÓN DUAL COMPLETADA CON ÉXITO!")
    print(f"🎙️ Stem Voz IA:          {salidas['voz_master']}")
    print(f"🎧 Stem Mezcla MDE:       {salidas['mde_master']}")
    print(f"📹 Video con Voz IA:      {salidas['video_con_voz']}")
    print(f"🎤 Video Clean / Karaoke: {salidas['video_sin_voz']}")
    print("=" * 65)
    return 0


def cmd_doblar(args) -> int:
    """Re-sincroniza el proyecto con un audio de voz humana proporcionado por el usuario."""
    from src.render import etapa_render
    from src.voz import obtener_duracion_wav

    p = Proyecto.cargar(args.slug)
    audio_humano = Path(args.audio)
    if not audio_humano.exists():
        print(f"❌ No se encontró el archivo de voz: {audio_humano}")
        return 1

    dur_humana = obtener_duracion_wav(audio_humano)
    print(f"🎙️ Importando voz humana: {audio_humano.name} ({dur_humana:.2f}s)...")

    # Mapear duraciones base desde el guion
    from src.guion import cargar_guion
    g = cargar_guion(p)
    # Distribuir proporcionalmente si es un solo track
    dur_esc = dur_humana / len(g.escenas)
    duraciones = {e.id: dur_esc for e in g.escenas}

    salidas = etapa_render(p, duraciones, voz_humana=audio_humano)
    print("\n" + "=" * 65)
    print("🎉 ¡VIDEO RE-SINCRONIZADO CON VOZ HUMANA!")
    print(f"📹 Video Final: {salidas['video_con_voz']}")
    print("=" * 65)
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

    d = sub.add_parser("doblar")
    d.add_argument("slug")
    d.add_argument("--audio", required=True, help="Ruta al archivo .wav con la voz humana")
    d.set_defaults(fn=cmd_doblar)

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
