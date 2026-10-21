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


def descargar_clip_youtube(query: str, destino_mp4: Path, inicio_s: int = 10, duracion_s: int = 15) -> bool:
    """Busca en YouTube mediante ID real y descarga un fragmento en alta resolución garantizando duración suficiente."""
    vids = buscar_youtube_ids(query, max_results=3)
    if not vids:
        # Intento secundario con términos más amplios
        palabras = [w for w in query.split() if len(w) > 3]
        if len(palabras) >= 2:
            vids = buscar_youtube_ids(" ".join(palabras[:3]), max_results=2)

    if not vids:
        return False

    temp_prefix = destino_mp4.parent / f"tmp_yt_{destino_mp4.stem}"
    ydl_opts = {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "outtmpl": str(temp_prefix.with_suffix(".%(ext)s")),
        "download_ranges": yt_dlp.utils.download_range_func(None, [(inicio_s, inicio_s + duracion_s)]),
        "force_keyframes_at_cuts": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
    }

    for vid_id in vids:
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
                        return True

            if destino_mp4.exists() and es_video_valido(destino_mp4):
                return True
        except Exception:
            for f in destino_mp4.parent.glob(f"{temp_prefix.name}.*"):
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    if destino_mp4.exists() and not es_video_valido(destino_mp4):
        destino_mp4.unlink(missing_ok=True)
    return False


def _buscar_pixabay_video(query: str) -> Optional[dict]:
    """Respaldo secundario con reintentos escalonados de palabras clave."""
    if not config.PIXABAY_API_KEY:
        return None
    url = "https://pixabay.com/api/videos/"
    queries_a_probar = [query]
    palabras = [w for w in query.split() if len(w) > 3]
    if len(palabras) > 2:
        queries_a_probar.append(" ".join(palabras[:2]))
        queries_a_probar.append(" ".join(palabras[-2:]))
    queries_a_probar.append("technology")

    for q_intento in queries_a_probar:
        params = {"key": config.PIXABAY_API_KEY, "q": q_intento, "per_page": 3}
        try:
            r = requests.get(url, params=params, headers=HTTP_HEADERS, verify=False, timeout=10)
            if r.ok:
                hits = r.json().get("hits", [])
                for h in hits:
                    vids = h.get("videos", {})
                    opt = vids.get("large") or vids.get("medium") or vids.get("small")
                    if opt and opt.get("url"):
                        return {
                            "tipo": "video",
                            "fuente": "Pixabay",
                            "id": h["id"],
                            "url": opt["url"],
                            "creditos": f"Pixabay Video ID {h['id']}"
                        }
        except Exception:
            pass
    return None


def descargar_archivo_directo(url: str, destino: Path) -> bool:
    try:
        temp_dest = destino.with_suffix(".tmp_download")
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


def etapa_broll(p: Proyecto, duraciones: Optional[dict[int, float]] = None) -> list[dict]:
    """Descarga clips de YouTube/TikTok optimizados para cada puesto del Top y valida duraciones."""
    from .voz import obtener_duracion_wav

    guion = cargar_guion(p)
    carpeta_broll = p.ruta("b_roll")
    carpeta_broll.mkdir(exist_ok=True, parents=True)

    creditos = []
    total = len(guion.escenas)
    print(f"🎬 Buscando clips de YouTube para {total} escenas del Top...")

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
                if t_vid < dur_audio:
                    print(f"      ℹ️ Clip ({t_vid:.1f}s) < Audio ({dur_audio:.1f}s) -> Se aplicará bucle fluido con zoom suave en render.")
                creditos.append({"escena": esc.id, "archivo": destino_clip.name, "fuente": "Cache", "duracion_video": t_vid})
                continue
            else:
                print(f"   ⚠️ Escena {esc.id}: Clip en caché corrupto o truncado ({destino_clip.name}). Eliminando y re-descargando...")
                destino_clip.unlink(missing_ok=True)

        query_yt = esc.broll_query_en
        dur_descarga = max(15, int(dur_audio) + 5)
        print(f"   [{i}/{total}] Descargando clip para Escena {esc.id}: '{esc.broll_query_en}' ({dur_descarga}s solicitados)...")
        exito = descargar_clip_youtube(query_yt, destino_clip, inicio_s=5, duracion_s=dur_descarga)

        if not exito:
            # Respaldo Pixabay
            print(f"   ⚠️ Intentando respaldo con Pixabay...")
            rec = _buscar_pixabay_video(esc.broll_query_en)
            if rec:
                exito = descargar_archivo_directo(rec["url"], destino_clip)

        if not exito:
            # Respaldo de emergencia estilizado
            print(f"   🛡️ Generando fondo cinematográfico de emergencia para Escena {esc.id}...")
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
        if exito and t_vid < dur_audio:
            print(f"      ℹ️ Clip descargado ({t_vid:.1f}s) < Audio ({dur_audio:.1f}s) -> Se aplicará bucle fluido con zoom suave en render.")

        creditos.append({
            "escena": esc.id,
            "archivo": destino_clip.name if exito else None,
            "fuente": "YouTube" if exito else ("Pixabay" if exito else "Fallback"),
            "duracion_video": t_vid
        })

    p.ruta("b_roll", "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=2), "utf-8")
    p.marcar("broll", "ok")
    print("✨ Clips de video listos y organizados.")
    return creditos
