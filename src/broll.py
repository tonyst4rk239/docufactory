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


import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


import re
import urllib.parse


def buscar_youtube_ids(query: str, max_results: int = 4) -> list[str]:
    """Busca videos reales en YouTube mediante scrape limpio sin bloqueos de bot."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    q = urllib.parse.quote(query)
    url = f"https://www.youtube.com/results?search_query={q}"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        vids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", r.text)
        return list(dict.fromkeys(vids))[:max_results]
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


def descargar_clip_youtube(
    query: str,
    destino_mp4: Path,
    inicio_s: int = 10,
    duracion_s: int = 15,
    clips_usados: Optional[set[str]] = None,
) -> Optional[str]:
    """Busca en YouTube mediante ID real y descarga un fragmento en alta resolución.
    Devuelve la clave del video usado ('yt:<id>') si tuvo éxito, o None."""
    if not youtube_disponible():
        return None
    vids = buscar_youtube_ids(query, max_results=4)
    if not vids:
        palabras = [w for w in query.split() if len(w) > 3]
        if len(palabras) >= 2:
            vids = buscar_youtube_ids(" ".join(palabras[:3]), max_results=3)

    if not vids:
        return None

    temp_prefix = destino_mp4.parent / f"tmp_yt_{destino_mp4.stem}"
    ydl_opts = {
        **opciones_ytdlp_base(),
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "outtmpl": str(temp_prefix.with_suffix(".%(ext)s")),
        "download_ranges": yt_dlp.utils.download_range_func(None, [(inicio_s, inicio_s + duracion_s)]),
        "force_keyframes_at_cuts": True,
    }

    for vid_id in vids:
        if not youtube_disponible():
            break
        clave_yt = f"yt:{vid_id}"
        if clips_usados is not None and clave_yt in clips_usados:
            continue
        url = f"https://www.youtube.com/watch?v={vid_id}"
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            candidatos = list(destino_mp4.parent.glob(f"{temp_prefix.name}.*"))
            for f in candidatos:
                if f.is_file():
                    exito_remux = _remux_a_mp4(f, destino_mp4)
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass
                    if exito_remux:
                        if clips_usados is not None:
                            clips_usados.add(clave_yt)
                        return clave_yt

            if destino_mp4.exists() and es_video_valido(destino_mp4):
                if clips_usados is not None:
                    clips_usados.add(clave_yt)
                return clave_yt
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
    # Tokens de la primera consulta (sujeto principal) valen más
    tokens_primaria = _tokenizar(
        (esc.broll_queries_en[0] if getattr(esc, "broll_queries_en", None) else esc.broll_query_en) or ""
    )

    tokens_mood = set(mood_cfg["mood"]) | _tokenizar(" ".join(getattr(esc, "broll_mood_keywords", []) or []))
    tokens_avoid_raw = set(mood_cfg["avoid"]) | _tokenizar(" ".join(getattr(esc, "broll_avoid_keywords", []) or []))
    # Si la consulta pide explícitamente un término, no lo bloqueamos
    tokens_avoid = {t for t in tokens_avoid_raw if t not in tokens_query}

    evaluados: list[dict] = []
    for cand in candidatos:
        key = cand.get("key") or f"{cand.get('fuente')}:{cand.get('id')}"
        if key in clips_usados or cand.get("url") in clips_usados:
            continue

        tokens_tags = _tokenizar(cand.get("tags", ""))
        # 1. Rechazo estricto si choca con términos evitados / mood opuesto
        if any(_coincide_termino(tokens_tags, av) for av in tokens_avoid):
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

    # Priorizar: 1) los que tienen al menos un match relevante de query/mood, 2) mayor score, 3) mayor duración
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
) -> list[dict]:
    """Busca y puntúa candidatos en orden: Pexels (si hay API key) -> Pixabay.
    Prioriza clips con duración >= dur_audio y devuelve candidatos que NO chocan con el mood ni están repetidos."""
    queries = _consultas_escena(esc)
    candidatos_pexels = _buscar_candidatos_pexels(queries) if config.PEXELS_API_KEY else []
    evaluados_pexels = _puntuar_y_filtrar_candidatos(candidatos_pexels, esc, dur_audio, clips_usados)

    candidatos_pixabay = _buscar_candidatos_pixabay(queries)
    evaluados_pixabay = _puntuar_y_filtrar_candidatos(candidatos_pixabay, esc, dur_audio, clips_usados)

    # Priorizar: 1) duracion >= dur_audio (cubre toda la escena sin cortes), 2) score de relevancia, 3) Pexels sobre Pixabay
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
                d_ext = obtener_duracion_video(tmp_extra)
                if d_ext > 0.5:
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


def etapa_broll(p: Proyecto, duraciones: Optional[dict[int, float]] = None) -> list[dict]:
    """Descarga clips de YouTube/Stock optimizados para cada escena, filtrando por mood, sin repetir
    y encadenando 2 clips distintos cuando uno solo sea más corto que el audio de la escena."""
    from .voz import obtener_duracion_wav

    guion = cargar_guion(p)
    carpeta_broll = p.ruta("b_roll")
    carpeta_broll.mkdir(exist_ok=True, parents=True)

    creditos = []
    clips_usados: set[str] = set()
    total = len(guion.escenas)
    print(f"🎬 Buscando y curando B-roll para {total} escenas (sin repeticiones, filtro de mood activo)...")

    for i, esc in enumerate(guion.escenas, 1):
        destino_clip = carpeta_broll / f"escena_{esc.id:03d}.mp4"

        # Obtener duración del audio de la escena
        dur_audio = (duraciones or {}).get(esc.id)
        if not dur_audio:
            wav_path = p.ruta("voz", f"escena_{esc.id:03d}.wav")
            if wav_path.exists():
                dur_audio = obtener_duracion_wav(wav_path)
            else:
                dur_audio = 10.0

        if destino_clip.exists():
            if es_video_valido(destino_clip):
                t_vid = obtener_duracion_video(destino_clip)
                print(f"   [{i}/{total}] Escena {esc.id}: Reutilizando clip ({destino_clip.name}, {t_vid:.1f}s)")
                extras_cache: list[str] = []
                if t_vid + 0.25 < dur_audio:
                    extras_cache = _completar_clip_corto_con_stock(esc, destino_clip, dur_audio, clips_usados)
                    t_vid = obtener_duracion_video(destino_clip)
                creditos.append({
                    "escena": esc.id,
                    "archivo": destino_clip.name,
                    "fuente": "Cache+Chained" if extras_cache else "Cache",
                    "detalle": f"encadenado con {extras_cache}" if extras_cache else "cache",
                    "duracion_video": t_vid,
                })
                continue
            else:
                print(f"   ⚠️ Escena {esc.id}: Clip en caché corrupto o truncado ({destino_clip.name}). Eliminando y re-descargando...")
                destino_clip.unlink(missing_ok=True)

        queries_esc = _consultas_escena(esc)
        query_yt = queries_esc[0]
        dur_descarga = max(15, int(dur_audio) + 5)
        fuente_usada = "Fallback"
        detalle_clip = ""
        exito = False
        candidatos_stock: Optional[list[dict]] = None

        if youtube_disponible():
            print(f"   [{i}/{total}] Buscando en YouTube para Escena {esc.id}: '{query_yt}' ({dur_descarga}s solicitados)...")
            clave_yt = descargar_clip_youtube(
                query_yt, destino_clip, inicio_s=5, duracion_s=dur_descarga, clips_usados=clips_usados
            )
            if clave_yt:
                exito = True
                fuente_usada = "YouTube"
                detalle_clip = clave_yt
                print(f"      ✅ Escena {esc.id}: Clip obtenido desde YouTube ({clave_yt}).")
            else:
                motivo_fb = "bloqueo anti-bot de YouTube" if not youtube_disponible() else "sin resultados válidos en YouTube"
                print(f"      ↪️ Escena {esc.id}: Fallback activado ({motivo_fb}) -> curando stock (Pexels/Pixabay)...")
        else:
            print(f"   [{i}/{total}] Escena {esc.id}: YouTube omitido (bloqueado) -> curando stock para {queries_esc[:2]}...")

        if not exito:
            candidatos_stock = _seleccionar_mejor_stock(esc, dur_audio, clips_usados)
            for cand in candidatos_stock:
                if descargar_archivo_directo(cand["url"], destino_clip):
                    exito = True
                    fuente_usada = cand["fuente"]
                    detalle_clip = f"{cand['key']} (score={cand['score']}, dur={cand['duracion']:.1f}s, tags='{cand['tags'][:60]}')"
                    clips_usados.add(cand["key"])
                    clips_usados.add(cand["url"])
                    print(f"      ✅ Escena {esc.id}: Clip curado de {fuente_usada} [{cand['key']}] "
                          f"(score {cand['score']}, {cand['duracion']:.1f}s, tags: {cand['tags'][:50]})")
                    break

        # Si el clip descargado dura menos que el audio de la escena, encadenar un 2º clip distinto en lugar de hacer loop
        if exito:
            extras = _completar_clip_corto_con_stock(
                esc, destino_clip, dur_audio, clips_usados, candidatos_precalculados=candidatos_stock
            )
            if extras:
                fuente_usada = f"{fuente_usada}+Chained"
                detalle_clip = f"{detalle_clip} + {extras}"

        if not exito:
            # Respaldo de emergencia estilizado
            fuente_usada = "Fallback"
            print(f"      🛡️ Escena {esc.id}: Ningún clip aprobó el filtro de mood -> generando fondo oscuro de emergencia...")
            cmd_emergencia = [
                ffmpeg_bin_path or "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=0x111625:s=1920x1080:r=30",
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
            "detalle": detalle_clip,
            "duracion_video": t_vid,
        })

    p.ruta("b_roll", "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=2), "utf-8")
    p.marcar("broll", "ok")
    print("✨ Clips de video listos y organizados.")
    return creditos
