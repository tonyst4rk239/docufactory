"""Docu Factory — Registro Automático y Retroactivo de Proyectos en SQLite.

Inserta y sincroniza en datos/docufactory.db todas las características del video:
metadatos, guion, escenas, tomas con tiempos reales, ritmo, audio (LUFS), miniatura,
métricas del título y curaduría de producción.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

PROYECTOS_DIR = RAIZ / "proyectos"

from datos.db import (
    DB_PATH,
    analizar_caracteristicas_titulo,
    analizar_legibilidad_guion,
    calcular_sha1,
    guardar_audio,
    guardar_escenas,
    guardar_guion,
    guardar_miniatura,
    guardar_produccion,
    guardar_ritmo,
    guardar_titulo_features,
    guardar_tomas,
    guardar_video,
    medir_lufs,
    medir_luminancia_media,
    obtener_conexion,
)
from src import config
from src.estado import Proyecto


def _obtener_duracion_archivo(ruta: Path) -> float:
    """Obtiene la duración en segundos de un archivo multimedia con ffprobe."""
    if not ruta or not ruta.exists():
        return 0.0
    ffprobe = config.ffmpeg_bin("ffprobe") or "ffprobe"
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(ruta),
    ]
    import subprocess
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _limpiar_ssml(texto: str) -> str:
    """Elimina etiquetas SSML o corchetes de dirección vocal."""
    t = re.sub(r"<[^>]+>", " ", texto or "")
    t = re.sub(r"\[[^\]]+\]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def registrar_proyecto_completo(
    p: Proyecto,
    duraciones: Optional[dict[int, float]] = None,
    tiempo_render_s: Optional[float] = None,
) -> bool:
    """Extrae y registra todas las características de un proyecto en SQLite.
    
    Es idempotente: si el video ya existe, actualiza los datos existentes sin duplicar.
    Si ocurre algún fallo, no rompe el pipeline; devuelve False y muestra aviso.
    """
    try:
        slug = p.datos.get("slug") or p.carpeta.name.replace("video_", "")
        tema = p.datos.get("tema") or slug.replace("_", " ").title()
        
        # 1. Detectar si es 16:9 (largo) o 9:16 (reel)
        ruta_guion_tt = p.ruta("guion", "guion_tiktok.json")
        ruta_guion_largo = p.ruta("guion", "guion.json")
        es_tiktok = ruta_guion_tt.exists()
        formato = "reel" if es_tiktok else "largo"
        
        datos_guion_raw = {}
        if es_tiktok:
            try:
                datos_guion_raw = json.loads(ruta_guion_tt.read_text(encoding="utf-8"))
            except Exception:
                pass
        elif ruta_guion_largo.exists():
            try:
                datos_guion_raw = json.loads(ruta_guion_largo.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Duración total real del video renderizado si existe
        carpeta_renders = p.carpeta / "renders"
        video_final = None
        for cand in [
            carpeta_renders / f"{slug}_con_voz_ia.mp4",
            carpeta_renders / "video_con_voz_ia.mp4",
            carpeta_renders / "tiktok_con_voz_ia.mp4",
            p.carpeta / "render" / "video_16x9.mp4",
        ]:
            if cand.exists() and cand.stat().st_size > 1000:
                video_final = cand
                break

        duracion_real = _obtener_duracion_archivo(video_final) if video_final else 0.0

        # Si no hay duraciones explícitas, deducir por archivos de voz o escena
        duraciones_escenas: dict[int, float] = dict(duraciones or {})
        escenas_raw = datos_guion_raw.get("escenas") or []
        for esc in escenas_raw:
            eid = int(esc.get("id", 1))
            if eid not in duraciones_escenas:
                # Buscar en voz/escena_XXX.mp3 o .wav
                voz_file = p.ruta("voz", f"escena_{eid:03d}.mp3")
                if not voz_file.exists():
                    voz_file = p.ruta("voz", f"escena_{eid:03d}.wav")
                d_voz = _obtener_duracion_archivo(voz_file) if voz_file.exists() else 0.0
                if d_voz > 0.1:
                    duraciones_escenas[eid] = d_voz
                else:
                    # Estimación por palabras
                    palabras = len(_limpiar_ssml(esc.get("voz", "")).split())
                    duraciones_escenas[eid] = max(2.5, palabras / 2.6)

        if duracion_real <= 0.1 and duraciones_escenas:
            duracion_real = sum(duraciones_escenas.values())

        # Título, descripción y tags
        yt_meta = datos_guion_raw.get("metadatos_youtube") or datos_guion_raw.get("youtube") or {}
        titulos_cands = yt_meta.get("titulos") or [datos_guion_raw.get("titulo") or tema]
        titulo_principal = titulos_cands[0] if titulos_cands else tema
        descripcion = yt_meta.get("descripcion") or ""
        tags_raw = yt_meta.get("tags") or []
        hashtags = " ".join(tags_raw) if isinstance(tags_raw, list) else str(tags_raw)

        # Miniatura
        mini_meta = datos_guion_raw.get("miniatura") or {}
        pub_meta_path = p.ruta("publicacion", "miniatura.json")
        if pub_meta_path.exists():
            try:
                pub_mini = json.loads(pub_meta_path.read_text(encoding="utf-8"))
                mini_meta = {**mini_meta, **pub_mini}
            except Exception:
                pass
        texto_mini = mini_meta.get("titulo_miniatura") or mini_meta.get("texto") or mini_meta.get("titulo") or ""

        # Voz usada
        voz_usada = p.datos.get("voz_usada") or ("gemini:Charon" if es_tiktok else "es-US-AlonsoNeural")
        es_fallback_voz = 1 if ("RESPALDO" in str(voz_usada).upper() or "fallback" in str(voz_usada).lower()) else 0

        # Costos y render
        costo_voz = float(p.datos.get("costo_voz_usd") or 0.0)
        costo_ia = float(p.datos.get("costo_ia_usd") or 0.0)
        t_render = float(tiempo_render_s or p.datos.get("tiempo_render_s") or 0.0)
        fecha_render = (
            datetime.fromtimestamp(video_final.stat().st_mtime, timezone.utc).isoformat()
            if video_final
            else p.datos.get("creado")
        )

        # -------------------------------------------------------------------
        # 2. INSERTAR EN TABLA VIDEOS
        # -------------------------------------------------------------------
        guardar_video({
            "id": slug,
            "slug": slug,
            "formato": formato,
            "tema": tema,
            "tono": datos_guion_raw.get("tono") or "misterio",
            "duracion_s": round(duracion_real, 2),
            "voz": voz_usada,
            "voz_fallback": es_fallback_voz,
            "fecha_render": fecha_render,
            "titulo": titulo_principal,
            "descripcion": descripcion,
            "hashtags": hashtags,
            "texto_miniatura": texto_mini,
            "fuente_tema": p.datos.get("fuente_tema", "otro"),
            "tendencia_origen": p.datos.get("tendencia_origen", ""),
            "fecha_especial": p.datos.get("fecha_especial", ""),
            "costo_voz_usd": costo_voz,
            "costo_ia_usd": costo_ia,
            "tiempo_render_s": round(t_render, 2),
        })

        # -------------------------------------------------------------------
        # 3. INSERTAR EN TABLA GUION Y TITULO_FEATURES
        # -------------------------------------------------------------------
        textos_escenas = [_limpiar_ssml(e.get("voz", "")) for e in escenas_raw]
        texto_completo = " ".join(textos_escenas)
        leg_info = analizar_legibilidad_guion(texto_completo)

        # Tipo de gancho y segundos hasta revelación
        primera_voz = textos_escenas[0] if textos_escenas else ""
        if "¿" in primera_voz or "?" in primera_voz:
            tipo_gancho = "pregunta"
        elif re.search(r"\b(1[89]\d\d|20\d\d|\d+%|\d+\s*mil)\b", primera_voz):
            tipo_gancho = "dato_perturbador"
        elif any(w in primera_voz.lower() for w in ("pero", "nadie", "oculto", "secreto")):
            tipo_gancho = "paradoja"
        else:
            tipo_gancho = "revelacion"

        seg_hasta_misterio = duraciones_escenas.get(1, 4.0)

        # Adelanta siguiente si hay cliffhanger
        adelanta = 1 if re.search(r"\b(siguiente|en el puesto|pero eso no es todo|lo peor|a continuaci[oó]n)\b", texto_completo, re.IGNORECASE) else 0

        guardar_guion({
            "video_id": slug,
            "palabras_totales": leg_info["palabras_totales"],
            "legibilidad": leg_info["legibilidad"],
            "segundos_hasta_misterio": round(seg_hasta_misterio, 2),
            "n_preguntas_abiertas": leg_info["n_preguntas_abiertas"],
            "menciona_caso_real": leg_info["menciona_caso_real"],
            "lugares": leg_info["lugares"],
            "fechas": leg_info["fechas"],
            "adelanta_siguiente": adelanta,
            "tipo_gancho": tipo_gancho,
        })

        feat_tit = analizar_caracteristicas_titulo(titulo_principal)
        feat_tit["video_id"] = slug
        guardar_titulo_features(feat_tit)

        # -------------------------------------------------------------------
        # 4. INSERTAR EN TABLA ESCENAS
        # -------------------------------------------------------------------
        lista_escenas_db = []
        t_acum = 0.0
        total_esc = len(escenas_raw)
        host_vis_segundos: list[float] = []

        for idx, esc in enumerate(escenas_raw, 1):
            eid = int(esc.get("id", idx))
            d_esc = duraciones_escenas.get(eid, 3.0)
            t_ini = t_acum
            t_fin = t_ini + d_esc
            t_acum = t_fin

            txt_esc = _limpiar_ssml(esc.get("voz", ""))
            pal_esc = len(txt_esc.split())
            ppm = (pal_esc / max(0.5, d_esc)) * 60.0

            if idx == 1:
                tipo_esc = "gancho"
            elif idx == total_esc:
                tipo_esc = "cierre"
            elif esc.get("puesto") is not None:
                tipo_esc = "puesto_top"
            else:
                tipo_esc = "desarrollo"

            tiene_preg = 1 if ("?" in esc.get("voz", "") or "¿" in esc.get("voz", "")) else 0
            tiene_cif = 1 if re.search(r"\d+", esc.get("voz", "")) else 0

            lista_escenas_db.append({
                "n_escena": eid,
                "inicio_s": round(t_ini, 3),
                "fin_s": round(t_fin, 3),
                "tipo": tipo_esc,
                "texto": txt_esc,
                "palabras_por_minuto": round(ppm, 1),
                "tiene_pregunta": tiene_preg,
                "tiene_cifra": tiene_cif,
                "emocion_voz": esc.get("music_mood") or datos_guion_raw.get("tono") or "neutral",
            })

            # Host visible
            host_vis = bool(esc.get("host_visible", True)) and not p.datos.get("sin_host", False)
            if host_vis:
                host_vis_segundos.append(round(t_ini + d_esc / 2.0, 1))

        guardar_escenas(slug, lista_escenas_db)

        # -------------------------------------------------------------------
        # 5. INSERTAR EN TABLA TOMAS (Tiempos REALES del Render)
        # -------------------------------------------------------------------
        lista_tomas_db = []
        t_acum = 0.0

        for idx, esc in enumerate(escenas_raw, 1):
            eid = int(esc.get("id", idx))
            d_esc = duraciones_escenas.get(eid, 3.0)
            t_ini_esc = t_acum
            t_fin_esc = t_ini_esc + d_esc
            t_acum = t_fin_esc

            host_vis = bool(esc.get("host_visible", True)) and not p.datos.get("sin_host", False)

            # Manifiesto de cortes detallados de tomas.py si existe
            man_path = p.ruta("b_roll", f"escena_{eid:03d}_tomas.json")
            if man_path.exists():
                try:
                    man = json.loads(man_path.read_text(encoding="utf-8"))
                    segs = man.get("cortes") or []
                    tomas_info = man.get("tomas") or []
                    offset_toma = t_ini_esc
                    for j, dur_t in enumerate(segs):
                        info_t = tomas_info[j] if j < len(tomas_info) else {}
                        arch_t = info_t.get("archivo") or f"escena_{eid:03d}.mp4"
                        ruta_arch = p.ruta("b_roll", arch_t)
                        sha = calcular_sha1(ruta_arch)
                        brillo = medir_luminancia_media(ruta_arch) or 0.0
                        fuente_t = info_t.get("fuente") or ("real" if "real" in arch_t else "pixabay")
                        modo_t = "panel_evidencia" if fuente_t == "real" else "ken_burns"

                        lista_tomas_db.append({
                            "n_escena": eid,
                            "inicio_s": round(offset_toma, 3),
                            "fin_s": round(offset_toma + dur_t, 3),
                            "archivo": arch_t,
                            "sha1": sha,
                            "fuente": fuente_t,
                            "autor": info_t.get("autor", ""),
                            "licencia": info_t.get("licencia", "libre"),
                            "modo": modo_t,
                            "brillo_medio": round(brillo, 1),
                            "movimiento": "zoom_lento" if modo_t == "ken_burns" else "estatico",
                            "aparece_host": 1 if host_vis else 0,
                        })
                        offset_toma += dur_t
                    continue
                except Exception:
                    pass

            # Si no hay manifiesto de tomas múltiples, tomar el clip principal de la escena
            arch_esc = f"escena_{eid:03d}.mp4"
            ruta_clip = p.ruta("b_roll", arch_esc)
            if not ruta_clip.exists():
                ruta_clip = p.ruta("b_roll", f"escena_{eid:03d}.jpg")
                arch_esc = ruta_clip.name if ruta_clip.exists() else arch_esc
            sha = calcular_sha1(ruta_clip)
            brillo = medir_luminancia_media(ruta_clip) or 0.0

            lista_tomas_db.append({
                "n_escena": eid,
                "inicio_s": round(t_ini_esc, 3),
                "fin_s": round(t_fin_esc, 3),
                "archivo": arch_esc,
                "sha1": sha,
                "fuente": "stock",
                "autor": "",
                "licencia": "libre",
                "modo": "fill" if not es_tiktok else "zoom_punch",
                "brillo_medio": round(brillo, 1),
                "movimiento": "zoom_punch" if es_tiktok else "zoom_lento",
                "aparece_host": 1 if host_vis else 0,
            })

        guardar_tomas(slug, lista_tomas_db)

        # -------------------------------------------------------------------
        # 6. INSERTAR EN TABLA RITMO
        # -------------------------------------------------------------------
        num_cortes = max(1, len(lista_tomas_db))
        cpm = (num_cortes / max(1.0, duracion_real)) * 60.0
        dur_media = duracion_real / num_cortes

        guardar_ritmo({
            "video_id": slug,
            "cortes_por_minuto": round(cpm, 2),
            "duracion_media_toma_s": round(dur_media, 2),
            "apariciones_host": host_vis_segundos,
            "subtitulos_resaltados": 1 if es_tiktok else 0,
        })

        # -------------------------------------------------------------------
        # 7. INSERTAR EN TABLA AUDIO (LUFS con FFmpeg loudnorm)
        # -------------------------------------------------------------------
        ruta_master_aud = carpeta_renders / "voz_ia_master.wav"
        if not ruta_master_aud.exists() and video_final:
            ruta_master_aud = video_final

        lufs_medido = medir_lufs(ruta_master_aud) or -16.0
        musica_nombre = datos_guion_raw.get("mood") or "misterio"

        # Conteo de pausas narrativas SSML
        todas_voces_raw = " ".join(esc.get("voz", "") for esc in escenas_raw)
        pausas_tags = re.findall(r"<break\s+time=['\"]?(\d+)m?s?['\"]?", todas_voces_raw)
        n_pausas = len(pausas_tags)
        media_pausa_s = (sum(float(p) / 1000.0 for p in pausas_tags) / max(1, n_pausas)) if n_pausas else 0.35

        sfx_usados = list({esc.get("sfx") for esc in escenas_raw if esc.get("sfx") and esc.get("sfx") != "ninguno"})

        guardar_audio({
            "video_id": slug,
            "lufs": round(lufs_medido, 1),
            "musica": musica_nombre,
            "efectos": sfx_usados,
            "n_pausas": n_pausas,
            "pausa_media_s": round(media_pausa_s, 2),
        })

        # -------------------------------------------------------------------
        # 8. INSERTAR EN TABLA MINIATURA
        # -------------------------------------------------------------------
        arch_mini = "publicacion/miniatura_1080p.jpg"
        tiene_cara = 1 if (mini_meta.get("host") or mini_meta.get("avatar") or not p.datos.get("sin_host")) else 0
        emocion_cara = mini_meta.get("host") or mini_meta.get("pose") or "sorprendido"
        tiene_rec = 1 if (mini_meta.get("stamp") and str(mini_meta.get("stamp")).lower() != "ninguno") else 0
        n_pal_mini = len(texto_mini.split())

        guardar_miniatura({
            "video_id": slug,
            "archivo": arch_mini,
            "n_palabras": n_pal_mini,
            "colores_dominantes": mini_meta.get("colores_dominantes") or ["#FFCC00", "#0B0C10"],
            "tiene_cara": tiene_cara,
            "emocion_cara": emocion_cara,
            "tiene_rec": tiene_rec,
        })

        # -------------------------------------------------------------------
        # 9. INSERTAR EN TABLA PRODUCCION (Tomas rechazadas Lente)
        # -------------------------------------------------------------------
        rev_path = p.ruta("b_roll", "revision.json")
        tomas_rechazadas = 0
        motivos_rechazo = []
        if rev_path.exists():
            try:
                rev_datos = json.loads(rev_path.read_text(encoding="utf-8"))
                for esc_r in rev_datos.get("escenas") or []:
                    if esc_r.get("decision") == "rechazada":
                        tomas_rechazadas += 1
                        if esc_r.get("motivo"):
                            motivos_rechazo.append(esc_r["motivo"])
            except Exception:
                pass

        guardar_produccion({
            "video_id": slug,
            "tomas_rechazadas_lente": tomas_rechazadas,
            "motivos_rechazo": motivos_rechazo,
            "reclamos_content_id": 0,
        })

        return True
    except Exception as e:
        print(f"⚠️ Aviso: no se pudieron registrar métricas en SQLite ({e})")
        return False


def reconstruir_todos_los_proyectos(carpeta_proyectos: Optional[Path] = None) -> tuple[int, int]:
    """Escanea la carpeta proyectos/ e inserta retroactivamente todos los videos."""
    base = Path(carpeta_proyectos or PROYECTOS_DIR)
    if not base.exists():
        print(f"❌ Carpeta no encontrada: {base}")
        return 0, 0

    candidatos = sorted([d for d in base.iterdir() if d.is_dir() and (d / "proyecto.json").exists()])
    print(f"🔄 Reconstruyendo base de datos SQLite para {len(candidatos)} proyectos en {base}...")

    exitos = 0
    fallos = 0
    for d in candidatos:
        try:
            p = Proyecto(d)
            ok = registrar_proyecto_completo(p)
            if ok:
                exitos += 1
                print(f"  ✅ Registrado: {p.datos.get('slug') or d.name}")
            else:
                fallos += 1
                print(f"  ⚠️ Error parcial: {d.name}")
        except Exception as e:
            fallos += 1
            print(f"  ❌ Falló: {d.name} ({e})")

    print("\n" + "=" * 65)
    print(f"🏁 Reconstrucción finalizada: {exitos} exitosos, {fallos} fallos.")
    print(f"📁 Base de datos actualizada en: {DB_PATH}")
    print("=" * 65)
    return exitos, fallos


def main():
    parser = argparse.ArgumentParser(description="Registro analítico y reconstrucción retroactiva de proyectos en SQLite.")
    parser.add_argument("comando", nargs="?", default="reconstruir", choices=["reconstruir", "registrar"], help="Acción a realizar")
    parser.add_argument("slug", nargs="?", default=None, help="Slug del proyecto específico (para comando registrar)")
    args = parser.parse_args()

    if args.comando == "reconstruir":
        reconstruir_todos_los_proyectos()
    elif args.comando == "registrar" and args.slug:
        p = Proyecto.cargar(args.slug)
        ok = registrar_proyecto_completo(p)
        print(f"Registro {'exitoso ✅' if ok else 'fallido ❌'} para {args.slug}")


if __name__ == "__main__":
    main()
