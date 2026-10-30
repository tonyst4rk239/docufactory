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


def _ahora_merida_iso(ts: Optional[float] = None) -> str:
    """Fecha ISO en hora de Mérida (America/Merida). En Windows sin tzdata cae a UTC-6 fijo."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Merida")
    except Exception:
        from datetime import timedelta
        tz = timezone(timedelta(hours=-6), "UTC-6")
    dt = datetime.fromtimestamp(ts, tz) if ts is not None else datetime.now(tz)
    return dt.isoformat(timespec="seconds")


def _clasificar_fuente(*textos: Any) -> Optional[str]:
    """Normaliza la fuente de una toma a commons/pixabay/pexels/ia/real/otro a partir de url, crédito o fuente."""
    t = " ".join(str(x) for x in textos if x).lower()
    if not t.strip():
        return None
    if "wikimedia" in t or "commons" in t:
        return "commons"
    if "pixabay" in t:
        return "pixabay"
    if "pexels" in t:
        return "pexels"
    if re.search(r"\b(ia|ai|gemini|imagen generada|generad[ao] con ia|flux|midjourney|dall)\b", t):
        return "ia"
    if re.search(r"\b(real|tiktok\.com|x\.com|twitter|youtube\.com|youtu\.be|facebook\.com|instagram)\b", t):
        return "real"
    return "otro"


_RE_LICENCIA = re.compile(r"\b(CC0|CC[ -]BY(?:[ -](?:SA|NC|ND))*(?:[ -]\d\.\d)?|Dominio p[uú]blico(?: \([^)]*\))?|PD(?:-[A-Za-z]+)?|Pixabay Content License|Pexels License)", re.IGNORECASE)


def _licencia_de(info: dict) -> Optional[str]:
    lic = info.get("licencia")
    if lic:
        return str(lic)
    m = _RE_LICENCIA.search(str(info.get("credito") or ""))
    if m:
        return m.group(1)
    fuente = _clasificar_fuente(info.get("url"), info.get("pagina"), info.get("fuente"), info.get("credito"))
    if fuente == "pixabay":
        return "Pixabay Content License"
    if fuente == "pexels":
        return "Pexels License"
    return None


def _autor_de(info: dict) -> Optional[str]:
    if info.get("autor"):
        return str(info["autor"])
    cred = str(info.get("credito") or "")
    if not cred:
        return None
    # "Autor / Wikimedia Commons (CC BY 3.0)" o "Archivo.jpg · Autor · CC BY-SA 4.0"
    if " · " in cred:
        partes = [x.strip() for x in cred.split(" · ")]
        if len(partes) >= 2:
            return partes[1]
    m = re.match(r"\s*([^/(;]+?)\s*/", cred)
    if m:
        return m.group(1).strip()
    return None


def _modo_desde_texto(v: Any) -> Optional[str]:
    t = str(v or "").lower()
    if not t:
        return None
    if "fit" in t or "desenfoc" in t or "centrad" in t or "panel" in t:
        return "fit"
    if "fill" in t or "pantalla completa" in t or "recorte" in t or "crop" in t:
        return "fill"
    return None


def _detectar_modo_encuadre(ruta: Path) -> Optional[str]:
    """Detecta fit (imagen centrada sobre fondo desenfocado) vs fill (llena el cuadro) en un clip vertical.

    Compara la energía de bordes (edgedetect) de las franjas superior e inferior contra el centro: en modo fit
    ambas franjas son fondo desenfocado (casi sin bordes)."""
    if not ruta or not Path(ruta).exists():
        return None
    import subprocess
    try:
        ffmpeg_bin = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
    except Exception:
        ffmpeg_bin = "ffmpeg"

    def _energia(crop: str) -> Optional[float]:
        cmd = [ffmpeg_bin, "-hide_banner", "-v", "info", "-ss", "0.5", "-i", str(ruta), "-frames:v", "3",
               "-vf", f"{crop},edgedetect=low=0.08:high=0.2,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
               "-f", "null", "-"]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            vals = [float(x) for x in re.findall(r"YAVG=(\d+(?:\.\d+)?)", (r.stdout or "") + (r.stderr or ""))]
            return sum(vals) / len(vals) if vals else None
        except Exception:
            return None

    arriba = _energia("crop=iw:ih*0.12:0:ih*0.02")
    abajo = _energia("crop=iw:ih*0.12:0:ih*0.86")
    centro = _energia("crop=iw:ih*0.2:0:ih*0.4")
    if arriba is None or abajo is None or centro is None or centro < 0.5:
        return None
    # fit: franjas superior E inferior son fondo desenfocado (sin bordes)
    umbral = max(0.1, centro * 0.05)
    return "fit" if (arriba < umbral and abajo < umbral) else "fill"


def _leer_textos_publicacion(p: Proyecto) -> tuple[Optional[str], Optional[str]]:
    """Descripción/caption y hashtags desde publicacion/ (caption*.txt, descripcion*.txt, paquete_youtube.txt)."""
    carpeta = p.carpeta / "publicacion"
    if not carpeta.exists():
        return None, None
    orden = ["caption.txt", "descripcion.txt", "descripcion_youtube.txt", "paquete_youtube.txt"]
    cands = [carpeta / n for n in orden] + sorted(carpeta.glob("caption*.txt")) + sorted(carpeta.glob("descripcion*.txt"))
    for c in cands:
        if c.exists() and c.stat().st_size > 0:
            try:
                txt = c.read_text(encoding="utf-8").strip()
            except Exception:
                continue
            if not txt:
                continue
            tags = list(dict.fromkeys(re.findall(r"#[\wáéíóúñÁÉÍÓÚÑ]+", txt)))
            return txt, (" ".join(tags) if tags else None)
    return None, None


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
        descripcion = yt_meta.get("descripcion") or None
        tags_raw = yt_meta.get("tags") or []
        hashtags = (" ".join(tags_raw) if isinstance(tags_raw, list) else str(tags_raw)) or None
        desc_pub, tags_pub = _leer_textos_publicacion(p)
        descripcion = descripcion or desc_pub
        hashtags = hashtags or tags_pub

        # Miniatura
        mini_meta = datos_guion_raw.get("miniatura") or {}
        pub_meta_path = p.ruta("publicacion", "miniatura.json")
        if pub_meta_path.exists():
            try:
                pub_mini = json.loads(pub_meta_path.read_text(encoding="utf-8"))
                mini_meta = {**mini_meta, **pub_mini}
            except Exception:
                pass
        texto_mini = mini_meta.get("titulo_miniatura") or mini_meta.get("texto") or mini_meta.get("titulo") or None

        # Voz usada
        voz_reel = p.datos.get("voz_reel") or {}
        voz_usada = p.datos.get("voz_usada") or (f"{voz_reel['motor']}:{voz_reel['voz']}" if voz_reel.get("motor") and voz_reel.get("voz") else None)
        if not voz_usada:
            vu = p.ruta("voz", "VOZ_USADA.txt")
            if vu.exists():
                try:
                    voz_usada = vu.read_text(encoding="utf-8").strip().splitlines()[0][:80] or None
                except Exception:
                    voz_usada = None
        es_fallback_voz = 1 if (voz_reel.get("motivo_respaldo") or "RESPALDO" in str(voz_usada or "").upper() or "fallback" in str(voz_usada or "").lower()) else 0

        # Costos y render
        def _num(v: Any) -> Optional[float]:
            try:
                return float(v) if v is not None and v != "" else None
            except (TypeError, ValueError):
                return None

        costo_voz = _num(p.datos.get("costo_voz_usd"))
        costo_ia = _num(p.datos.get("costo_ia_usd"))
        t_render = _num(tiempo_render_s if tiempo_render_s is not None else p.datos.get("tiempo_render_s"))
        fecha_render = (
            _ahora_merida_iso(video_final.stat().st_mtime)
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
            "fuente_tema": p.datos.get("fuente_tema"),
            "tendencia_origen": p.datos.get("tendencia_origen"),
            "fecha_especial": p.datos.get("fecha_especial"),
            "costo_voz_usd": costo_voz,
            "costo_ia_usd": costo_ia,
            "tiempo_render_s": round(t_render, 2) if t_render is not None else None,
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
        # El avatar sólo aparece si el guion lo usa (usar_avatar) y el proyecto no es sin_host
        usar_avatar = bool(datos_guion_raw.get("usar_avatar", True)) and not p.datos.get("sin_host", False)

        # Créditos reales por escena (fuente, autor, licencia)
        creditos_por_escena: dict[int, dict] = {}
        cred_path = p.ruta("b_roll", "creditos.json")
        if cred_path.exists():
            try:
                for c_item in json.loads(cred_path.read_text(encoding="utf-8")) or []:
                    if isinstance(c_item, dict) and c_item.get("escena") is not None:
                        creditos_por_escena[int(c_item["escena"])] = c_item
            except Exception:
                pass

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
            host_vis = usar_avatar and bool(esc.get("host_visible", True))
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

            host_vis = usar_avatar and bool(esc.get("host_visible", True))
            cred_esc = creditos_por_escena.get(eid, {})

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
                        sha = calcular_sha1(ruta_arch) if ruta_arch.exists() else None
                        brillo = medir_luminancia_media(ruta_arch) if ruta_arch.exists() else None
                        fuente_t = _clasificar_fuente(info_t.get("pagina"), info_t.get("url"), info_t.get("credito"),
                                                      info_t.get("fuente")) or _clasificar_fuente(cred_esc.get("url"), cred_esc.get("credito"))
                        modo_t = _modo_desde_texto(info_t.get("encuadre") or info_t.get("modo")) or _detectar_modo_encuadre(ruta_arch)
                        mov = info_t.get("movimiento")

                        lista_tomas_db.append({
                            "n_escena": eid,
                            "inicio_s": round(offset_toma, 3),
                            "fin_s": round(offset_toma + dur_t, 3),
                            "archivo": arch_t,
                            "sha1": sha,
                            "fuente": fuente_t,
                            "autor": _autor_de(info_t),
                            "licencia": _licencia_de(info_t),
                            "modo": modo_t,
                            "brillo_medio": round(brillo, 1) if brillo is not None else None,
                            "movimiento": mov or None,
                            "aparece_host": 1 if host_vis else 0,
                        })
                        offset_toma += dur_t
                    if segs:
                        continue
                except Exception as e:
                    print(f"⚠️ Aviso: manifiesto de tomas ilegible {man_path.name} ({e})")

            # Si no hay manifiesto de tomas múltiples, tomar el clip principal de la escena
            arch_esc = f"escena_{eid:03d}.mp4"
            ruta_clip = p.ruta("b_roll", arch_esc)
            if not ruta_clip.exists():
                ruta_clip = p.ruta("b_roll", f"escena_{eid:03d}.jpg")
                arch_esc = ruta_clip.name if ruta_clip.exists() else arch_esc
            sha = calcular_sha1(ruta_clip) if ruta_clip.exists() else None
            brillo = medir_luminancia_media(ruta_clip) if ruta_clip.exists() else None

            lista_tomas_db.append({
                "n_escena": eid,
                "inicio_s": round(t_ini_esc, 3),
                "fin_s": round(t_fin_esc, 3),
                "archivo": arch_esc,
                "sha1": sha,
                "fuente": _clasificar_fuente(cred_esc.get("url"), cred_esc.get("credito"), cred_esc.get("fuente")),
                "autor": _autor_de(cred_esc),
                "licencia": _licencia_de(cred_esc),
                "modo": _modo_desde_texto(cred_esc.get("encuadre") or cred_esc.get("modo")) or _detectar_modo_encuadre(ruta_clip),
                "brillo_medio": round(brillo, 1) if brillo is not None else None,
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

        # LUFS del video final (lo que escucha la audiencia); si no hay, del máster de voz
        lufs_medido = medir_lufs(video_final) if video_final else None
        if lufs_medido is None:
            lufs_medido = medir_lufs(ruta_master_aud)
        musica_nombre = datos_guion_raw.get("mood") or None

        # Conteo de pausas narrativas SSML
        todas_voces_raw = " ".join(esc.get("voz", "") for esc in escenas_raw)
        pausas_tags = re.findall(r"<break\s+time=['\"]?(\d+)m?s?['\"]?", todas_voces_raw)
        n_pausas = len(pausas_tags)
        # Pausas: <break time="..ms"> o etiquetas [pausa corta]/[pausa larga] del guion
        n_pausas += len(re.findall(r"\[pausa[^\]]*\]", todas_voces_raw, re.IGNORECASE))
        media_pausa_s = (sum(float(x) / 1000.0 for x in pausas_tags) / len(pausas_tags)) if pausas_tags else None

        sfx_usados = list({esc.get("sfx") for esc in escenas_raw if esc.get("sfx") and esc.get("sfx") != "ninguno"})

        guardar_audio({
            "video_id": slug,
            "lufs": round(lufs_medido, 1) if lufs_medido is not None else None,
            "musica": musica_nombre,
            "efectos": sfx_usados,
            "n_pausas": n_pausas,
            "pausa_media_s": round(media_pausa_s, 2) if media_pausa_s is not None else None,
        })

        # -------------------------------------------------------------------
        # 8. INSERTAR EN TABLA MINIATURA
        # -------------------------------------------------------------------
        arch_mini = None
        for nombre_m in ("miniatura_1080p.jpg", "miniatura_1080p.png", "miniatura.jpg", "miniatura.png"):
            if p.ruta("publicacion", nombre_m).exists():
                arch_mini = f"publicacion/{nombre_m}"
                break
        pose_m = mini_meta.get("host") or mini_meta.get("pose")
        con_avatar_m = mini_meta.get("layout") not in ("sin_avatar",) and (mini_meta.get("avatar") or pose_m)
        stamp = mini_meta.get("stamp") or mini_meta.get("sello")
        guardar_miniatura({
            "video_id": slug,
            "archivo": arch_mini,
            "n_palabras": len(texto_mini.split()) if (arch_mini and texto_mini) else None,
            "colores_dominantes": mini_meta.get("colores_dominantes") if arch_mini else None,
            "tiene_cara": (1 if con_avatar_m else 0) if arch_mini else None,
            "emocion_cara": pose_m if (arch_mini and pose_m) else None,
            "tiene_rec": (1 if (stamp and str(stamp).lower() != "ninguno") else 0) if arch_mini else None,
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
            "reclamos_content_id": None,
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
