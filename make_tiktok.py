"""Docu Factory — CLI para producción automática de videos en TikTok / Shorts / Reels (9:16).
Duración optimizada para 30 segundos, retención extrema, avatar en esquina inferior y bucle continuo.

Uso:
  python make_tiktok.py auto "tema" [--segundos 30]
  python make_tiktok.py nuevo "tema" [--segundos 30]
  python make_tiktok.py continuar <slug>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src import config
from src.estado import Proyecto
from src_tiktok.guion_tt import generar_guion_tiktok, GuionTikTok
from src_tiktok.voz_tt import etapa_voz_tiktok
from src_tiktok.broll_tt import etapa_broll_tiktok
from src_tiktok.render_tt import etapa_render_tiktok

sys.stdout.reconfigure(encoding="utf-8")


def cmd_nuevo(args) -> int:
    p = Proyecto.crear(args.tema, minutos=(args.segundos / 60.0), lang="es")
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
    video_final = etapa_render_tiktok(p, guion, duraciones)

    print("\n" + "=" * 65)
    print("🏆 ¡VIDEO VERTICAL DE TIKTOK TERMINADO CON ÉXITO!")
    print(f"📱 Archivo Final (9:16): {video_final}")
    print("=" * 65)

    if getattr(args, "publicar", False):
        print("\n🚀 Iniciando subida automática multi-plataforma...")
        import subprocess
        cmd_sub = [
            sys.executable, "subir_video.py", str(video_final),
            "--titulo", guion.titulo,
            "--texto", f"{guion.hook}\n\n#fyp #parati #viral #codigoocultotv #Shorts"
        ]
        subprocess.run(cmd_sub)

    return 0


def cmd_auto(args) -> int:
    cmd_nuevo(args)
    slug = config.slugify(args.tema)
    args.slug = slug
    return cmd_continuar(args)


def main():
    parser = argparse.ArgumentParser(description="Motor de videos verticales para TikTok / Shorts.")
    subs = parser.add_subparsers(dest="comando")

    p_nuevo = subs.add_parser("nuevo", help="Crea guion vertical")
    p_nuevo.add_argument("tema", help="Tema del video")
    p_nuevo.add_argument("--segundos", type=int, default=30, help="Duración en segundos (default: 30)")
    p_nuevo.set_defaults(func=cmd_nuevo)

    p_cont = subs.add_parser("continuar", help="Renderiza proyecto existente")
    p_cont.add_argument("slug", help="Slug del proyecto")
    p_cont.add_argument("--publicar", action="store_true", help="Sube automáticamente a redes tras terminar")
    p_cont.set_defaults(func=cmd_continuar)

    p_auto = subs.add_parser("auto", help="Genera y renderiza sin pausas")
    p_auto.add_argument("tema", help="Tema del video")
    p_auto.add_argument("--segundos", type=int, default=30, help="Duración en segundos (default: 30)")
    p_auto.add_argument("--publicar", action="store_true", help="Sube automáticamente a redes tras terminar")
    p_auto.set_defaults(func=cmd_auto)

    args = parser.parse_args()
    if not args.comando:
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
