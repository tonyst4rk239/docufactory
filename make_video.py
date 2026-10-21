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
    from src.edicion import cargar_config_edicion, listar_archivos_overlay
    from src.render import listar_archivos_audio, resolver_musica_mood, resolver_sfx_categoria

    ok = True
    print("== Herramientas del Sistema ==")
    for b in ("ffmpeg", "ffprobe"):
        ruta = config.ffmpeg_bin(b)
        print(f"  {'✅' if ruta else '❌'} {b}: {ruta or 'no encontrado'}")
        ok &= bool(ruta)

    print("\n== Claves, APIs y Cookies (.env) ==")
    for nombre, req in [
        ("GEMINI_API_KEY", True),
        ("PIXABAY_API_KEY", True),
        ("PEXELS_API_KEY", False),
        ("FREESOUND_API_KEY", False),
    ]:
        val = getattr(config, nombre)
        marca = "✅" if val else ("❌" if req else "➖ (opcional / fallback activo)")
        print(f"  {marca} {nombre}")
        ok &= bool(val) or not req

    if config.YTDLP_COOKIES:
        if config.YTDLP_COOKIES.exists() and config.YTDLP_COOKIES.is_file():
            print(f"  ✅ YTDLP_COOKIES: {config.YTDLP_COOKIES}")
        else:
            print(f"  ⚠️ YTDLP_COOKIES configurado pero el archivo no existe: {config.YTDLP_COOKIES}")
    else:
        print("  ➖ YTDLP_COOKIES (opcional: no configurado; yt-dlp usará modo sin cookies y fallback a Pexels/Pixabay)")

    print("\n== Configuración de Edición (config/edicion.yaml) ==")
    cfg_ed = cargar_config_edicion()
    if config.CONFIG_EDICION_YAML.exists():
        print(f"  ✅ {config.CONFIG_EDICION_YAML.relative_to(config.RAIZ).as_posix()} cargado correctamente")
    else:
        print("  ⚠️ config/edicion.yaml no encontrado -> usando valores por defecto internos")
    h_cfg = cfg_ed.get("formatos", {}).get("horizontal_16_9", {})
    v_cfg = cfg_ed.get("formatos", {}).get("vertical_9_16", {})
    print(
        f"     • 16:9 Documental: color_grading={h_cfg.get('color_grading')}, vignette={h_cfg.get('vignette')}, "
        f"grain={h_cfg.get('film_grain_ffmpeg')}, overlay={h_cfg.get('video_overlay')}, "
        f"ken_burns={h_cfg.get('ken_burns')}, xfade={h_cfg.get('transiciones_xfade')}, "
        f"top_fx={h_cfg.get('top_rank_fx')}, sidechain={h_cfg.get('audio_ducking_sidechain')}"
    )
    print(
        f"     • 9:16 Reels:      cortes={v_cfg.get('duracion_corte_min_s')}-{v_cfg.get('duracion_corte_max_s')}s, "
        f"karaoke={v_cfg.get('subtitulos_karaoke')}, zoom_punch={v_cfg.get('zoom_punch')}, "
        f"sidechain={v_cfg.get('audio_ducking_sidechain')}"
    )

    print("\n== Identidad de Marca (Host Sprites) ==")
    poses_ok = []
    poses_faltantes = []
    for p_name in config.POSES:
        tiene_cerrada = (config.HOST_DIR / f"{p_name}_cerrada.png").exists()
        tiene_abierta = (config.HOST_DIR / f"{p_name}_abierta.png").exists()
        if tiene_cerrada and tiene_abierta:
            poses_ok.append(p_name)
        else:
            poses_faltantes.append(p_name)
    print(f"  {'✅' if not poses_faltantes else '⚠️'} Host Personalizado: {len(poses_ok)}/{len(config.POSES)} poses activas ({', '.join(poses_ok)})")
    if poses_faltantes:
        print(f"     ⚠️ Poses incompletas: {', '.join(poses_faltantes)}")

    print("\n== Música por Mood (assets/music/) ==")
    al_menos_una_musica = False
    total_musica = 0
    for mood in config.MUSIC_MOODS:
        carpeta_m = config.MUSIC_DIR / mood
        archivos_m = listar_archivos_audio(carpeta_m)
        total_musica += len(archivos_m)
        if archivos_m:
            al_menos_una_musica = True
            ejemplos = ", ".join(a.name for a in archivos_m[:3]) + ("..." if len(archivos_m) > 3 else "")
            print(f"  ✅ mood '{mood}': {len(archivos_m)} archivo(s) ({ejemplos})")
        else:
            ruta_fb, mood_fb, _ = resolver_musica_mood(mood, silencioso=True)
            estado_dir = "0 archivos" if carpeta_m.exists() else "carpeta no existe"
            if ruta_fb:
                al_menos_una_musica = True
                print(f"  ⚠️ mood '{mood}': {estado_dir} -> degradará con elegancia a '{mood_fb}' ({ruta_fb.name})")
            else:
                print(f"  ❌ mood '{mood}': {estado_dir} y sin fallback disponible (ejecuta: python scripts/descargar_assets.py)")
    print(f"     Total pistas de música: {total_musica}")
    ok &= al_menos_una_musica

    print("\n== Efectos de Sonido por Categoría (assets/sfx/) ==")
    categorias_sfx = [c for c in config.SFX_CATEGORIAS if c != "ninguno"]
    total_sfx = 0
    for cat in categorias_sfx:
        carpeta_s = config.SFX_DIR / cat
        archivos_s = listar_archivos_audio(carpeta_s)
        total_sfx += len(archivos_s)
        if archivos_s:
            print(f"  ✅ sfx '{cat}': {len(archivos_s)} archivo(s)")
        else:
            ruta_fb, cat_fb, _ = resolver_sfx_categoria(cat, silencioso=True)
            estado_dir = "0 archivos" if carpeta_s.exists() else "carpeta no existe"
            if ruta_fb:
                print(f"  ⚠️ sfx '{cat}': {estado_dir} -> degradará con elegancia a '{cat_fb}' ({ruta_fb.name})")
            else:
                print(f"  ❌ sfx '{cat}': {estado_dir} y sin fallback disponible")
    print(f"     Total archivos SFX: {total_sfx}")

    print("\n== Overlays de Video por Tipo (assets/overlays/) ==")
    total_overlays = 0
    for tipo_ov in config.OVERLAY_TIPOS:
        carpeta_o = config.OVERLAYS_DIR / tipo_ov
        archivos_o = listar_archivos_overlay(carpeta_o)
        total_overlays += len(archivos_o)
        if archivos_o:
            print(f"  ✅ overlay '{tipo_ov}': {len(archivos_o)} archivo(s)")
        else:
            estado_dir = "0 archivos" if carpeta_o.exists() else "carpeta no existe"
            print(f"  ⚠️ overlay '{tipo_ov}': {estado_dir} -> degradará con elegancia a otro overlay o grano/viñeta FFmpeg")
    print(f"     Total archivos de overlay: {total_overlays}")

    print("\nTodo listo para operar ✅" if ok else "\nFaltan elementos obligatorios ❌")
    return 0 if ok else 1


def cmd_nuevo(args) -> int:
    from src.guion import etapa_guion

    p = Proyecto.crear(args.tema, args.minutos, args.lang)
    if getattr(args, "sin_host", False):
        p.datos["sin_host"] = True
        p.guardar()
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
    if getattr(args, "sin_host", False):
        p.datos["sin_host"] = True
        p.guardar()
    print(f"\n🚀 Procesando proyecto: '{p.tema}' ({p.datos['slug']})\n")

    # 1. Voz IA Masterizada
    duraciones = etapa_voz(p)

    # 2. B-Roll
    etapa_broll(p, duraciones)

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
    n.add_argument("--sin-host", action="store_true", help="Desactiva el avatar Host 2D en todos los planos")
    n.set_defaults(fn=cmd_nuevo)

    c = sub.add_parser("continuar")
    c.add_argument("slug")
    c.add_argument("--sin-host", action="store_true", help="Desactiva el avatar Host 2D en todos los planos")
    c.set_defaults(fn=cmd_continuar)

    d = sub.add_parser("doblar")
    d.add_argument("slug")
    d.add_argument("--audio", required=True, help="Ruta al archivo .wav con la voz humana")
    d.set_defaults(fn=cmd_doblar)

    a = sub.add_parser("auto")
    a.add_argument("tema")
    a.add_argument("--minutos", type=float, default=1.0)
    a.add_argument("--lang", default="es")
    a.add_argument("--sin-host", action="store_true", help="Desactiva el avatar Host 2D en todos los planos")
    a.set_defaults(fn=cmd_auto)

    s = sub.add_parser("estado")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_estado)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
