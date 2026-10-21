"""Búsqueda y descarga inteligente de clips de YouTube y TikTok (con fallback a Pixabay).

Utiliza yt-dlp con rangos de tiempo (download_ranges) para descargar únicamente
fragmentos de 3 a 6 segundos en alta resolución sin sobrecargar ancho de banda.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional
import requests
import yt_dlp

from . import config
from .estado import Proyecto
from .guion import cargar_guion, Guion, Escena

# Asegurar que FFmpeg esté en el PATH dinámico de yt-dlp
ffmpeg_bin_path = config.ffmpeg_bin("ffmpeg")
if ffmpeg_bin_path:
    ffmpeg_dir = str(Path(ffmpeg_bin_path).parent)
    if ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")


def obtener_duracion_video(ruta: Path) -> float:
    """Devuelve la duración exacta en segundos de un archivo de video mediante ffprobe."""
    ffprobe = config.ffmpeg_bin("ffprobe")
    if not ffprobe or not ruta.exists() or ruta.stat().st_size < 1024:
        return 0.0
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(ruta)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        val = res.stdout.strip()
        return float(val) if val else 0.0
    except Exception:
        return 0.0


def obtener_dimensiones_video(ruta: Path) -> tuple[int, int, float]:
    """Devuelve (width, height, duration) del stream de video mediante ffprobe."""
    ffprobe = config.ffmpeg_bin("ffprobe")
    if not ffprobe or not ruta.exists() or ruta.stat().st_size < 1024:
        return 0, 0, 0.0
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json",
        str(ruta),
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(res.stdout or "{}")
        streams = data.get("streams") or [{}]
        w = int(streams[0].get("width") or 0)
        h = int(streams[0].get("height") or 0)
        dur = float((data.get("format") or {}).get("duration") or 0.0)
        return w, h, dur
    except Exception:
        return 0, 0, obtener_duracion_video(ruta)


def es_video_valido(ruta: Path, min_duracion: float = 0.5) -> bool:
    """Valida que el archivo exista, tenga un tamaño razonable y streams de video decodificables."""
    if not ruta.exists() or ruta.stat().st_size < 10000:
        return False
    dur = obtener_duracion_video(ruta)
    return dur >= min_duracion


def _remux_a_mp4(origen: Path, destino: Path) -> bool:
    """Remuxea o transcodifica un archivo de video a un MP4 limpio sin audio."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    if not ffmpeg or not origen.exists():
        return False
    cmd = [
        ffmpeg, "-y",
        "-i", str(origen),
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(destino)
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return es_video_valido(destino)
    except Exception:
        return False


import re
import urllib.parse
import urllib3
import numpy as np
from PIL import Image

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Términos y canales que se penalizan o rechazan en YouTube por riesgo de Content ID o texto quemado
_TERMINOS_PENALIZADOS_YT = (
    "top", "scary", "subscribe", "#shorts", "shorts", "compilation", "compilacion", "compilación",
    "reaction", "reaccion", "reacción", "reacts", "tiktok", "subtitulado", "con subtitulos",
    "countdown", "watchmojo", "chills", "nuke's top", "slapped ham", "bizarrebu", "dross",
    "try not to", "caught on camera compilation", "lyrics", "gameplay",
)

_CANALES_EXCLUIDOS_YT = (
    "chills", "top15s", "nuke's top 5", "slapped ham", "bizarrebu", "watchmojo", "mojo",
    "be amazed", "mostamazingtop10", "react", "fbe", "drossrotzank", "tiktok compilation",
)


def analizar_calidad_visual_clip(
    ruta_mp4: Path,
    formato: str = "16:9",
    min_yavg: float = 25.0,
    es_fuente_youtube: bool = False,
) -> tuple[bool, str, dict]:
    """Analiza 3-4 cuadros del clip con FFmpeg (signalstats YAVG + bordes de alto contraste / OCR opcional):
    - Rechaza videos verticales en 16:9, y horizontales en 9:16 salvo que sean HD (>=1280x720) y recortables.
    - Rechaza si la luminancia media es muy baja (signalstats YAVG < ~25).
    - Detecta texto quemado grande o marcas de agua intensas en centro y esquinas.
    Devuelve (aprobado, motivo, metricas)."""
    if not es_video_valido(ruta_mp4):
        return False, "archivo de video inválido o corrupto", {}

    ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
    w, h, dur = obtener_dimensiones_video(ruta_mp4)
    metricas: dict = {"width": w, "height": h, "duracion": round(dur, 2), "yavg": 0.0}

    # 1. Filtro estricto de orientación / relación de aspecto
    if w > 0 and h > 0:
        ratio = w / float(h)
        if formato == "16:9" and w < h:
            return False, f"video vertical ({w}x{h}) descartado para formato horizontal 16:9", metricas
        if formato == "9:16" and w > h:
            if w < 1280 or h < 720 or ratio > 1.85:
                return (
                    False,
                    f"video horizontal ({w}x{h}, ratio={ratio:.2f}) sin resolución HD suficiente para recorte limpio 9:16",
                    metricas,
                )

    # 2. Analizar 4 cuadros con FFmpeg signalstats (YAVG)
    step = max(0.4, dur / 4.5) if dur > 0 else 1.0
    cmd_sig = [
        ffmpeg, "-hide_banner", "-loglevel", "info",
        "-i", str(ruta_mp4),
        "-vf", f"fps=1/{step:.2f},signalstats,metadata=print:file=-",
        "-frames:v", "4",
        "-f", "null", "-",
    ]
    yavg_vals: list[float] = []
    try:
        res_sig = subprocess.run(cmd_sig, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        salida_sig = (res_sig.stdout or "") + "\n" + (res_sig.stderr or "")
        for m in re.finditer(r"lavfi\.signalstats\.YAVG=(\d+(?:\.\d+)?)", salida_sig):
            yavg_vals.append(float(m.group(1)))
    except Exception:
        pass

    # Extraer hasta 4 cuadros reales para verificación de luminancia, bordes de alto contraste y OCR ligero opcional
    fracciones = (0.18, 0.42, 0.66, 0.85)
    cuadros_gris: list[np.ndarray] = []
    textos_ocr: list[str] = []

    tiene_pytesseract = False
    try:
        import pytesseract  # type: ignore
        tiene_pytesseract = True
    except Exception:
        pass

    for idx_f, frac in enumerate(fracciones):
        t_sample = max(0.1, round(dur * frac, 2)) if dur > 0.5 else 0.1
        tmp_png = ruta_mp4.parent / f".tmp_frame_{ruta_mp4.stem}_{idx_f}.png"
        try:
            cmd_f = [
                ffmpeg, "-y", "-ss", f"{t_sample:.2f}",
                "-i", str(ruta_mp4),
                "-frames:v", "1",
                "-vf", "scale=640:360",
                str(tmp_png),
            ]
            subprocess.run(cmd_f, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if tmp_png.exists() and tmp_png.stat().st_size > 200:
                with Image.open(tmp_png) as im:
                    gris = np.asarray(im.convert("L"), dtype=np.float32)
                    cuadros_gris.append(gris)
                    if tiene_pytesseract and es_fuente_youtube:
                        try:
                            import pytesseract  # type: ignore
                            txt_det = pytesseract.image_to_string(im.convert("L")).strip()
                            palabras_ocr = re.findall(r"[A-Za-z0-9]{3,}", txt_det)
                            if len(palabras_ocr) >= 2:
                                textos_ocr.append(" ".join(palabras_ocr[:5]))
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            tmp_png.unlink(missing_ok=True)

    if not yavg_vals and cuadros_gris:
        yavg_vals = [float(np.mean(c)) for c in cuadros_gris]

    yavg_medio = float(np.mean(yavg_vals)) if yavg_vals else 50.0
    metricas["yavg"] = round(yavg_medio, 1)

    if yavg_medio < min_yavg:
        return (
            False,
            f"luminancia media muy baja en {len(yavg_vals) or 4} cuadros (signalstats YAVG={yavg_medio:.1f} < {min_yavg})",
            metricas,
        )

    # 3. Detección de texto quemado o marcas de agua grandes (OCR ligero o bordes de alto contraste en centro/esquinas)
    if textos_ocr and len(textos_ocr) >= 2:
        metricas["ocr_detectado"] = textos_ocr[:2]
        return (
            False,
            f"texto quemado / subtítulos detectados por OCR en cuadros ({textos_ocr[0][:40]})",
            metricas,
        )

    if cuadros_gris:
        scores_sub_band: list[float] = []
        bordes_esquinas: list[np.ndarray] = []
        for g in cuadros_gris:
            gh, gw = g.shape
            gx = np.abs(np.diff(g, axis=1))
            # Banda central/inferior típica de subtítulos quemados y carteles de canales de terror/tops (y: 45% a 88%, x: 15% a 85%)
            y1, y2 = int(gh * 0.45), int(gh * 0.88)
            x1, x2 = int(gw * 0.15), int(gw * 0.85)
            roi_g = g[y1:y2, x1:x2]
            roi_gx = gx[y1:y2, x1:x2]
            # El texto quemado combina trazos muy brillantes (Y>220) junto a bordes negros duros (|dI/dx|>115)
            p_brillante = float(np.mean(roi_g > 222.0))
            p_oscuro = float(np.mean(roi_g < 35.0))
            p_borde_duro = float(np.mean(roi_gx > 115.0))
            if 0.015 <= p_brillante <= 0.28 and p_oscuro >= 0.05:
                scores_sub_band.append(p_borde_duro)
            else:
                scores_sub_band.append(0.0)

            # Esquina superior derecha e inferior derecha para detectar marcas de agua estáticas grandes
            c_tr = (gx[: int(gh * 0.20), int(gw * 0.72) :] > 105.0).astype(np.float32)
            bordes_esquinas.append(c_tr)

        umbral_texto = 0.055 if es_fuente_youtube else 0.085
        cuadros_con_texto = sum(1 for s in scores_sub_band if s > umbral_texto)
        metricas["edge_text_score"] = round(float(max(scores_sub_band, default=0.0)), 4)

        if cuadros_con_texto >= 2:
            return (
                False,
                f"detectado texto quemado de alto contraste en centro/subtítulos (score={metricas['edge_text_score']:.3f})",
                metricas,
            )

        if len(bordes_esquinas) >= 3 and es_fuente_youtube:
            # Si exactamente los mismos píxeles de alto contraste permanecen inmóviles en la esquina en todos los cuadros
            persistencia_esquina = float(np.mean(np.prod(np.stack(bordes_esquinas, axis=0), axis=0)))
            metricas["watermark_persistence"] = round(persistencia_esquina, 4)
            if persistencia_esquina > 0.032:
                return (
                    False,
                    f"detectada marca de agua estática grande en esquina (persistencia={persistencia_esquina:.3f})",
                    metricas,
                )

    return True, "OK", metricas


def buscar_youtube_ids(query: str, max_results: int = 5, solo_creative_commons: bool = False) -> list[str]:
    """Busca videos en YouTube mediante scrape limpio. Si solo_creative_commons=True, aplica el filtro CC de YouTube."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    q = urllib.parse.quote(query)
    sp_param = "&sp=EgIwAQ%253D%253D" if solo_creative_commons else ""
    url = f"https://www.youtube.com/results?search_query={q}{sp_param}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        # Ignorar enlaces a /shorts/ y extraer únicamente watch?v=
        vids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", r.text)
        shorts_ids = set(re.findall(r"/shorts/([a-zA-Z0-9_-]{11})", r.text))
        limpios = [v for v in dict.fromkeys(vids) if v not in shorts_ids]
        return limpios[:max_results]
    except Exception:
        return []


# ------------------------------------------------------------------ yt-dlp
# Estado de YouTube durante la corrida actual (circuit breaker).
_YT_ESTADO = {"bloqueado": False, "motivo": "", "aviso_cookies": False}
_MARCAS_BLOQUEO = ("sign in to confirm", "not a bot", "http error 429", "too many requests")


def youtube_disponible() -> bool:
    return not _YT_ESTADO["bloqueado"]


def opciones_ytdlp_base() -> dict:
    """Opciones comunes de yt-dlp. Añade --cookies si YTDLP_COOKIES apunta a un archivo existente."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
    }
    ruta = config.YTDLP_COOKIES
    if ruta is not None:
        if ruta.is_file():
            opts["cookiefile"] = str(ruta)
            if not _YT_ESTADO["aviso_cookies"]:
                print(f"   🍪 yt-dlp usando cookies de: {ruta}")
                _YT_ESTADO["aviso_cookies"] = True
        elif not _YT_ESTADO["aviso_cookies"]:
            print(f"   ⚠️ YTDLP_COOKIES apunta a un archivo inexistente: {ruta} (se ignora)")
            _YT_ESTADO["aviso_cookies"] = True
    return opts


def registrar_error_youtube(error: Exception) -> None:
    """Si el error es un bloqueo anti-bot/rate-limit, apaga YouTube para el resto de la corrida."""
    msg = str(error).lower()
    if _YT_ESTADO["bloqueado"] or not any(m in msg for m in _MARCAS_BLOQUEO):
        return
    _YT_ESTADO["bloqueado"] = True
    _YT_ESTADO["motivo"] = str(error).strip().splitlines()[0][:200]
    sugerencia = (
        "Las cookies configuradas no fueron aceptadas; exporta unas nuevas."
        if "cookiefile" in opciones_ytdlp_base()
        else "Define YTDLP_COOKIES con la ruta a un cookies.txt para habilitarlo."
    )
    print("   ⛔ YouTube bloqueó la descarga (verificación anti-bot). "
          "Se desactiva YouTube por el resto de la corrida y se usará stock (Pexels/Pixabay).")
    print(f"      Motivo: {_YT_ESTADO['motivo']}")
    print(f"      {sugerencia}")


def evaluar_metadatos_youtube(
    info: dict,
    formato: str = "16:9",
    es_busqueda_cc: bool = False,
) -> tuple[bool, float, str]:
    """Evalúa metadatos de un video de YouTube antes de descargarlo para evitar Content ID,
    Shorts, compilaciones, canales de reacción/terror con texto quemado y orientaciones incorrectas.
    Devuelve (aceptado, score, motivo_o_detalle)."""
    titulo = str(info.get("title") or "").strip()
    titulo_low = titulo.lower()
    canal = str(info.get("uploader") or info.get("channel") or "").strip()
    canal_low = canal.lower()
    url_web = str(info.get("webpage_url") or info.get("original_url") or "").lower()
    licencia = str(info.get("license") or "").strip()
    w = int(info.get("width") or 0)
    h = int(info.get("height") or 0)
    dur = float(info.get("duration") or 0.0)

    # 1. Excluir Shorts explícitamente
    if "/shorts/" in url_web or "#shorts" in titulo_low or "#short" in titulo_low:
        return False, -100.0, f"es un YouTube Short ('{titulo[:55]}')"
    if 0 < dur <= 61 and w > 0 and h > 0 and h > w:
        return False, -100.0, f"duración/aspecto de Short vertical ({w}x{h}, {dur:.0f}s)"

    # 2. Verificar orientación según el formato del proyecto
    if w > 0 and h > 0:
        ratio = w / float(h)
        if formato == "16:9" and w < h:
            return False, -100.0, f"video vertical ({w}x{h}) descartado en formato 16:9"
        if formato == "9:16" and w > h:
            if w < 1280 or h < 720 or ratio > 1.85:
                return False, -100.0, f"video horizontal ({w}x{h}) que no recorta con calidad en 9:16"

    # 3. Excluir canales de reacción, compilaciones y canales de terror/rankings que queman texto
    for ch_ban in _CANALES_EXCLUIDOS_YT:
        if ch_ban in canal_low:
            return False, -100.0, f"canal excluido de compilaciones/reacción/terror ('{canal}')"

    # 4. Penalizar/rechazar títulos con TOP, scary, subscribe, #shorts, compilation, reaction, etc.
    score = 20.0
    penalizaciones: list[str] = []
    for term in ("top", "scary", "subscribe", "#shorts", "compilation", "compilacion", "compilación", "reaction", "reaccion", "reacción"):
        patron = re.compile(rf"(?:^|\W){re.escape(term)}(?:$|\W)", re.IGNORECASE)
        if patron.search(titulo_low):
            penalizaciones.append(term.upper())
            score -= 25.0

    for term_extra in _TERMINOS_PENALIZADOS_YT:
        if term_extra in titulo_low and term_extra.upper() not in penalizaciones:
            penalizaciones.append(term_extra)
            score -= 20.0

    if penalizaciones:
        return (
            False,
            score,
            f"título penalizado/excluido por términos {penalizaciones} ('{titulo[:60]}')",
        )

    # 5. Bonificación por licencia Creative Commons
    es_cc = es_busqueda_cc or ("creative commons" in licencia.lower()) or ("reuse allowed" in licencia.lower())
    if es_cc:
        score += 30.0

    return True, score, f"título='{titulo[:55]}', canal='{canal[:30]}', licencia='{'CC-BY' if es_cc else (licencia or 'YouTube Standard')}', res={w}x{h}"


def descargar_clip_youtube(
    query: str,
    destino_mp4: Path,
    inicio_s: int = 10,
    duracion_s: int = 15,
    clips_usados: Optional[set[str]] = None,
    formato: str = "16:9",
    rechazos_log: Optional[list[dict]] = None,
) -> Optional[str]:
    """Busca en YouTube (priorizando Creative Commons), filtra metadatos/orientación/títulos,
    descarga un fragmento y analiza 4 cuadros con FFmpeg (luminancia YAVG y texto quemado).
    Devuelve la clave del video usado ('yt:<id>') si tuvo éxito, o None."""
    if not youtube_disponible():
        return None

    # Priorizar videos Creative Commons primero y luego búsqueda documental limpia
    vids_cc = buscar_youtube_ids(query, max_results=3, solo_creative_commons=True)
    vids_std = buscar_youtube_ids(f"{query} archival footage -shorts -compilation -top", max_results=4, solo_creative_commons=False)
    if not vids_std:
        vids_std = buscar_youtube_ids(query, max_results=4, solo_creative_commons=False)

    candidatos_yt: list[tuple[str, bool]] = []
    vistos_id: set[str] = set()
    for v in vids_cc:
        if v not in vistos_id:
            vistos_id.add(v)
            candidatos_yt.append((v, True))
    for v in vids_std:
        if v not in vistos_id:
            vistos_id.add(v)
            candidatos_yt.append((v, False))

    if not candidatos_yt:
        return None

    temp_prefix = destino_mp4.parent / f"tmp_yt_{destino_mp4.stem}"
    info_opts = {
        **opciones_ytdlp_base(),
        "skip_download": True,
        "extract_flat": False,
    }
    ydl_opts = {
        **opciones_ytdlp_base(),
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "outtmpl": str(temp_prefix.with_suffix(".%(ext)s")),
        "download_ranges": yt_dlp.utils.download_range_func(None, [(inicio_s, inicio_s + duracion_s)]),
        "force_keyframes_at_cuts": True,
    }

    for vid_id, es_cc in candidatos_yt[:5]:
        if not youtube_disponible():
            break
        clave_yt = f"yt:{vid_id}"
        if clips_usados is not None and clave_yt in clips_usados:
            continue
        url = f"https://www.youtube.com/watch?v={vid_id}"

        try:
            # Paso A: Inspeccionar metadatos antes de bajar el video
            with yt_dlp.YoutubeDL(info_opts) as ydl_info:
                info = ydl_info.extract_info(url, download=False) or {}
            aceptado_meta, score_meta, motivo_meta = evaluar_metadatos_youtube(
                info, formato=formato, es_busqueda_cc=es_cc
            )
            if not aceptado_meta:
                print(f"      🚫 YouTube [{clave_yt}] rechazado en pre-filtro: {motivo_meta}")
                if rechazos_log is not None:
                    rechazos_log.append({
                        "fuente": "YouTube",
                        "candidato": clave_yt,
                        "url": url,
                        "motivo": f"Pre-filtro metadatos: {motivo_meta}",
                    })
                continue

            # Paso B: Descargar el rango solicitado
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            candidatos_arch = list(destino_mp4.parent.glob(f"{temp_prefix.name}.*"))
            descargado_ok = False
            for f in candidatos_arch:
                if f.is_file():
                    exito_remux = _remux_a_mp4(f, destino_mp4)
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass
                    if exito_remux:
                        descargado_ok = True
                        break

            if not descargado_ok and destino_mp4.exists() and es_video_valido(destino_mp4):
                descargado_ok = True

            if not descargado_ok:
                continue

            # Paso C: Analizar 3-4 cuadros con FFmpeg (signalstats YAVG < 25 y texto quemado / marca de agua)
            aprobado_vis, motivo_vis, metricas_vis = analizar_calidad_visual_clip(
                destino_mp4, formato=formato, min_yavg=25.0, es_fuente_youtube=True
            )
            if not aprobado_vis:
                print(f"      🚫 YouTube [{clave_yt}] rechazado tras análisis FFmpeg: {motivo_vis}")
                destino_mp4.unlink(missing_ok=True)
                if rechazos_log is not None:
                    rechazos_log.append({
                        "fuente": "YouTube",
                        "candidato": clave_yt,
                        "url": url,
                        "motivo": f"Post-descarga FFmpeg: {motivo_vis} ({motivo_meta})",
                    })
                continue

            if clips_usados is not None:
                clips_usados.add(clave_yt)
            return f"{clave_yt} ({'CC-BY' if es_cc else 'Standard'}, YAVG={metricas_vis.get('yavg', 0)})"
        except Exception as e:
            registrar_error_youtube(e)
            for f in destino_mp4.parent.glob(f"{temp_prefix.name}.*"):
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    if destino_mp4.exists() and not es_video_valido(destino_mp4):
        destino_mp4.unlink(missing_ok=True)
    return None


# ------------------------------------------------------------------ curaduría y puntuación de stock (Pexels / Pixabay)
_STOPWORDS_EN = {
    "the", "and", "with", "from", "into", "over", "under", "for", "that", "this",
    "are", "was", "were", "been", "have", "has", "had", "very", "shot", "video", "clip", "footage",
}

_MOOD_DEFAULTS: dict[str, dict[str, set[str]]] = {
    "misterio": {
        "mood": {
            "dark", "night", "shadow", "shadows", "mystery", "mysterious", "fog", "foggy",
            "abandoned", "old", "ancient", "vintage", "archive", "corridor", "eerie", "gloomy",
            "silhouette", "candle", "dusty", "secret", "creepy", "cinematic", "forest", "moon",
        },
        "avoid": {
            "beach", "sunny", "summer", "vacation", "tropical", "resort", "party", "dancing",
            "smiling", "happy", "comedy", "cartoon", "kids", "wedding", "shopping", "escalator",
            "cheerful", "bright", "pool", "surf", "bikini", "picnic", "festival", "carnival",
        },
    },
    "tension": {
        "mood": {
            "dark", "night", "danger", "emergency", "storm", "shadow", "warning", "security",
            "surveillance", "cinematic", "tense", "crime", "police", "alarm", "corridor", "glitch",
        },
        "avoid": {
            "beach", "sunny", "summer", "vacation", "tropical", "resort", "party", "happy",
            "comedy", "cartoon", "relaxing", "spa", "escalator", "smiling", "cheerful", "wedding",
        },
    },
    "epica": {
        "mood": {"cinematic", "dramatic", "epic", "aerial", "storm", "horizon", "monumental", "mountain"},
        "avoid": {"cartoon", "comedy", "funny", "meme", "escalator", "shopping"},
    },
    "curiosidad": {
        "mood": {"cinematic", "macro", "detail", "history", "science", "archive", "museum", "ancient"},
        "avoid": {"cartoon", "meme", "party", "bikini", "clubbing"},
    },
    "calma": {
        "mood": {"cinematic", "slow", "nature", "calm", "soft", "ambient", "clouds", "water"},
        "avoid": {"explosion", "horror", "blood", "panic", "riot"},
    },
}


def _tokenizar(texto: str) -> set[str]:
    palabras = re.findall(r"[a-z0-9]+", (texto or "").lower())
    return {w for w in palabras if len(w) >= 3 and w not in _STOPWORDS_EN}


def _coincide_termino(token_cand: set[str], termino: str) -> bool:
    t = termino.lower().strip()
    if not t:
        return False
    if t in token_cand:
        return True
    raiz = t.rstrip("s")
    if len(raiz) >= 4:
        return any(tc == raiz or tc.startswith(raiz) or raiz.startswith(tc) for tc in token_cand if len(tc) >= 4)
    return False


def _consultas_escena(esc: Escena) -> list[str]:
    """Construye la lista ordenada de consultas en inglés para una escena."""
    base: list[str] = []
    for q in getattr(esc, "broll_queries_en", []) or []:
        q_clean = (q or "").strip()
        if q_clean and q_clean not in base:
            base.append(q_clean)
    if esc.broll_query_en and esc.broll_query_en.strip() not in base:
        base.insert(0, esc.broll_query_en.strip())

    mood_kws = [w.strip() for w in (getattr(esc, "broll_mood_keywords", []) or []) if w.strip()]
    if not mood_kws:
        mood_kws = ["dark", "cinematic"] if esc.music_mood in ("misterio", "tension") else ["cinematic"]

    expandidas: list[str] = list(base)
    # Añadir versión corta (núcleo de 2-3 palabras significativas) + combinación con mood
    for q in base[:2]:
        palabras = [w for w in re.findall(r"[a-zA-Z0-9]+", q) if len(w) > 3 and w.lower() not in _STOPWORDS_EN]
        if len(palabras) >= 2:
            nucleo = " ".join(palabras[:2])
            if nucleo not in expandidas:
                expandidas.append(nucleo)
            con_mood = f"{nucleo} {mood_kws[0]}"
            if con_mood not in expandidas:
                expandidas.append(con_mood)

    # Último recurso atmosférico acorde al mood (jamás 'technology' genérico si es misterio)
    fallback_mood = {
        "misterio": "dark mysterious fog night",
        "tension": "dark corridor shadow night",
        "epica": "dramatic clouds storm aerial",
        "curiosidad": "ancient archive old book",
        "calma": "calm night sky stars",
    }.get(esc.music_mood, "dark cinematic night")
    if fallback_mood not in expandidas:
        expandidas.append(fallback_mood)
    return expandidas


def _buscar_candidatos_pexels(queries: list[str], per_page: int = 10) -> list[dict]:
    """Consulta Pexels Videos API y devuelve candidatos con tags, duración y URL."""
    if not config.PEXELS_API_KEY:
        return []
    url = "https://api.pexels.com/videos/search"
    headers = {**HTTP_HEADERS, "Authorization": config.PEXELS_API_KEY}
    vistos: set[str] = set()
    resultados: list[dict] = []

    for q in queries[:4]:
        params = {"query": q, "per_page": per_page, "orientation": "landscape"}
        try:
            r = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not r.ok:
                continue
            for v in r.json().get("videos", []):
                vid_id = str(v.get("id", ""))
                if not vid_id or vid_id in vistos:
                    continue
                files = v.get("video_files", [])
                mp4_files = [
                    f for f in files
                    if f.get("link") and (f.get("file_type") == "video/mp4" or str(f.get("link", "")).endswith(".mp4"))
                ]
                if not mp4_files:
                    continue
                # Preferir resolución HD <= 1080p
                mp4_files.sort(
                    key=lambda f: (
                        1 if 720 <= (f.get("height") or 0) <= 1080 else 0,
                        f.get("height") or 0,
                    ),
                    reverse=True,
                )
                elegido = mp4_files[0]
                slug_url = v.get("url", "")
                m_slug = re.search(r"/video/([a-z0-9-]+)-\d+/?", slug_url.lower())
                slug_tags = m_slug.group(1).replace("-", " ") if m_slug else ""
                tags_str = f"{slug_tags} {q}".strip()
                vistos.add(vid_id)
                resultados.append({
                    "tipo": "video",
                    "fuente": "Pexels",
                    "id": vid_id,
                    "key": f"pexels:{vid_id}",
                    "url": elegido["link"],
                    "tags": tags_str,
                    "duracion": float(v.get("duration") or 0.0),
                    "query_origen": q,
                    "creditos": f"Pexels Video ID {vid_id}",
                })
        except Exception:
            continue
    return resultados


def _buscar_candidatos_pixabay(queries: list[str], per_page: int = 12) -> list[dict]:
    """Consulta Pixabay Videos API para las consultas de la escena y devuelve todos los candidatos con sus tags y duración."""
    if not config.PIXABAY_API_KEY:
        return []
    url = "https://pixabay.com/api/videos/"
    vistos: set[str] = set()
    resultados: list[dict] = []

    for q in queries[:5]:
        params = {"key": config.PIXABAY_API_KEY, "q": q, "per_page": per_page}
        try:
            r = requests.get(url, params=params, headers=HTTP_HEADERS, verify=False, timeout=10)
            if not r.ok:
                continue
            for h in r.json().get("hits", []):
                vid_id = str(h.get("id", ""))
                if not vid_id or vid_id in vistos:
                    continue
                vids = h.get("videos", {})
                opt = vids.get("large") or vids.get("medium") or vids.get("small")
                if not opt or not opt.get("url"):
                    continue
                vistos.add(vid_id)
                resultados.append({
                    "tipo": "video",
                    "fuente": "Pixabay",
                    "id": vid_id,
                    "key": f"pixabay:{vid_id}",
                    "url": opt["url"],
                    "tags": str(h.get("tags") or ""),
                    "duracion": float(h.get("duration") or 0.0),
                    "query_origen": q,
                    "creditos": f"Pixabay Video ID {vid_id}",
                })
        except Exception:
            continue
    return resultados


def _puntuar_y_filtrar_candidatos(
    candidatos: list[dict],
    esc: Escena,
    dur_objetivo: float,
    clips_usados: set[str],
    rechazos_log: Optional[list[dict]] = None,
) -> list[dict]:
    """Puntúa candidatos de stock por coincidencia de tags, mood y duración.
    Rechaza tajantemente clips ya usados o cuyos tags choquen con el mood / avoid_keywords."""
    mood_cfg = _MOOD_DEFAULTS.get(esc.music_mood, _MOOD_DEFAULTS["misterio"])

    # Tokens positivos de las consultas de la escena
    texto_queries = " ".join(
        ([esc.broll_query_en] if esc.broll_query_en else [])
        + (getattr(esc, "broll_queries_en", []) or [])
    )
    tokens_query = _tokenizar(texto_queries)
    tokens_primaria = _tokenizar(
        (esc.broll_queries_en[0] if getattr(esc, "broll_queries_en", None) else esc.broll_query_en) or ""
    )

    tokens_mood = set(mood_cfg["mood"]) | _tokenizar(" ".join(getattr(esc, "broll_mood_keywords", []) or []))
    tokens_avoid_raw = set(mood_cfg["avoid"]) | _tokenizar(" ".join(getattr(esc, "broll_avoid_keywords", []) or []))
    tokens_avoid = {t for t in tokens_avoid_raw if t not in tokens_query}

    evaluados: list[dict] = []
    for cand in candidatos:
        key = cand.get("key") or f"{cand.get('fuente')}:{cand.get('id')}"
        if key in clips_usados or cand.get("url") in clips_usados:
            if rechazos_log is not None:
                rechazos_log.append({
                    "fuente": cand.get("fuente", "Stock"),
                    "candidato": key,
                    "url": cand.get("url", ""),
                    "motivo": "Clip ya utilizado en una escena anterior (no repetir clips)",
                })
            continue

        tokens_tags = _tokenizar(cand.get("tags", ""))
        # 1. Rechazo estricto si choca con términos evitados / mood opuesto
        choques = [av for av in tokens_avoid if _coincide_termino(tokens_tags, av)]
        if choques:
            if rechazos_log is not None:
                rechazos_log.append({
                    "fuente": cand.get("fuente", "Stock"),
                    "candidato": key,
                    "url": cand.get("url", ""),
                    "motivo": f"Choque con mood / avoid_keywords {choques[:3]} en tags '{cand.get('tags', '')[:50]}'",
                })
            continue

        # 2. Puntuación por coincidencia con términos de búsqueda
        hits_primarios = sum(1 for qt in tokens_primaria if _coincide_termino(tokens_tags, qt))
        hits_secundarios = sum(1 for qt in (tokens_query - tokens_primaria) if _coincide_termino(tokens_tags, qt))
        hits_mood = sum(1 for mt in tokens_mood if _coincide_termino(tokens_tags, mt))

        score = (hits_primarios * 14.0) + (hits_secundarios * 8.0) + (hits_mood * 5.0)

        # 3. Puntuación por duración respecto al audio de la escena
        dur = float(cand.get("duracion") or 0.0)
        if dur >= dur_objetivo:
            score += 15.0
        elif dur >= max(5.0, dur_objetivo * 0.6):
            score += 6.0
        elif 0.0 < dur < 4.0:
            score -= 15.0

        matches_relevantes = hits_primarios + hits_secundarios + hits_mood
        item = {
            **cand,
            "score": round(score, 2),
            "hits_query": hits_primarios + hits_secundarios,
            "hits_mood": hits_mood,
            "matches_relevantes": matches_relevantes,
        }
        evaluados.append(item)

    evaluados.sort(
        key=lambda x: (
            1 if x["hits_query"] > 0 else (0.5 if x["matches_relevantes"] > 0 else 0),
            x["score"],
            x.get("duracion", 0.0),
        ),
        reverse=True,
    )
    return evaluados


def _buscar_pixabay_video(query: str) -> Optional[dict]:
    """Wrapper de compatibilidad para búsqueda simple en Pixabay."""
    esc_dummy = Escena(
        id=0, acto="contexto", voz="", pose="neutro", host_visible=False,
        host_lado="izquierda", broll_query_en=query, broll_queries_en=[query],
        broll_descripcion="", texto_pantalla="", sfx="ninguno", music_mood="misterio",
    )
    cands = _buscar_candidatos_pixabay(_consultas_escena(esc_dummy))
    if not cands:
        return None
    untuados = _puntuar_y_filtrar_candidatos(cands, esc_dummy, 8.0, set())
    return untuados[0] if untuados else cands[0]


def descargar_archivo_directo(url: str, destino: Path) -> bool:
    temp_dest = destino.with_suffix(".tmp_download")
    try:
        with requests.get(url, stream=True, headers=HTTP_HEADERS, verify=False, timeout=30) as r:
            r.raise_for_status()
            with open(temp_dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        if es_video_valido(temp_dest):
            temp_dest.replace(destino)
            return True
        else:
            temp_dest.unlink(missing_ok=True)
            return False
    except Exception:
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)
        return False


def _seleccionar_mejor_stock(
    esc: Escena,
    dur_audio: float,
    clips_usados: set[str],
    rechazos_log: Optional[list[dict]] = None,
) -> list[dict]:
    """Busca y puntúa candidatos con licencia segura en orden: Pexels -> Pixabay.
    Prioriza clips con duración >= dur_audio y devuelve candidatos que NO chocan con el mood ni están repetidos."""
    queries = _consultas_escena(esc)
    candidatos_pexels = _buscar_candidatos_pexels(queries) if config.PEXELS_API_KEY else []
    evaluados_pexels = _puntuar_y_filtrar_candidatos(
        candidatos_pexels, esc, dur_audio, clips_usados, rechazos_log=rechazos_log
    )

    candidatos_pixabay = _buscar_candidatos_pixabay(queries)
    evaluados_pixabay = _puntuar_y_filtrar_candidatos(
        candidatos_pixabay, esc, dur_audio, clips_usados, rechazos_log=rechazos_log
    )

    con_query = [c for c in (evaluados_pexels + evaluados_pixabay) if c["hits_query"] > 0]
    con_query.sort(
        key=lambda c: (
            1 if float(c.get("duracion") or 0.0) >= dur_audio else 0,
            c["score"],
            1 if c["fuente"] == "Pexels" else 0,
            float(c.get("duracion") or 0.0),
        ),
        reverse=True,
    )

    sin_query = [c for c in (evaluados_pexels + evaluados_pixabay) if c["hits_query"] == 0]
    sin_query.sort(
        key=lambda c: (
            1 if float(c.get("duracion") or 0.0) >= dur_audio else 0,
            c["score"],
            1 if c["fuente"] == "Pexels" else 0,
            float(c.get("duracion") or 0.0),
        ),
        reverse=True,
    )

    return con_query + sin_query


def _concatenar_clips_broll(clips: list[Path], destino: Path) -> bool:
    """Normaliza a 1920x1080 30fps (sin deformar aspecto) y encadena 2 o más clips distintos en un solo MP4 sin audio."""
    ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
    validos = [c for c in clips if c.exists() and es_video_valido(c)]
    if len(validos) < 2:
        return False

    temp_concat = destino.with_suffix(".chained_tmp.mp4")
    inputs: list[str] = []
    filtros: list[str] = []
    etiquetas: list[str] = []

    for idx, c in enumerate(validos):
        inputs += ["-i", str(c)]
        filtros.append(
            f"[{idx}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(1920-iw)/2:(1080-ih)/2:color=black,setsar=1,fps=30,format=yuv420p[v{idx}]"
        )
        etiquetas.append(f"[v{idx}]")

    filtro_str = f"{';'.join(filtros)};{''.join(etiquetas)}concat=n={len(validos)}:v=1:a=0[vout]"
    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filtro_str,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(temp_concat),
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if es_video_valido(temp_concat):
            temp_concat.replace(destino)
            return True
    except Exception:
        pass
    temp_concat.unlink(missing_ok=True)
    return False


def _completar_clip_corto_con_stock(
    esc: Escena,
    destino_clip: Path,
    dur_audio: float,
    clips_usados: set[str],
    candidatos_precalculados: Optional[list[dict]] = None,
) -> list[str]:
    """Si el clip descargado dura menos que la escena, descarga 1 (o 2) clips adicionales DISTINTOS
    y los encadena para cubrir la duración sin repetir jamás el mismo clip en loop."""
    t_actual = obtener_duracion_video(destino_clip)
    if t_actual <= 0.0 or t_actual + 0.25 >= dur_audio:
        return []

    faltante = max(3.0, dur_audio - t_actual)
    candidatos = (
        [c for c in candidatos_precalculados if c["key"] not in clips_usados and c["url"] not in clips_usados]
        if candidatos_precalculados is not None
        else _seleccionar_mejor_stock(esc, faltante, clips_usados)
    )
    if not candidatos:
        return []

    partes_extra: list[Path] = []
    claves_extra: list[str] = []
    dur_acum = t_actual

    try:
        for cand in candidatos:
            if dur_acum + 0.25 >= dur_audio or len(partes_extra) >= 2:
                break
            if cand["key"] in clips_usados or cand["url"] in clips_usados:
                continue
            tmp_extra = destino_clip.parent / f"tmp_extra_{esc.id:03d}_{len(partes_extra)+1}.mp4"
            if descargar_archivo_directo(cand["url"], tmp_extra):
                aprobado, _, _ = analizar_calidad_visual_clip(tmp_extra, formato="16:9", min_yavg=25.0)
                d_ext = obtener_duracion_video(tmp_extra)
                if aprobado and d_ext > 0.5:
                    partes_extra.append(tmp_extra)
                    claves_extra.append(cand["key"])
                    clips_usados.add(cand["key"])
                    clips_usados.add(cand["url"])
                    dur_acum += d_ext
                else:
                    tmp_extra.unlink(missing_ok=True)

        if partes_extra:
            if _concatenar_clips_broll([destino_clip, *partes_extra], destino_clip):
                t_nueva = obtener_duracion_video(destino_clip)
                print(
                    f"      🔗 Escena {esc.id}: Clip inicial corto ({t_actual:.1f}s < {dur_audio:.1f}s) "
                    f"-> encadenado con {len(partes_extra)} clip(s) distinto(s) {claves_extra} (total: {t_nueva:.1f}s)."
                )
                return claves_extra
    finally:
        for p_tmp in partes_extra:
            p_tmp.unlink(missing_ok=True)

    return []


def generar_reporte_broll_md(
    ruta_reporte: Path,
    tema: str,
    formato: str,
    creditos: list[dict],
    rechazos_por_escena: dict[int, list[dict]],
) -> None:
    """Escribe b_roll/broll_reporte.md detallando la selección final y el motivo exacto de cada candidato rechazado."""
    total_rechazos = sum(len(v) for v in rechazos_por_escena.values())
    lineas = [
        f"# 📋 Reporte de Curaduría y Filtrado Anti-Content ID de B-Roll",
        f"- **Proyecto:** `{tema}`",
        f"- **Formato:** `{formato}`",
        f"- **Escenas procesadas:** `{len(creditos)}`",
        f"- **Total de candidatos rechazados:** `{total_rechazos}`",
        "",
        "## 1. Resumen de Selección por Escena",
        "",
        "| Escena | Fuente Elegida | Detalle / Licencia / Métricas | Duración (s) | Rechazos en Escena |",
        "| :---: | :--- | :--- | :---: | :---: |",
    ]
    for c in creditos:
        eid = c.get("escena", 0)
        n_rej = len(rechazos_por_escena.get(eid, []))
        det = str(c.get("detalle") or "-").replace("|", "/")
        lineas.append(
            f"| {eid} | **{c.get('fuente')}** | `{det}` | {float(c.get('duracion_video') or 0.0):.1f}s | {n_rej} |"
        )

    lineas.append("\n## 2. Registro Detallado de Rechazos por Escena\n")
    for c in creditos:
        eid = c.get("escena", 0)
        rejs = rechazos_por_escena.get(eid, [])
        lineas.append(f"### Escena {eid:02d} — Seleccionado: `{c.get('fuente')}` ({c.get('archivo')})")
        if not rejs:
            lineas.append("- ✅ *Ningún candidato fue rechazado antes de encontrar el clip óptimo.*")
        else:
            for r in rejs:
                lineas.append(
                    f"- ❌ **[{r.get('fuente')}]** `{r.get('candidato')}`: {r.get('motivo')}"
                )
        lineas.append("")

    ruta_reporte.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def etapa_broll(p: Proyecto, duraciones: Optional[dict[int, float]] = None) -> list[dict]:
    """Descarga clips priorizando fuentes con licencia segura (Pexels/Pixabay y YouTube Creative Commons),
    filtrando orientación, títulos/canales riesgosos, luminancia FFmpeg (YAVG < 25) y texto quemado."""
    from .voz import obtener_duracion_wav

    guion = cargar_guion(p)
    carpeta_broll = p.ruta("b_roll")
    carpeta_broll.mkdir(exist_ok=True, parents=True)

    creditos = []
    rechazos_por_escena: dict[int, list[dict]] = {}
    clips_usados: set[str] = set()
    total = len(guion.escenas)
    print(f"🎬 Buscando y curando B-roll para {total} escenas (prioridad licencia segura + filtro anti-Content ID + FFmpeg YAVG)...")

    for i, esc in enumerate(guion.escenas, 1):
        destino_clip = carpeta_broll / f"escena_{esc.id:03d}.mp4"
        rechazos_esc: list[dict] = []
        rechazos_por_escena[esc.id] = rechazos_esc

        dur_audio = (duraciones or {}).get(esc.id)
        if not dur_audio:
            wav_path = p.ruta("voz", f"escena_{esc.id:03d}.wav")
            if wav_path.exists():
                dur_audio = obtener_duracion_wav(wav_path)
            else:
                dur_audio = 10.0

        if destino_clip.exists():
            aprobado_cache, motivo_cache, met_cache = analizar_calidad_visual_clip(
                destino_clip, formato="16:9", min_yavg=25.0
            )
            if aprobado_cache:
                t_vid = obtener_duracion_video(destino_clip)
                print(f"   [{i}/{total}] Escena {esc.id}: Reutilizando clip válido ({destino_clip.name}, {t_vid:.1f}s, YAVG={met_cache.get('yavg')})")
                extras_cache: list[str] = []
                if t_vid + 0.25 < dur_audio:
                    extras_cache = _completar_clip_corto_con_stock(esc, destino_clip, dur_audio, clips_usados)
                    t_vid = obtener_duracion_video(destino_clip)
                creditos.append({
                    "escena": esc.id,
                    "archivo": destino_clip.name,
                    "fuente": "Cache+Chained" if extras_cache else "Cache",
                    "detalle": f"YAVG={met_cache.get('yavg')}, res={met_cache.get('width')}x{met_cache.get('height')}",
                    "duracion_video": t_vid,
                })
                continue
            else:
                print(f"   ⚠️ Escena {esc.id}: Clip en caché rechazado ({motivo_cache}). Re-descargando...")
                rechazos_esc.append({
                    "fuente": "Cache",
                    "candidato": destino_clip.name,
                    "url": "",
                    "motivo": f"Caché invalidado: {motivo_cache}",
                })
                destino_clip.unlink(missing_ok=True)

        queries_esc = _consultas_escena(esc)
        query_yt = queries_esc[0]
        dur_descarga = max(15, int(dur_audio) + 5)
        fuente_usada = "Fallback"
        detalle_clip = ""
        exito = False

        # 1. Priorizar fuentes con licencia segura (Pexels / Pixabay) cuando existe un match relevante de query
        candidatos_stock = _seleccionar_mejor_stock(esc, dur_audio, clips_usados, rechazos_log=rechazos_esc)
        candidatos_stock_fuertes = [c for c in candidatos_stock if c.get("hits_query", 0) > 0 and c.get("score", 0) >= 14.0]

        for cand in candidatos_stock_fuertes:
            if descargar_archivo_directo(cand["url"], destino_clip):
                aprobado_st, motivo_st, met_st = analizar_calidad_visual_clip(
                    destino_clip, formato="16:9", min_yavg=25.0, es_fuente_youtube=False
                )
                if aprobado_st:
                    exito = True
                    fuente_usada = f"{cand['fuente']} (Licencia Segura)"
                    detalle_clip = (
                        f"{cand['key']} (score={cand['score']}, YAVG={met_st.get('yavg')}, "
                        f"res={met_st.get('width')}x{met_st.get('height')}, tags='{cand['tags'][:50]}')"
                    )
                    clips_usados.add(cand["key"])
                    clips_usados.add(cand["url"])
                    print(
                        f"   [{i}/{total}] ✅ Escena {esc.id}: Clip con licencia segura de {cand['fuente']} [{cand['key']}] "
                        f"(score {cand['score']}, YAVG={met_st.get('yavg')}, {cand['duracion']:.1f}s)"
                    )
                    break
                else:
                    destino_clip.unlink(missing_ok=True)
                    rechazos_esc.append({
                        "fuente": cand["fuente"],
                        "candidato": cand["key"],
                        "url": cand["url"],
                        "motivo": f"Post-descarga FFmpeg: {motivo_st}",
                    })

        # 2. Si no hubo match fuerte en Pexels/Pixabay, buscar en YouTube (priorizando Creative Commons y filtro anti-Content ID)
        if not exito and youtube_disponible():
            print(f"   [{i}/{total}] Buscando en YouTube (CC / Archivo filtrado) para Escena {esc.id}: '{query_yt}'...")
            clave_yt = descargar_clip_youtube(
                query_yt,
                destino_clip,
                inicio_s=8,
                duracion_s=dur_descarga,
                clips_usados=clips_usados,
                formato="16:9",
                rechazos_log=rechazos_esc,
            )
            if clave_yt:
                exito = True
                fuente_usada = "YouTube"
                detalle_clip = clave_yt
                print(f"      ✅ Escena {esc.id}: Clip aprobado de YouTube ({clave_yt}).")
            else:
                motivo_fb = "bloqueo anti-bot de YouTube" if not youtube_disponible() else "candidatos de YouTube rechazados por filtro"
                print(f"      ↪️ Escena {esc.id}: Pasando a candidatos secundarios de Pexels/Pixabay ({motivo_fb})...")

        # 3. Probar resto de candidatos de Pexels/Pixabay si YouTube fue rechazado o bloqueado
        if not exito:
            restantes_stock = [c for c in candidatos_stock if c not in candidatos_stock_fuertes]
            for cand in restantes_stock:
                if descargar_archivo_directo(cand["url"], destino_clip):
                    aprobado_st, motivo_st, met_st = analizar_calidad_visual_clip(
                        destino_clip, formato="16:9", min_yavg=25.0, es_fuente_youtube=False
                    )
                    if aprobado_st:
                        exito = True
                        fuente_usada = f"{cand['fuente']} (Fallback Seguro)"
                        detalle_clip = (
                            f"{cand['key']} (score={cand['score']}, YAVG={met_st.get('yavg')}, "
                            f"tags='{cand['tags'][:50]}')"
                        )
                        clips_usados.add(cand["key"])
                        clips_usados.add(cand["url"])
                        print(f"      ✅ Escena {esc.id}: Clip de respaldo seguro {cand['fuente']} [{cand['key']}] (YAVG={met_st.get('yavg')})")
                        break
                    else:
                        destino_clip.unlink(missing_ok=True)
                        rechazos_esc.append({
                            "fuente": cand["fuente"],
                            "candidato": cand["key"],
                            "url": cand["url"],
                            "motivo": f"Post-descarga FFmpeg: {motivo_st}",
                        })

        # 4. Encadenar un 2º clip distinto si el clip descargado es más corto que la locución
        if exito:
            extras = _completar_clip_corto_con_stock(
                esc, destino_clip, dur_audio, clips_usados, candidatos_precalculados=candidatos_stock
            )
            if extras:
                fuente_usada = f"{fuente_usada}+Chained"
                detalle_clip = f"{detalle_clip} + {extras}"

        if not exito:
            fuente_usada = "Fallback"
            print(f"      🛡️ Escena {esc.id}: Ningún clip aprobó los filtros -> generando fondo estilizado...")
            cmd_emergencia = [
                ffmpeg_bin_path or "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=0x1e2538:s=1920x1080:r=30",
                "-t", f"{dur_descarga:.2f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-an",
                str(destino_clip)
            ]
            try:
                subprocess.run(cmd_emergencia, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                exito = es_video_valido(destino_clip)
            except Exception:
                pass

        t_vid = obtener_duracion_video(destino_clip) if exito else 0.0
        creditos.append({
            "escena": esc.id,
            "archivo": destino_clip.name if exito else None,
            "fuente": fuente_usada if exito else "Error",
            "credito": f"{fuente_usada}: {detalle_clip}",
            "detalle": detalle_clip,
            "duracion_video": t_vid,
        })

    p.ruta("b_roll", "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=2), "utf-8")
    ruta_rep = p.ruta("b_roll", "broll_reporte.md")
    generar_reporte_broll_md(ruta_rep, p.tema, "16:9", creditos, rechazos_por_escena)
    p.marcar("broll", "ok")
    print(f"✨ Clips de video listos y organizados. Reporte de rechazos: {ruta_rep}")
    return creditos
