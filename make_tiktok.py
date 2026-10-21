"""Docu Factory — CLI para producción automática de videos en TikTok / Shorts / Reels (9:16).
Duración optimizada para 30 segundos, retención extrema, avatar en esquina inferior y bucle continuo.

Uso:
  python make_tiktok.py importar <guion.json> [--auto] [--reusar]
  python make_tiktok.py auto "tema" [--segundos 30] [--reusar]
  python make_tiktok.py nuevo "tema" [--segundos 30] [--reusar]
  python make_tiktok.py continuar <slug>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src import config
from src.estado import Proyecto
from src_tiktok.guion_tt import generar_guion_tiktok, importar_guion_tiktok, GuionTikTok
from src_tiktok.voz_tt import etapa_voz_tiktok
from src_tiktok.broll_tt import etapa_broll_tiktok
from src_tiktok.render_tt import etapa_render_tiktok

sys.stdout.reconfigure(encoding="utf-8")


def cmd_importar(args) -> int:
    ruta_json = Path(args.guion_json)
    print(f"📥 Validando e importando guion vertical (9:16): {ruta_json}")
    try:
        p, guion, avisos = importar_guion_tiktok(
            ruta_json,
            reusar=getattr(args, "reusar", False),
        )
    except ValueError as e:
        print(f"\n❌ Error de validación en el guion JSON:\n{e}")
        return 1
    except Exception as e:
        print(f"\n❌ No se pudo importar el guion '{ruta_json}': {e}")
        return 1

    print(f"📱 Proyecto vertical inicializado en: {p.carpeta} (slug: {p.datos['slug']})")
    print(f"✅ Guion validado: '{guion.titulo}' ({len(guion.escenas)} micro-escenas)")
    for a in avisos:
        print(f"  ⚠️  {a}")
    print(
        "\n📖 Archivos generados:\n"
        f"   • Guía para Teleprompter / Doblaje: {p.ruta('guion', 'guion_doblaje.md')}\n"
        f"   • Lectura rápida de montaje:        {p.ruta('guion', 'guion_montaje.txt')}\n"
        f"   • Guion vertical TikTok:            {p.ruta('guion', 'guion_tiktok.json')}"
    )

    if getattr(args, "solo_guion", False):
        print(f"\n⏸️  Modo --solo-guion activo. Para continuar: python make_tiktok.py continuar {p.datos['slug']}")
        return 0

    args.slug = p.datos["slug"]
    return cmd_continuar(args)


def cmd_nuevo(args) -> int:
    if not config.GEMINI_API_KEY:
        print(
            "⚠️  GEMINI_API_KEY no está configurada (Gemini es opcional en v3).\n"
            "👉 Para crear y producir un Reel desde un archivo de guion externo (Pluma), usa:\n"
            "   python make_tiktok.py importar <guion.json> [--auto]"
        )
        return 1

    try:
        p = Proyecto.crear(args.tema, minutos=(args.segundos / 60.0), lang="es", reusar=getattr(args, "reusar", False))
    except TypeError:
        p = Proyecto.crear(args.tema, minutos=(args.segundos / 60.0), lang="es")
    args._ultimo_slug = p.datos["slug"]
    print(f"📱 Inicializando proyecto vertical en: {p.carpeta}")
    guion = generar_guion_tiktok(p, segundos=args.segundos)
    print(f"\n✅ Guion vertical generado exitosamente con Hook y Bucle Infinito:")
    print(f"   Hook inicial: \"{guion.hook}\"")
    print(f"   Bucle final:  \"{guion.bucle_loop_frase}\"")
    print(f"   Micro-escenas: {len(guion.escenas)} tomas rápidas.")
    print(f"\nPara renderizar: python make_tiktok.py continuar {p.datos['slug']}")
    return 0


def cmd_continuar(args) -> int:
    p = Proyecto.cargar(args.slug)
    p_guion = p.ruta("guion") / "guion_tiktok.json"
    if not p_guion.exists():
        print(f"❌ No se encontró guion de TikTok en: {p_guion}")
        return 1

    import json
    data = json.loads(p_guion.read_text(encoding="utf-8"))
    guion = GuionTikTok.model_validate(data)

    print(f"\n🚀 Renderizando video vertical TikTok: '{p.tema}' ({p.datos['slug']})\n")

    # 1. Voces aceleradas Edge-TTS (+12% rate)
    duraciones = etapa_voz_tiktok(p, guion)

    # 2. Descarga de clips verticales / adaptables
    etapa_broll_tiktok(p, guion, duraciones)

    # 3. Render 1080x1920 con Avatar en esquina y Subtítulos Hormozi
    resultado_render = etapa_render_tiktok(p, guion, duraciones)
    if isinstance(resultado_render, dict):
        video_con_voz = resultado_render.get("video_con_voz")
        video_sin_voz = resultado_render.get("video_sin_voz")
    else:
        video_con_voz = resultado_render
        video_sin_voz = None

    print("\n" + "=" * 65)
    print("🏆 ¡VIDEO VERTICAL DE TIKTOK TERMINADO CON ÉXITO!")
    print(f"📱 Video con Voz IA (9:16):    {video_con_voz}")
    if video_sin_voz:
        print(f"🎤 Video Clean / Sin Voz (9:16): {video_sin_voz}")
    print("=" * 65)

    if getattr(args, "publicar", False) and video_con_voz:
        print("\n🚀 Iniciando subida automática multi-plataforma...")
        import subprocess
        cmd_sub = [
            sys.executable, "subir_video.py", str(video_con_voz),
            "--titulo", guion.titulo,
            "--texto", f"{guion.hook}\n\n#fyp #parati #viral #codigoocultotv #Shorts"
        ]
        subprocess.run(cmd_sub)

    return 0


def cmd_auto(args) -> int:
    posible_json = Path(args.tema)
    if posible_json.suffix.lower() == ".json" and posible_json.exists():
        args.guion_json = str(posible_json)
        args.auto = True
        args.solo_guion = False
        return cmd_importar(args)

    rc = cmd_nuevo(args)
    if rc != 0:
        return rc
    args.slug = getattr(args, "_ultimo_slug", None) or config.slugify(args.tema)
    return cmd_continuar(args)


def main():
    parser = argparse.ArgumentParser(description="Motor de videos verticales para TikTok / Shorts.")
    subs = parser.add_subparsers(dest="comando")

    p_imp = subs.add_parser("importar", help="Valida e importa un guion JSON externo (Pluma) para 9:16")
    p_imp.add_argument("guion_json", help="Ruta al archivo .json del guion")
    p_imp.add_argument("--auto", action="store_true", help="Ejecuta todo el pipeline vertical de corrido")
    p_imp.add_argument("--solo-guion", action="store_true", help="Solo valida el JSON y genera guion_doblaje.md sin renderizar")
    p_imp.add_argument("--reusar", action="store_true", help="Reutiliza la carpeta de proyecto existente con el mismo slug base")
    p_imp.add_argument("--publicar", action="store_true", help="Sube automáticamente a redes tras terminar")
    p_imp.set_defaults(func=cmd_importar)

    p_nuevo = subs.add_parser("nuevo", help="Crea guion vertical")
    p_nuevo.add_argument("tema", help="Tema del video")
    p_nuevo.add_argument("--segundos", type=int, default=30, help="Duración en segundos (default: 30)")
    p_nuevo.add_argument("--reusar", action="store_true", help="Reutiliza la carpeta de proyecto existente con el mismo slug base")
    p_nuevo.set_defaults(func=cmd_nuevo)

    p_cont = subs.add_parser("continuar", help="Renderiza proyecto existente")
    p_cont.add_argument("slug", help="Slug del proyecto")
    p_cont.add_argument("--publicar", action="store_true", help="Sube automáticamente a redes tras terminar")
    p_cont.set_defaults(func=cmd_continuar)

    p_auto = subs.add_parser("auto", help="Genera y renderiza sin pausas")
    p_auto.add_argument("tema", help="Tema del video")
    p_auto.add_argument("--segundos", type=int, default=30, help="Duración en segundos (default: 30)")
    p_auto.add_argument("--reusar", action="store_true", help="Reutiliza la carpeta de proyecto existente con el mismo slug base")
    p_auto.add_argument("--publicar", action="store_true", help="Sube automáticamente a redes tras terminar")
    p_auto.set_defaults(func=cmd_auto)

    args = parser.parse_args()
    if not args.comando:
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
