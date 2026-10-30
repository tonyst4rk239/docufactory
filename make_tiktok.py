"""Docu Factory — CLI para producción automática de videos en TikTok / Shorts / Reels (9:16).
Duración optimizada para 30 segundos, retención extrema, avatar en esquina inferior y bucle continuo.

Uso:
  python make_tiktok.py importar <guion.json> [--auto] [--reusar]
  python make_tiktok.py nuevo "tema" [--segundos 30] [--reusar]
  python make_tiktok.py preparar <slug>                        # voz + b-roll 9:16 + cuadros para revisión
  python make_tiktok.py revisar <slug> [opciones]              # aprueba, rechaza o reemplaza clips (Lente)
  python make_tiktok.py renderizar <slug> [--forzar]           # montaje 9:16 y exportación dual
  python make_tiktok.py continuar <slug>                       # pipeline 9:16 de corrido
  python make_tiktok.py auto "tema" [--segundos 30] [--reusar] # automático completo
  python make_tiktok.py estado <slug>                          # estado del reel y resumen de revisión
"""
from __future__ import annotations

import argparse
import json
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
    print(f"\nPara continuar: python make_tiktok.py preparar {p.datos['slug']} o continuar {p.datos['slug']}")
    return 0


def cmd_preparar(args) -> int:
    from src.revision import generar_revision_broll, formatear_resumen_revision

    p = Proyecto.cargar(args.slug)
    p_guion = p.ruta("guion", "guion_tiktok.json")
    if not p_guion.exists():
        print(f"❌ No se encontró guion de TikTok en: {p_guion}")
        return 1

    data = json.loads(p_guion.read_text(encoding="utf-8"))
    guion = GuionTikTok.model_validate(data)
    p.invalidar_cache_si_guion_cambio(guion.escenas)

    print(f"\n🎬 [PREPARAR 9:16] Síntesis de voz y B-roll vertical: '{p.tema}' ({p.datos['slug']})\n")

    # 1. Voces aceleradas Edge-TTS
    duraciones = etapa_voz_tiktok(p, guion)

    # 2. Descarga de clips verticales
    etapa_broll_tiktok(p, guion, duraciones)

    # 3. Generar cuadros JPG de revisión (inicio, mitad, final) y revision.json
    generar_revision_broll(p, formato="9:16")

    print("\n" + "=" * 65)
    print("⏸️  PAUSA DE REVISIÓN DE B-ROLL VERTICAL (Agente Lente)")
    print("=" * 65)
    print(formatear_resumen_revision(p))
    print(
        "\n💡 Próximos pasos:\n"
        f"   • Aprobar escenas:   python make_tiktok.py revisar {p.datos['slug']} --aprobar 1,2,3\n"
        f"   • Rechazar escenas:  python make_tiktok.py revisar {p.datos['slug']} --rechazar 2:\"motivo\"\n"
        f"   • Reemplazar clip:   python make_tiktok.py revisar {p.datos['slug']} --reemplazar 2 --consulta \"dark alley\"\n"
        f"   • Renderizar final:  python make_tiktok.py renderizar {p.datos['slug']}\n"
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
        formato="9:16",
    )
    print(salida)
    try:
        from datos.db import guardar_produccion
        rev_path = p.ruta("b_roll", "revision.json")
        if rev_path.exists():
            rev_datos = json.loads(rev_path.read_text(encoding="utf-8"))
            rech = [e for e in rev_datos.get("escenas") or [] if e.get("decision") == "rechazada"]
            guardar_produccion({
                "video_id": p.datos.get("slug"),
                "tomas_rechazadas_lente": len(rech),
                "motivos_rechazo": [e.get("motivo") for e in rech if e.get("motivo")],
            })
    except Exception as e:
        print(f"⚠️ Aviso: no se pudo registrar revisión en SQLite ({e})")
    return 0 if ok else 1


def cmd_renderizar(args) -> int:
    from src.revision import verificar_aprobacion

    p = Proyecto.cargar(args.slug)
    p_guion = p.ruta("guion", "guion_tiktok.json")
    if not p_guion.exists():
        print(f"❌ No se encontró guion de TikTok en: {p_guion}")
        return 1

    # Verificar revisión
    aprobado, no_aprobadas = verificar_aprobacion(p, forzar=getattr(args, "forzar", False))
    if not aprobado:
        print("\n" + "=" * 65)
        print("❌ RENDER DETENIDO: Hay micro-escenas pendientes o rechazadas en la revisión:")
        print("=" * 65)
        for na in no_aprobadas:
            eid = na.get("escena")
            est = na.get("estado", "pendiente")
            mot = na.get("motivo_rechazo") or "sin revisar aún"
            txt = (na.get("texto_narrado") or "")[:40]
            print(f"  • Escena {eid:02d} [{est.upper()}]: {mot} (\"{txt}...\")")
        print(
            "\n💡 Opciones:\n"
            f"   1. Aprobar:   python make_tiktok.py revisar {p.datos['slug']} --aprobar {','.join(str(x['escena']) for x in no_aprobadas)}\n"
            f"   2. Reemplazar: python make_tiktok.py revisar {p.datos['slug']} --reemplazar <id> --consulta \"...\"\n"
            f"   3. Forzar:    python make_tiktok.py renderizar {p.datos['slug']} --forzar\n"
        )
        return 1

    data = json.loads(p_guion.read_text(encoding="utf-8"))
    guion = GuionTikTok.model_validate(data)
    duraciones = etapa_voz_tiktok(p, guion)

    print(f"\n🚀 Renderizando video vertical TikTok: '{p.tema}' ({p.datos['slug']})\n")
    resultado_render = etapa_render_tiktok(p, guion, duraciones, sin_normalizar_brillo=getattr(args, 'sin_normalizar_brillo', False))
    try:
        from datos.registrar import registrar_proyecto_completo
        registrar_proyecto_completo(p, duraciones)
    except Exception as e:
        print(f"⚠️ Aviso: no se pudieron registrar métricas en SQLite ({e})")
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


def cmd_continuar(args) -> int:
    from src.revision import generar_revision_broll

    p = Proyecto.cargar(args.slug)
    p_guion = p.ruta("guion", "guion_tiktok.json")
    if not p_guion.exists():
        print(f"❌ No se encontró guion de TikTok en: {p_guion}")
        return 1

    data = json.loads(p_guion.read_text(encoding="utf-8"))
    guion = GuionTikTok.model_validate(data)
    p.invalidar_cache_si_guion_cambio(guion.escenas)

    print(f"\n🚀 Renderizando video vertical TikTok de corrido: '{p.tema}' ({p.datos['slug']})\n")

    # 1. Voces aceleradas Edge-TTS (+12% rate)
    duraciones = etapa_voz_tiktok(p, guion)

    # 2. Descarga de clips verticales / adaptables
    etapa_broll_tiktok(p, guion, duraciones)

    # 3. Generar cuadros de revisión para registro
    generar_revision_broll(p, formato="9:16")

    # 4. Render 1080x1920 con Avatar en esquina y Subtítulos Hormozi
    resultado_render = etapa_render_tiktok(p, guion, duraciones, sin_normalizar_brillo=getattr(args, 'sin_normalizar_brillo', False))
    try:
        from datos.registrar import registrar_proyecto_completo
        registrar_proyecto_completo(p, duraciones)
    except Exception as e:
        print(f"⚠️ Aviso: no se pudieron registrar métricas en SQLite ({e})")
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


def main():
    parser = argparse.ArgumentParser(description="Motor de videos verticales para TikTok / Shorts.")
    subs = parser.add_subparsers(dest="comando")

    p_imp = subs.add_parser("importar", help="Valida e importa un guion JSON externo (Pluma) para 9:16")
    p_imp.add_argument("guion_json", help="Ruta al archivo .json del guion")
    p_imp.add_argument("--auto", action="store_true", help="Ejecuta todo el pipeline vertical de corrido")
    p_imp.add_argument("--solo-guion", action="store_true", help="Solo valida el JSON y genera guion_doblaje.md sin renderizar")
    p_imp.add_argument("--reusar", action="store_true", help="Reutiliza la carpeta de proyecto existente con el mismo slug base")
    p_imp.add_argument("--publicar", action="store_true", help="Sube automáticamente a redes tras terminar")
    p_imp.add_argument("--sin-normalizar-brillo", action="store_true", help="Desactiva la normalización automática de brillo entre escenas")
    p_imp.set_defaults(func=cmd_importar)

    p_nuevo = subs.add_parser("nuevo", help="Crea guion vertical")
    p_nuevo.add_argument("tema", help="Tema del video")
    p_nuevo.add_argument("--segundos", type=int, default=30, help="Duración en segundos (default: 30)")
    p_nuevo.add_argument("--reusar", action="store_true", help="Reutiliza la carpeta de proyecto existente con el mismo slug base")
    p_nuevo.set_defaults(func=cmd_nuevo)

    p_prep = subs.add_parser("preparar", help="Genera voz y B-roll vertical, creando cuadros para revisión visual")
    p_prep.add_argument("slug", help="Slug del proyecto")
    p_prep.set_defaults(func=cmd_preparar)

    p_rev = subs.add_parser("revisar", help="Revisión y curaduría de B-roll vertical: aprobar, rechazar o reemplazar clips")
    p_rev.add_argument("slug", help="Slug del proyecto")
    p_rev.add_argument("--aprobar", help="Lista de escenas a aprobar (ej. '1,2,3' o 'all')")
    p_rev.add_argument("--rechazar", nargs="*", default=[], help="Escenas a rechazar con motivo (ej. 2:'muy oscuro')")
    p_rev.add_argument("--reemplazar", type=int, default=None, help="Número de micro-escena a reemplazar")
    p_rev.add_argument("--url", default=None, help="URL de video para reemplazar")
    p_rev.add_argument("--inicio", type=float, default=0.0, help="Segundo de inicio")
    p_rev.add_argument("--consulta", default=None, help="Nueva búsqueda en inglés para reemplazar")
    p_rev.add_argument("--desde-archivo", nargs="?", const="", default=None, help="Sincroniza decisiones desde revision.json")
    p_rev.set_defaults(func=cmd_revisar)

    p_rnd = subs.add_parser("renderizar", help="Montaje y render final 9:16 (requiere escenas aprobadas salvo --forzar)")
    p_rnd.add_argument("slug", help="Slug del proyecto")
    p_rnd.add_argument("--forzar", action="store_true", help="Fuerza el render ignorando escenas pendientes o rechazadas")
    p_rnd.add_argument("--publicar", action="store_true", help="Sube automáticamente a redes tras terminar")
    p_rnd.add_argument("--sin-normalizar-brillo", action="store_true", help="Desactiva la normalización automática de brillo entre escenas")
    p_rnd.set_defaults(func=cmd_renderizar)

    p_cont = subs.add_parser("continuar", help="Renderiza proyecto existente de corrido")
    p_cont.add_argument("slug", help="Slug del proyecto")
    p_cont.add_argument("--publicar", action="store_true", help="Sube automáticamente a redes tras terminar")
    p_cont.add_argument("--sin-normalizar-brillo", action="store_true", help="Desactiva la normalización automática de brillo entre escenas")
    p_cont.set_defaults(func=cmd_continuar)

    p_auto = subs.add_parser("auto", help="Genera y renderiza sin pausas")
    p_auto.add_argument("tema", help="Tema del video")
    p_auto.add_argument("--segundos", type=int, default=30, help="Duración en segundos (default: 30)")
    p_auto.add_argument("--reusar", action="store_true", help="Reutiliza la carpeta de proyecto existente con el mismo slug base")
    p_auto.add_argument("--publicar", action="store_true", help="Sube automáticamente a redes tras terminar")
    p_auto.add_argument("--sin-normalizar-brillo", action="store_true", help="Desactiva la normalización automática de brillo entre escenas")
    p_auto.set_defaults(func=cmd_auto)

    p_est = subs.add_parser("estado", help="Ver estado del proyecto y resumen de revisión")
    p_est.add_argument("slug", help="Slug del proyecto")
    p_est.set_defaults(func=cmd_estado)

    args = parser.parse_args()
    if not args.comando:
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
