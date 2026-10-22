"""Docu Factory — CLI principal con orquestación completa y doblaje humano.

Uso:
  python make_video.py doctor                                  # verifica entorno, claves y assets
  python make_video.py importar <guion.json> [--auto]          # importa guion externo (Pluma), valida y produce
  python make_video.py nuevo "tema" [--minutos 1.0]            # crea guion con Gemini (opcional) y guía de doblaje
  python make_video.py preparar <slug>                         # sintetiza voz + descarga B-roll y genera revisión visual
  python make_video.py revisar <slug> [opciones]               # aprueba, rechaza o reemplaza clips (Lente)
  python make_video.py renderizar <slug> [--forzar]            # montaje y render final (exige aprobación)
  python make_video.py miniatura <slug> [--titulo "TEXTO"]     # genera miniaturas de alto CTR (1080p y 720p)
  python make_video.py continuar <slug>                        # corre voz, broll, stems y renders duales de corrido
  python make_video.py auto "tema" [--minutos 1.0]             # pipeline continuo sin pausas
  python make_video.py doblar <slug> --audio <wav>             # re-sincroniza con locución humana
  python make_video.py estado <slug>                           # ver progreso del proyecto y resumen de revisión
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
    for nombre, req, nota_opc in [
        ("GEMINI_API_KEY", False, f"opcional: usa 'importar <guion.json>' o respaldo {config.MODELO_GUION}"),
        ("PIXABAY_API_KEY", True, "requerida para B-roll y overlays"),
        ("PEXELS_API_KEY", False, "opcional / recomendada para B-roll con licencia segura"),
        ("FREESOUND_API_KEY", False, "opcional / SFX CC0"),
    ]:
        val = getattr(config, nombre)
        marca = "✅" if val else ("❌" if req else f"➖ ({nota_opc})")
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


def cmd_importar(args) -> int:
    from src.guion import importar_guion_archivo

    ruta_json = Path(args.guion_json)
    print(f"📥 Validando e importando guion externo: {ruta_json}")
    try:
        p, guion_obj, avisos = importar_guion_archivo(
            ruta_json,
            formato_forzado="16:9",
            sin_host=getattr(args, "sin_host", False),
            reusar=getattr(args, "reusar", False),
        )
    except ValueError as e:
        print(f"\n❌ Error de validación en el guion JSON:\n{e}")
        return 1
    except Exception as e:
        print(f"\n❌ No se pudo importar el guion '{ruta_json}': {e}")
        return 1

    print(f"📁 Proyecto inicializado en: {p.carpeta} (slug: {p.datos['slug']})")
    print(f"✅ Guion validado: '{guion_obj.titulo_trabajo}' ({len(guion_obj.escenas)} escenas, TOP {guion_obj.top_n or '-'})")
    for a in avisos:
        print(f"  ⚠️  {a}")
    print(
        "\n📖 Archivos generados:\n"
        f"   • Guía para Teleprompter / Doblaje: {p.ruta('guion', 'guion_doblaje.md')}\n"
        f"   • Lectura rápida de montaje:        {p.ruta('guion', 'guion_montaje.txt')}\n"
        f"   • Estructura técnica de escenas:   {p.ruta('guion', 'guion.json')}"
    )

    if getattr(args, "solo_guion", False):
        print(f"\n⏸️  Modo --solo-guion activo. Para continuar: python make_video.py continuar {p.datos['slug']}")
        return 0

    args.slug = p.datos["slug"]
    if not getattr(args, "auto", False):
        rc = cmd_preparar(args)
        print(
            "\n⏸️  PAUSA DE REVISIÓN (Lente): no se renderizó el video.\n"
            f"   Revisa b_roll/revision/ y luego: python make_video.py revisar {args.slug} --aprobar all\n"
            f"   Render final: python make_video.py renderizar {args.slug}\n"
            "   (Usa 'importar <guion.json> --auto' para correr todo sin pausa.)"
        )
        return rc
    return cmd_continuar(args)


def cmd_nuevo(args) -> int:
    from src.guion import etapa_guion

    if not config.GEMINI_API_KEY:
        print(
            "⚠️  GEMINI_API_KEY no está configurada (Gemini es opcional en v3).\n"
            "👉 Para crear y producir un proyecto desde un archivo de guion externo (Pluma), usa:\n"
            "   python make_video.py importar <guion.json> [--auto]"
        )
        return 1

    try:
        p = Proyecto.crear(args.tema, args.minutos, args.lang, reusar=getattr(args, "reusar", False))
    except TypeError:
        p = Proyecto.crear(args.tema, args.minutos, args.lang)
    if getattr(args, "sin_host", False):
        p.datos["sin_host"] = True
        p.guardar()
    args._ultimo_slug = p.datos["slug"]
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


def cmd_preparar(args) -> int:
    from src.guion import cargar_guion
    from src.voz import etapa_voz
    from src.broll import etapa_broll
    from src.revision import generar_revision_broll, formatear_resumen_revision

    p = Proyecto.cargar(args.slug)
    if getattr(args, "sin_host", False):
        p.datos["sin_host"] = True
        p.guardar()
    print(f"\n🎬 [PREPARAR] Iniciando voz y descarga de B-roll: '{p.tema}' ({p.datos['slug']})\n")

    guion_actual = cargar_guion(p)
    p.invalidar_cache_si_guion_cambio(guion_actual.escenas)

    # 1. Voz IA Masterizada
    duraciones = etapa_voz(p)

    # 2. Descarga y curaduría de B-Roll
    etapa_broll(p, duraciones)

    # 3. Generar cuadros JPG de revisión y revision.json
    generar_revision_broll(p, formato="16:9")

    print("\n" + "=" * 65)
    print("⏸️  PAUSA DE REVISIÓN DE B-ROLL (Para el Agente Lente)")
    print("=" * 65)
    print(formatear_resumen_revision(p))
    print(
        "\n💡 Próximos pasos de curaduría:\n"
        f"   • Aprobar escenas:   python make_video.py revisar {p.datos['slug']} --aprobar 1,2,4\n"
        f"   • Rechazar escenas:  python make_video.py revisar {p.datos['slug']} --rechazar 3:\"motivo\"\n"
        f"   • Reemplazar clip:   python make_video.py revisar {p.datos['slug']} --reemplazar 3 --consulta \"nueva búsqueda en inglés\"\n"
        f"   • Renderizar final:  python make_video.py renderizar {p.datos['slug']}\n"
    )
    return 0


def cmd_revisar(args) -> int:
    from src.revision import aplicar_revision_cli

    p = Proyecto.cargar(args.slug)
    ok, salida = aplicar_revision_cli(
        p,
        aprobar=getattr(args, "aprobar", None),
        rechazar=getattr(args, "rechazar", None),
        reemplazar_id=getattr(args, "reemplazar", None),
        url=getattr(args, "url", None),
        inicio_s=getattr(args, "inicio", 0.0),
        consulta=getattr(args, "consulta", None),
        desde_archivo=getattr(args, "desde_archivo", None),
        formato="16:9",
    )
    print(salida)
    return 0 if ok else 1


def cmd_renderizar(args) -> int:
    from src.voz import etapa_voz
    from src.render import etapa_render
    from src.subtitulos import generar_srt
    from src.publicacion import etapa_publicacion
    from src.revision import verificar_aprobacion

    p = Proyecto.cargar(args.slug)
    if getattr(args, "sin_host", False):
        p.datos["sin_host"] = True
        p.guardar()

    # Verificar aprobación de revisión salvo con --forzar
    aprobado, no_aprobadas = verificar_aprobacion(p, forzar=getattr(args, "forzar", False))
    if not aprobado:
        print("\n" + "=" * 65)
        print("❌ RENDER DETENIDO: Hay escenas pendientes o rechazadas en la revisión de B-roll:")
        print("=" * 65)
        for na in no_aprobadas:
            eid = na.get("escena")
            est = na.get("estado", "pendiente")
            mot = na.get("motivo_rechazo") or "sin revisar aún"
            txt = (na.get("texto_narrado") or "")[:45]
            print(f"  • Escena {eid:02d} [{est.upper()}]: {mot} (\"{txt}...\")")
        print(
            "\n💡 Opciones para resolver:\n"
            f"   1. Aprobar escenas:   python make_video.py revisar {p.datos['slug']} --aprobar {','.join(str(x['escena']) for x in no_aprobadas)}\n"
            f"   2. Reemplazar clip:   python make_video.py revisar {p.datos['slug']} --reemplazar <id> --consulta \"nueva búsqueda\"\n"
            f"   3. Forzar el render:  python make_video.py renderizar {p.datos['slug']} --forzar\n"
        )
        return 1

    print(f"\n🚀 Renderizando montaje final: '{p.tema}' ({p.datos['slug']})\n")
    duraciones = etapa_voz(p)

    # 1. Subtítulos
    generar_srt(p, duraciones)

    # 2. Render Dual (Stems + Video IA + Video Karaoke)
    salidas = etapa_render(p, duraciones)

    # 3. Publicación
    etapa_publicacion(p, duraciones)

    print("\n" + "=" * 65)
    print("🏆 ¡PRODUCCIÓN DUAL COMPLETADA CON ÉXITO!")
    print(f"🎙️ Stem Voz IA:          {salidas['voz_master']}")
    print(f"🎧 Stem Mezcla MDE:       {salidas['mde_master']}")
    print(f"📹 Video con Voz IA:      {salidas['video_con_voz']}")
    print(f"🎤 Video Clean / Karaoke: {salidas['video_sin_voz']}")
    print("=" * 65)
    return 0


def cmd_continuar(args) -> int:
    from src.guion import cargar_guion
    from src.voz import etapa_voz
    from src.broll import etapa_broll
    from src.render import etapa_render
    from src.subtitulos import generar_srt
    from src.publicacion import etapa_publicacion
    from src.revision import generar_revision_broll

    p = Proyecto.cargar(args.slug)
    if getattr(args, "sin_host", False):
        p.datos["sin_host"] = True
        p.guardar()
    print(f"\n🚀 Procesando proyecto de corrido: '{p.tema}' ({p.datos['slug']})\n")

    guion_actual = cargar_guion(p)
    p.invalidar_cache_si_guion_cambio(guion_actual.escenas)

    # 1. Voz IA Masterizada
    duraciones = etapa_voz(p)

    # 2. B-Roll
    etapa_broll(p, duraciones)

    # 3. Generar cuadros de revisión para registro
    generar_revision_broll(p, formato="16:9")

    # 4. Subtítulos
    generar_srt(p, duraciones)

    # 5. Render Dual (Stems + Video IA + Video Karaoke)
    salidas = etapa_render(p, duraciones)

    # 6. Publicación
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


def cmd_miniatura(args) -> int:
    from src.miniatura import generar_miniatura_proyecto

    p = Proyecto.cargar(args.slug)
    print(f"\n🎨 Generando paquete de miniaturas A/B para: '{p.tema}' ({p.datos['slug']})...\n")
    res = generar_miniatura_proyecto(
        p=p,
        titulo_custom=getattr(args, "titulo", None),
        pose_custom=getattr(args, "host", None),
        fondo_custom=Path(args.fondo) if getattr(args, "fondo", None) else None,
        subtitulo_custom=getattr(args, "subtitulo", None),
        sello_custom=getattr(args, "stamp", None),
        layout_custom=getattr(args, "layout", None),
        tono_custom=getattr(args, "tono", None),
    )
    print("=" * 65)
    print("🏆 ¡MINIATURAS GENERADAS CON ÉXITO!")
    print(f"🖼️  1080p Full HD: {res['1080p']}")
    print(f"🖼️  720p Estándar: {res['720p']}")
    print(f"📄 Metadatos JSON: {p.ruta('publicacion', 'miniatura.json')}")
    print("=" * 65)
    return 0


def cmd_estado(args) -> int:
    from src.revision import formatear_resumen_revision

    p = Proyecto.cargar(args.slug)
    print(f"Tema: {p.tema}\nUbicación: {p.carpeta}\n")
    print("== Progreso por Etapas ==")
    for e, s in p.datos["etapas"].items():
        icono = {"ok": "✅", "revisar": "⏸️", "pendiente": "⬜", "error": "❌"}.get(s, "•")
        print(f"  {icono} {e:12s}: {s}")
    print()
    print(formatear_resumen_revision(p))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="make_video", description="Docu Factory - Automatización de Video")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    imp = sub.add_parser("importar", help="Valida e importa un guion JSON externo (Pluma), prepara voz/B-roll y pausa para revisión (--auto: todo)")
    imp.add_argument("guion_json", help="Ruta al archivo .json del guion")
    imp.add_argument("--auto", action="store_true", help="Ejecuta todo el pipeline de corrido (voz, broll y render)")
    imp.add_argument("--solo-guion", action="store_true", help="Solo valida el JSON y genera guion_doblaje.md sin renderizar")
    imp.add_argument("--reusar", action="store_true", help="Reutiliza la carpeta de proyecto existente con el mismo slug base")
    imp.add_argument("--sin-host", action="store_true", help="Desactiva el avatar Host 2D en todos los planos")
    imp.set_defaults(fn=cmd_importar)

    n = sub.add_parser("nuevo")
    n.add_argument("tema")
    n.add_argument("--minutos", type=float, default=1.0)
    n.add_argument("--lang", default="es")
    n.add_argument("--reusar", action="store_true", help="Reutiliza la carpeta de proyecto existente con el mismo slug base")
    n.add_argument("--sin-host", action="store_true", help="Desactiva el avatar Host 2D en todos los planos")
    n.set_defaults(fn=cmd_nuevo)

    prep = sub.add_parser("preparar", help="Genera voz y descarga B-roll, extrayendo cuadros para revisión del agente Lente")
    prep.add_argument("slug", help="Slug del proyecto")
    prep.add_argument("--sin-host", action="store_true", help="Desactiva el avatar Host 2D en todos los planos")
    prep.set_defaults(fn=cmd_preparar)

    rev = sub.add_parser("revisar", help="Revisión y curaduría de B-roll: aprobar, rechazar o reemplazar clips")
    rev.add_argument("slug", help="Slug del proyecto")
    rev.add_argument("--aprobar", help="Lista de escenas a aprobar (ej. '1,2,4' o 'all')")
    rev.add_argument("--rechazar", nargs="*", default=[], help="Escenas a rechazar con motivo (ej. 3:'demasiado oscuro')")
    rev.add_argument("--reemplazar", type=int, default=None, help="Número de escena a reemplazar")
    rev.add_argument("--url", default=None, help="URL de video para reemplazar (YouTube, TikTok o directa)")
    rev.add_argument("--inicio", type=float, default=0.0, help="Segundo de inicio para el clip reemplazado")
    rev.add_argument("--consulta", default=None, help="Nueva consulta de búsqueda en inglés para reemplazar")
    rev.add_argument("--desde-archivo", nargs="?", const="", default=None, help="Sincroniza decisiones desde revision.json")
    rev.set_defaults(fn=cmd_revisar)

    rnd = sub.add_parser("renderizar", help="Montaje y render final del proyecto (requiere escenas aprobadas salvo --forzar)")
    rnd.add_argument("slug", help="Slug del proyecto")
    rnd.add_argument("--forzar", action="store_true", help="Fuerza el render ignorando escenas pendientes o rechazadas")
    rnd.add_argument("--sin-host", action="store_true", help="Desactiva el avatar Host 2D en todos los planos")
    rnd.set_defaults(fn=cmd_renderizar)

    mini = sub.add_parser("miniatura", help="Genera miniaturas 16:9 de alto CTR para el proyecto (1080p y 720p)")
    mini.add_argument("slug", help="Slug del proyecto")
    mini.add_argument("--titulo", default=None, help="Texto viral en amarillo de alto impacto (opcional)")
    mini.add_argument("--host", default=None, help="Pose del host (si se omite, se elige según tono)")
    mini.add_argument("--fondo", default=None, help="Ruta a imagen de fondo personalizada")
    mini.add_argument("--subtitulo", default=None, help="Banner inferior")
    mini.add_argument("--stamp", default=None, help="Sello: REC, CONFIDENCIAL, POLÉMICA, EXCLUSIVA o ninguno")
    mini.add_argument("--layout", default=None, choices=["avatar_derecha", "avatar_izquierda", "avatar_centro", "sin_avatar"])
    mini.add_argument("--tono", default=None, help="Fuerza un tono (si no, usa guion.tono)")
    mini.set_defaults(fn=cmd_miniatura)

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
    a.add_argument("--reusar", action="store_true", help="Reutiliza la carpeta de proyecto existente con el mismo slug base")
    a.add_argument("--sin-host", action="store_true", help="Desactiva el avatar Host 2D en todos los planos")
    a.set_defaults(fn=cmd_auto)

    s = sub.add_parser("estado")
    s.add_argument("slug")
    s.set_defaults(fn=cmd_estado)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
