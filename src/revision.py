"""Módulo de pausa de revisión y curaduría de B-roll (para el agente Lente y curador humano).

Gestiona la generación de cuadros JPG (inicio, mitad y final), el registro
b_roll/revision.json, la aprobación/rechazo de clips, el reemplazo dinámico
mediante URL o nueva consulta, y la verificación previa al render final.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

import requests

import sys

from . import config
from .estado import Proyecto

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _sin_ssml(texto: str) -> str:
    """Quita etiquetas SSML (<break .../>, etc.) del texto narrado para revision.json."""
    import re as _re
    t = _re.sub(r"<[^>]+>", " ", texto or "")
    return _re.sub(r"\s+", " ", t).strip()


def _imprimir(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


def obtener_metricas_visuales(ruta_clip: Path, formato: str = "16:9") -> dict[str, Any]:
    """Obtiene duración, resolución y luminancia media (YAVG) de un clip."""
    from .broll import analizar_calidad_visual_clip, obtener_dimensiones_video, obtener_duracion_video

    if not ruta_clip.exists() or ruta_clip.stat().st_size < 1000:
        return {"duracion": 0.0, "resolucion": "0x0", "luminancia_media": 0.0}

    w, h, dur = obtener_dimensiones_video(ruta_clip)
    if dur <= 0:
        dur = obtener_duracion_video(ruta_clip)

    _, _, metricas = analizar_calidad_visual_clip(
        ruta_clip, formato=formato, min_yavg=1.0, es_fuente_youtube=False
    )
    yavg = float(metricas.get("yavg", 50.0))

    return {
        "duracion": round(dur, 2),
        "resolucion": f"{w}x{h}" if (w and h) else ("1920x1080" if formato == "16:9" else "1080x1920"),
        "luminancia_media": round(yavg, 1),
    }


def extraer_cuadros_revision(ruta_clip: Path, carpeta_revision: Path, escena_id: int) -> list[str]:
    """Extrae 3 cuadros JPG (inicio, mitad y final) de un clip de video."""
    ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
    carpeta_revision.mkdir(parents=True, exist_ok=True)

    cuadros_rel: list[str] = []
    from .broll import obtener_duracion_video
    dur = obtener_duracion_video(ruta_clip) if ruta_clip.exists() else 0.0
    if dur <= 0:
        dur = 3.0

    t_inicio = min(0.35, max(0.08, dur * 0.08))
    t_mitad = max(0.15, dur * 0.50)
    t_final = max(0.20, dur - 0.35 if dur > 0.8 else dur * 0.90)

    marcas = [
        ("inicio", t_inicio),
        ("mitad", t_mitad),
        ("final", t_final),
    ]

    for sufijo, t_sec in marcas:
        nombre_jpg = f"escena_{escena_id:03d}_{sufijo}.jpg"
        destino_jpg = carpeta_revision / nombre_jpg
        rel_posix = f"b_roll/revision/{nombre_jpg}"

        if ruta_clip.exists():
            cmd = [
                ffmpeg, "-y",
                "-ss", f"{t_sec:.2f}",
                "-i", str(ruta_clip),
                "-frames:v", "1",
                "-q:v", "2",
                str(destino_jpg),
            ]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
            except Exception:
                pass

        if not destino_jpg.exists() or destino_jpg.stat().st_size < 100:
            # Generar cuadro sustituto si el clip no decodificó o falló
            cmd_fb = [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", f"color=c=0x1a202c:s=640x360:d=0.1",
                "-frames:v", "1",
                str(destino_jpg),
            ]
            try:
                subprocess.run(cmd_fb, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            except Exception:
                pass

        cuadros_rel.append(rel_posix)

    return cuadros_rel


def cargar_revision_json(p: Proyecto) -> list[dict[str, Any]]:
    """Carga b_roll/revision.json o lo inicializa si no existe."""
    archivo_rev = p.ruta("b_roll", "revision.json")
    if archivo_rev.exists():
        try:
            datos = json.loads(archivo_rev.read_text(encoding="utf-8"))
            if isinstance(datos, list):
                return datos
            if isinstance(datos, dict) and "escenas" in datos:
                return datos["escenas"]
        except Exception:
            pass
    return generar_revision_broll(p)


def guardar_revision_json(p: Proyecto, items: list[dict[str, Any]]) -> None:
    """Guarda b_roll/revision.json y actualiza el estado de la etapa en proyecto.json."""
    archivo_rev = p.ruta("b_roll", "revision.json")
    archivo_rev.parent.mkdir(parents=True, exist_ok=True)
    archivo_rev.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    total = len(items)
    aprobadas = sum(1 for it in items if it.get("estado") == "aprobado")
    rechazadas = sum(1 for it in items if it.get("estado") == "rechazado")
    pendientes = total - aprobadas - rechazadas

    if total > 0 and aprobadas == total:
        p.marcar("revision", "ok")
    elif rechazadas > 0:
        p.marcar("revision", "revisar")
    else:
        p.marcar("revision", "pendiente")


def _cuadros_tomas(p: Proyecto, eid: int, carpeta_revision: Path) -> list[dict[str, Any]]:
    """Un cuadro JPG (mitad) por toma del manifiesto: clips reales (fuente='real') y B-roll libre."""
    from .tomas import cargar_manifiesto
    from .broll import obtener_duracion_video

    man = cargar_manifiesto(p, eid)
    if not man:
        return []
    ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
    salida: list[dict[str, Any]] = []
    for k, t in enumerate(man.get("tomas", []), 1):
        ruta = p.ruta("b_roll", t["archivo"])
        nombre = f"escena_{eid:03d}_toma_{k:02d}.jpg"
        destino = carpeta_revision / nombre
        if ruta.exists():
            dur = obtener_duracion_video(ruta) or 2.0
            subprocess.run(
                [ffmpeg, "-y", "-ss", f"{max(0.1, dur * 0.5):.2f}", "-i", str(ruta), "-frames:v", "1",
                 "-vf", "scale=640:-2", "-q:v", "4", str(destino)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        salida.append({
            "toma": k,
            "archivo": t["archivo"],
            "fuente": t.get("fuente", "stock"),
            "url": t.get("url", ""),
            "credito": t.get("credito"),
            "duracion": t.get("duracion") or t.get("duracion_archivo"),
            "cuadro": f"b_roll/revision/{nombre}" if destino.exists() else None,
        })
    return salida


def generar_revision_broll(p: Proyecto, formato: str = "16:9", preservar_estados: bool = True) -> list[dict[str, Any]]:
    """Genera los 3 cuadros JPG por escena y escribe b_roll/revision.json con estado inicial 'pendiente'."""
    carpeta_revision = p.ruta("b_roll", "revision")
    carpeta_revision.mkdir(parents=True, exist_ok=True)

    # 1. Cargar guion técnico
    escenas_datos: list[dict[str, Any]] = []
    p_guion_json = p.ruta("guion", "guion.json")
    p_guion_tt = p.ruta("guion", "guion_tiktok.json")

    if p_guion_json.exists():
        try:
            from .guion import cargar_guion
            g = cargar_guion(p)
            for esc in g.escenas:
                queries = list(getattr(esc, "broll_queries_en", []) or [])
                if esc.broll_query_en and esc.broll_query_en not in queries:
                    queries.insert(0, esc.broll_query_en)
                escenas_datos.append({
                    "id": esc.id,
                    "texto": getattr(esc, "voz", None) or getattr(esc, "narracion", ""),
                    "queries": queries,
                })
        except Exception:
            pass

    if not escenas_datos and p_guion_tt.exists():
        try:
            from src_tiktok.guion_tt import GuionTikTok
            data_tt = json.loads(p_guion_tt.read_text(encoding="utf-8"))
            g_tt = GuionTikTok.model_validate(data_tt)
            for esc in g_tt.escenas:
                queries = list(getattr(esc, "broll_queries_en", []) or [])
                if esc.broll_query_en and esc.broll_query_en not in queries:
                    queries.insert(0, esc.broll_query_en)
                escenas_datos.append({
                    "id": esc.id,
                    "texto": esc.voz,
                    "queries": queries,
                })
            formato = "9:16"
        except Exception:
            pass

    # 2. Cargar créditos para extraer URL y fuentes ya detectadas
    creditos_map: dict[int, dict[str, Any]] = {}
    p_creditos = p.ruta("b_roll", "creditos.json")
    if p_creditos.exists():
        try:
            c_list = json.loads(p_creditos.read_text(encoding="utf-8"))
            for item in c_list:
                eid = int(item.get("escena", 0))
                if eid:
                    creditos_map[eid] = item
        except Exception:
            pass

    # 3. Cargar estados previos si ya existía revisión y se pide preservar
    estados_previos: dict[int, dict[str, Any]] = {}
    archivo_rev = p.ruta("b_roll", "revision.json")
    if preservar_estados and archivo_rev.exists():
        try:
            r_list = json.loads(archivo_rev.read_text(encoding="utf-8"))
            for item in r_list:
                eid = int(item.get("escena", 0))
                if eid:
                    estados_previos[eid] = item
        except Exception:
            pass

    # 4. Si no se cargaron escenas del guion, inferirlas de los clips en b_roll/
    if not escenas_datos:
        clips = sorted(p.ruta("b_roll").glob("escena_*.mp4"))
        for c in clips:
            m = re.search(r"escena_(\d+)", c.name)
            eid = int(m.group(1)) if m else len(escenas_datos) + 1
            escenas_datos.append({"id": eid, "texto": "", "queries": []})

    items_revision: list[dict[str, Any]] = []
    _imprimir(f"📸 Generando cuadros y metadatos de revisión visual para {len(escenas_datos)} escenas...")

    for esc_info in escenas_datos:
        eid = esc_info["id"]
        clip_path = p.ruta("b_roll", f"escena_{eid:03d}.mp4")

        # Extraer cuadros
        cuadros = extraer_cuadros_revision(clip_path, carpeta_revision, eid)

        # Extraer métricas visuales
        metricas = obtener_metricas_visuales(clip_path, formato=formato)

        c_item = creditos_map.get(eid, {})
        prev_item = estados_previos.get(eid, {})

        fuente = c_item.get("fuente") or prev_item.get("fuente") or "B-Roll"
        url = c_item.get("url") or prev_item.get("url") or ""
        if not url:
            det = str(c_item.get("detalle") or "")
            m_yt = re.search(r"yt:([A-Za-z0-9_-]{11})", det)
            if m_yt:
                url = f"https://www.youtube.com/watch?v={m_yt.group(1)}"
            elif "pixabay" in det.lower():
                url = "https://pixabay.com/videos/"
            elif "pexels" in det.lower():
                url = "https://www.pexels.com/video/"

        consultas = esc_info["queries"] or prev_item.get("consultas_usadas") or []
        estado = prev_item.get("estado", "pendiente")
        motivo_rechazo = prev_item.get("motivo_rechazo")

        items_revision.append({
            "escena": eid,
            "texto_narrado": _sin_ssml(esc_info["texto"]),
            "consultas_usadas": consultas,
            "fuente": fuente,
            "url": url,
            "duracion": metricas["duracion"],
            "resolucion": metricas["resolucion"],
            "luminancia_media": metricas["luminancia_media"],
            "cuadros": cuadros,
            "tomas": _cuadros_tomas(p, eid, carpeta_revision),
            "estado": estado,
            "motivo_rechazo": motivo_rechazo,
        })

    guardar_revision_json(p, items_revision)
    _imprimir(f"✅ Archivo de revisión listo: {archivo_rev.relative_to(config.RAIZ).as_posix()}")
    return items_revision


def parsear_lista_escenas(cadena: str, max_escenas: int) -> list[int]:
    """Parsea listas de escenas como '1,2,4', '1-3', 'all', 'todas'."""
    s = (cadena or "").strip().lower()
    if not s:
        return []
    if s in ("all", "todas", "todo", "*"):
        return list(range(1, max_escenas + 1))

    resultado: set[int] = set()
    for bloque in s.split(","):
        bloque = bloque.strip()
        if not bloque:
            continue
        if "-" in bloque:
            partes = bloque.split("-")
            if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
                ini, fin = int(partes[0]), int(partes[1])
                for x in range(min(ini, fin), max(ini, fin) + 1):
                    resultado.add(x)
        elif bloque.isdigit():
            resultado.add(int(bloque))

    return sorted(resultado)


def parsear_rechazos(especificaciones: list[str] | str) -> dict[int, str]:
    """Parsea motivos de rechazo como 3:'motivo', 3:motivo, o listas mixtas."""
    if isinstance(especificaciones, str):
        especificaciones = [especificaciones]

    rechazos: dict[int, str] = {}
    for spec in especificaciones:
        spec = (spec or "").strip()
        if not spec:
            continue
        # Manejar múltiples declaraciones separadas por comas fuera de comillas
        partes = [spec]
        if "," in spec and ":" in spec and not (spec.startswith('"') and spec.endswith('"')):
            # Divisor básico respetando comillas
            sub_partes = re.findall(r'(\d+(?:\s*,\s*\d+)*\s*:\s*(?:"[^"]*"|\'[^\']*\'|[^,]+))', spec)
            if sub_partes:
                partes = sub_partes

        for p in partes:
            if ":" in p:
                ids_str, motivo_str = p.split(":", 1)
                motivo = motivo_str.strip().strip('"\'')
                for eid_str in ids_str.split(","):
                    eid_str = eid_str.strip()
                    if eid_str.isdigit():
                        rechazos[int(eid_str)] = motivo or "Rechazado por curador"
            elif p.isdigit():
                rechazos[int(p)] = "Rechazado por curador"

    return rechazos


def _descargar_desde_url(url: str, destino_mp4: Path, inicio_s: float = 0.0, duracion_s: float = 8.0) -> tuple[bool, str, str]:
    """Descarga un clip desde una URL (soporta YouTube/TikTok vía yt-dlp y enlaces directos)."""
    from .broll import _remux_a_mp4, es_video_valido, opciones_ytdlp_base
    import yt_dlp

    url = url.strip()
    temp_prefix = destino_mp4.parent / f"tmp_replace_{destino_mp4.stem}"
    ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"

    es_streaming = any(dom in url.lower() for dom in ("youtube.com", "youtu.be", "tiktok.com", "vimeo.com", "instagram.com"))

    if es_streaming:
        ydl_opts = {
            **opciones_ytdlp_base(),
            "format": "bestvideo[height<=1080][ext=mp4]+bestaudio/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "outtmpl": str(temp_prefix.with_suffix(".%(ext)s")),
            "download_ranges": yt_dlp.utils.download_range_func(None, [(inicio_s, inicio_s + duracion_s)]),
            "force_keyframes_at_cuts": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            candidatos = list(destino_mp4.parent.glob(f"{temp_prefix.name}.*"))
            for f in candidatos:
                if f.is_file() and f.stat().st_size > 10000:
                    ok = _remux_a_mp4(f, destino_mp4)
                    f.unlink(missing_ok=True)
                    if ok:
                        return True, "Streaming (yt-dlp)", url
        except Exception as e:
            _imprimir(f"⚠️ Error al descargar URL streaming con yt-dlp: {e}")

    # Descarga directa vía HTTP/HTTPS
    temp_direct = temp_prefix.with_suffix(".download.tmp")
    try:
        r = requests.get(url, stream=True, headers={"User-Agent": "Mozilla/5.0"}, timeout=20, verify=False)
        if r.ok:
            with open(temp_direct, "wb") as fd:
                for chunk in r.iter_content(chunk_size=65536):
                    fd.write(chunk)
            if temp_direct.exists() and temp_direct.stat().st_size > 10000:
                cmd_cut = [
                    ffmpeg, "-y",
                    "-ss", f"{inicio_s:.2f}",
                    "-i", str(temp_direct),
                    "-t", f"{duracion_s:.2f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-an", str(destino_mp4)
                ]
                subprocess.run(cmd_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                temp_direct.unlink(missing_ok=True)
                if es_video_valido(destino_mp4):
                    return True, "URL Directa", url
    except Exception as e:
        _imprimir(f"⚠️ Error al descargar URL directa: {e}")
    finally:
        temp_direct.unlink(missing_ok=True)

    return False, "Error Descarga", url


def reemplazar_clip(
    p: Proyecto,
    escena_id: int,
    url: str | None = None,
    inicio_s: float = 0.0,
    consulta: str | None = None,
    formato: str = "16:9",
) -> tuple[bool, str]:
    """Descarga un nuevo clip para una escena vía URL o consulta de búsqueda, regenera cuadros y lo deja 'pendiente'."""
    items = cargar_revision_json(p)
    idx_esc = next((i for i, it in enumerate(items) if it.get("escena") == escena_id), None)
    if idx_esc is None:
        return False, f"No se encontró la Escena {escena_id} en el proyecto."

    destino_clip = p.ruta("b_roll", f"escena_{escena_id:03d}.mp4")

    # Determinar duración necesaria
    dur_audio = 8.0
    p_wav = p.ruta("voz", f"escena_{escena_id:03d}.wav")
    p_mp3 = p.ruta("voz", f"escena_{escena_id:03d}.mp3")
    if p_wav.exists():
        from .voz import obtener_duracion_wav
        try:
            dur_audio = obtener_duracion_wav(p_wav)
        except Exception:
            pass
    elif p_mp3.exists():
        from .broll import obtener_duracion_video
        dur_audio = obtener_duracion_video(p_mp3)

    dur_descarga = max(5.0, dur_audio + 2.5)
    exito = False
    fuente_usada = "Reemplazo"
    url_usada = ""
    consultas_usadas: list[str] = []

    if url:
        _imprimir(f"📥 Reemplazando Escena {escena_id} desde URL: {url} (inicio={inicio_s}s, dur={dur_descarga:.1f}s)...")
        exito, fuente_usada, url_usada = _descargar_desde_url(url, destino_clip, inicio_s=inicio_s, duracion_s=dur_descarga)
        consultas_usadas = [url]
    elif consulta:
        _imprimir(f"🔍 Reemplazando Escena {escena_id} con búsqueda en inglés: '{consulta}'...")
        from .broll import (
            _buscar_candidatos_pexels_scoring,
            _buscar_candidatos_pixabay_scoring,
            descargar_archivo_directo,
            descargar_clip_youtube,
            youtube_disponible,
        )
        consultas_usadas = [consulta.strip()]
        _usados: set[str] = set()
        try:
            _rev = json.loads(p.ruta("b_roll", "revision.json").read_text(encoding="utf-8"))
            _usados = {it.get("url") for it in _rev if it.get("escena") != escena_id and it.get("url")}
        except Exception:
            pass
        queries = [consulta.strip(), f"{consulta.strip()} cinematic dark"]

        # Buscar en Pexels
        cands_pex = _buscar_candidatos_pexels_scoring(queries, avoid=set(), mood="misterio", clips_usados=_usados)
        for c in cands_pex:
            if descargar_archivo_directo(c["url"], destino_clip):
                exito = True
                fuente_usada = f"{c['fuente']} (Reemplazo Lente)"
                url_usada = c["url"]
                break

        # Buscar en Pixabay
        if not exito:
            cands_pix = _buscar_candidatos_pixabay_scoring(queries, avoid=set(), mood="misterio", clips_usados=_usados)
            for c in cands_pix:
                if descargar_archivo_directo(c["url"], destino_clip):
                    exito = True
                    fuente_usada = f"{c['fuente']} (Reemplazo Lente)"
                    url_usada = c["url"]
                    break

        # Buscar en YouTube
        if not exito and youtube_disponible():
            _imprimir(f"   Buscando en YouTube para reemplazo: '{consulta}'...")
            clave_yt = descargar_clip_youtube(
                consulta,
                destino_clip,
                inicio_s=max(4.0, inicio_s or 8.0),
                duracion_s=dur_descarga,
                clips_usados=set(),
                formato=formato,
            )
            if clave_yt:
                exito = True
                fuente_usada = "YouTube (Reemplazo Lente)"
                m_yt = re.search(r"yt:([A-Za-z0-9_-]{11})", clave_yt)
                url_usada = f"https://www.youtube.com/watch?v={m_yt.group(1)}" if m_yt else clave_yt
    else:
        return False, "Debe especificar --url <url> o --consulta <consulta> para reemplazar."

    if not exito or not destino_clip.exists():
        return False, f"No se pudo descargar un clip válido para la Escena {escena_id}."

    # Regenerar los 3 cuadros JPG
    carpeta_rev = p.ruta("b_roll", "revision")
    cuadros = extraer_cuadros_revision(destino_clip, carpeta_rev, escena_id)
    metricas = obtener_metricas_visuales(destino_clip, formato=formato)

    # Actualizar registro en revision.json (estado 'pendiente' obligatorio)
    item_actual = items[idx_esc]
    item_actual["estado"] = "pendiente"
    item_actual["motivo_rechazo"] = None
    item_actual["fuente"] = fuente_usada
    item_actual["url"] = url_usada or item_actual.get("url", "")
    item_actual["consultas_usadas"] = consultas_usadas or item_actual.get("consultas_usadas", [])
    item_actual["duracion"] = metricas["duracion"]
    item_actual["resolucion"] = metricas["resolucion"]
    item_actual["luminancia_media"] = metricas["luminancia_media"]
    item_actual["cuadros"] = cuadros

    guardar_revision_json(p, items)
    return True, f"Escena {escena_id} reemplazada con éxito ({fuente_usada}). 3 nuevos cuadros generados en b_roll/revision/. Estado: 'pendiente'."


def aplicar_revision_cli(
    p: Proyecto,
    aprobar: str | None = None,
    rechazar: list[str] | str | None = None,
    reemplazar_id: int | None = None,
    url: str | None = None,
    inicio_s: float = 0.0,
    consulta: str | None = None,
    desde_archivo: str | None = None,
    formato: str = "16:9",
) -> tuple[bool, str]:
    """Aplica las acciones de revisión desde el CLI y devuelve el resultado y resumen."""
    # 1. Cargar o sincronizar desde archivo si se indicó
    items = cargar_revision_json(p)
    total = len(items)
    mensajes: list[str] = []

    if desde_archivo is not None:
        ruta_origen = Path(desde_archivo) if desde_archivo.strip() else p.ruta("b_roll", "revision.json")
        if not ruta_origen.exists():
            return False, f"No se encontró el archivo de revisión especificado: {ruta_origen}"
        try:
            datos_nuevos = json.loads(ruta_origen.read_text(encoding="utf-8"))
            items = datos_nuevos if isinstance(datos_nuevos, list) else datos_nuevos.get("escenas", [])
            mensajes.append(f"📥 Metadatos y decisiones sincronizadas desde: {ruta_origen.name}")
        except Exception as e:
            return False, f"Error leyendo archivo de revisión: {e}"

    item_map = {it["escena"]: it for it in items}

    # 2. Reemplazo de clip si se indicó
    if reemplazar_id is not None:
        ok_rep, msg_rep = reemplazar_clip(
            p,
            escena_id=reemplazar_id,
            url=url,
            inicio_s=inicio_s,
            consulta=consulta,
            formato=formato,
        )
        if not ok_rep:
            return False, msg_rep
        mensajes.append(f"🔄 {msg_rep}")
        items = cargar_revision_json(p)
        item_map = {it["escena"]: it for it in items}

    # 3. Aplicar aprobaciones
    if aprobar:
        ids_aprobar = parsear_lista_escenas(aprobar, max_escenas=total)
        for eid in ids_aprobar:
            if eid in item_map:
                item_map[eid]["estado"] = "aprobado"
                item_map[eid]["motivo_rechazo"] = None
        mensajes.append(f"✅ Escenas aprobadas: {', '.join(str(x) for x in ids_aprobar)}")

    # 4. Aplicar rechazos
    if rechazar:
        mapa_rechazos = parsear_rechazos(rechazar)
        for eid, motivo in mapa_rechazos.items():
            if eid in item_map:
                item_map[eid]["estado"] = "rechazado"
                item_map[eid]["motivo_rechazo"] = motivo
        rechazos_txt = ", ".join(f"{k} ('{v}')" for k, v in mapa_rechazos.items())
        mensajes.append(f"❌ Escenas rechazadas: {rechazos_txt}")

    guardar_revision_json(p, items)

    # 5. Imprimir tabla de resumen
    resumen_txt = formatear_resumen_revision(p)
    return True, "\n".join(mensajes) + "\n\n" + resumen_txt


def verificar_aprobacion(p: Proyecto, forzar: bool = False) -> tuple[bool, list[dict[str, Any]]]:
    """Verifica si el proyecto puede renderizarse. Refusa si hay escenas pendientes o rechazadas."""
    if forzar:
        return True, []

    items = cargar_revision_json(p)
    if not items:
        items = generar_revision_broll(p)

    no_aprobadas = [it for it in items if it.get("estado") != "aprobado"]
    if not no_aprobadas:
        return True, []

    return False, no_aprobadas


def obtener_resumen_revision(p: Proyecto) -> dict[str, Any]:
    """Devuelve conteos y resumen estructurado de la revisión para estado."""
    items = cargar_revision_json(p)
    aprobadas = sum(1 for it in items if it.get("estado") == "aprobado")
    rechazadas = sum(1 for it in items if it.get("estado") == "rechazado")
    pendientes = sum(1 for it in items if it.get("estado") == "pendiente")
    return {
        "total": len(items),
        "aprobadas": aprobadas,
        "rechazadas": rechazadas,
        "pendientes": pendientes,
        "items": items,
    }


def formatear_resumen_revision(p: Proyecto) -> str:
    """Genera la visualización clara y detallada de la revisión para la consola."""
    res = obtener_resumen_revision(p)
    items = res["items"]
    lineas = [
        f"== Revisión de B-Roll (Agente Lente) ==",
        f"Proyecto: {p.datos.get('slug', p.carpeta.name)}",
        f"Total: {res['total']} escenas | ✅ {res['aprobadas']} aprobadas | ⏸️ {res['pendientes']} pendientes | ❌ {res['rechazadas']} rechazadas",
        "",
    ]

    for it in items:
        eid = it.get("escena", 0)
        estado = it.get("estado", "pendiente")
        icono = "✅" if estado == "aprobado" else ("❌" if estado == "rechazado" else "⏸️")
        dur = it.get("duracion", 0.0)
        res_vid = it.get("resolucion", "-")
        yavg = it.get("luminancia_media", 0.0)
        fuente = it.get("fuente", "-")
        txt = (it.get("texto_narrado") or "").strip()
        txt_res = (txt[:55] + "...") if len(txt) > 55 else txt

        lineas.append(
            f"  [{eid:02d}] {icono} {estado.upper():10s} | {dur:04.1f}s | {res_vid:9s} | YAVG={yavg:4.1f} | {fuente:24s} | \"{txt_res}\""
        )
        if estado == "rechazado" and it.get("motivo_rechazo"):
            lineas.append(f"       ↳ 🚫 Motivo de rechazo: {it.get('motivo_rechazo')}")

    carpeta_cuadros = p.ruta("b_roll", "revision")
    if carpeta_cuadros.exists():
        lineas.append(f"\n🖼️  Cuadros JPG para inspección visual: {carpeta_cuadros.as_posix()}/")
        lineas.append(f"📄 Metadatos técnicos completos:       {p.ruta('b_roll', 'revision.json').as_posix()}")

    return "\n".join(lineas)
