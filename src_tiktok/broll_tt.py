"""Descargador de B-Roll vertical o adaptable a 1080x1920."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
import requests
import urllib3
from src import config
from src.broll import descargar_clip_youtube, descargar_archivo_directo, es_video_valido
from src.estado import Proyecto
from src_tiktok.guion_tt import GuionTikTok

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def buscar_clip_pixabay(query: str) -> str | None:
    """Busca video en Pixabay priorizando formato vertical y fallback general."""
    if not config.PIXABAY_API_KEY:
        return None
    url = "https://pixabay.com/api/videos/"
    palabras = [w for w in query.split() if len(w) > 3]

    intentos = [
        (query, "vertical"),
        (query, "all"),
    ]
    if len(palabras) >= 2:
        intentos.append((" ".join(palabras[:2]), "vertical"))
        intentos.append((" ".join(palabras[:2]), "all"))
        intentos.append((" ".join(palabras[-2:]), "all"))
    elif palabras:
        intentos.append((palabras[0], "all"))

    intentos.append(("dark cinematic", "all"))
    intentos.append(("suspense", "all"))

    for q_int, orient in intentos:
        params = {
            "key": config.PIXABAY_API_KEY,
            "q": q_int,
            "orientation": orient,
            "per_page": 5
        }
        try:
            r = requests.get(url, params=params, headers=HTTP_HEADERS, verify=False, timeout=10)
            if r.ok:
                hits = r.json().get("hits", [])
                for h in hits:
                    vids = h.get("videos", {})
                    opt = vids.get("large") or vids.get("medium") or vids.get("small")
                    if opt and opt.get("url"):
                        return opt["url"]
        except Exception:
            continue
    return None


import re
import urllib.parse
import yt_dlp
from src.broll import descargar_archivo_directo, es_video_valido


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


def descargar_clip_social_yt(video_id: str, destino: Path, inicio_s: int = 5, duracion_s: int = 6) -> bool:
    """Descarga un fragmento exacto de video de YouTube/Shorts y lo remuxa a MP4."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    temp_prefix = destino.parent / f"tmp_{destino.stem}"
    ydl_opts = {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "outtmpl": str(temp_prefix) + ".%(ext)s",
        "download_ranges": yt_dlp.utils.download_range_func(None, [(inicio_s, inicio_s + duracion_s)]),
        "force_keyframes_at_cuts": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        candidatos = list(destino.parent.glob(f"{temp_prefix.name}.*"))
        if not candidatos:
            return False
        descargado = candidatos[0]
        ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
        cmd = [
            ffmpeg, "-y",
            "-i", str(descargado),
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(destino)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        descargado.unlink(missing_ok=True)
        return destino.exists() and es_video_valido(destino)
    except Exception:
        for f in destino.parent.glob(f"{temp_prefix.name}.*"):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        return False


def etapa_broll_tiktok(p: Proyecto, guion: GuionTikTok, duraciones: dict[int, float]):
    carpeta_broll = p.ruta("b_roll")
    carpeta_broll.mkdir(parents=True, exist_ok=True)
    total = len(guion.escenas)
    print(f"🎬 Descargando clips REALES de redes sociales (YouTube / Shorts / TikTok) para {total} micro-escenas...")

    for i, esc in enumerate(guion.escenas, 1):
        destino = carpeta_broll / f"escena_{esc.id:03d}.mp4"
        if destino.exists() and es_video_valido(destino):
            print(f"   [{i}/{total}] Clip existente y válido para Escena {esc.id}: {destino.name}")
            continue

        query = esc.broll_query_en.strip()
        dur_pedida = max(5, int(duraciones.get(esc.id, 3.0)) + 3)
        print(f"   [{i}/{total}] Buscando clip real de redes: '{query}'...")

        exito = False

        # 1. PRIORIDAD 1: Búsqueda de clip real en YouTube / Shorts / Noticias
        queries_yt = [
            f"{query} #shorts",
            f"{query} news footage",
            query,
        ]
        
        # Enriquecer con tema si la query es genérica
        if len(query.split()) < 3 and p.tema:
            queries_yt.insert(0, f"{p.tema} {query}")

        for q_yt in queries_yt:
            vids = buscar_youtube_ids(q_yt, max_results=3)
            for vid_id in vids:
                print(f"      ⬇️ Descargando metraje real desde YouTube ({vid_id})...")
                exito = descargar_clip_social_yt(vid_id, destino, inicio_s=5, duracion_s=dur_pedida)
                if exito:
                    print(f"      ✅ Clip real de redes sociales obtenido ({destino.name})")
                    break
            if exito:
                break

        # 2. PRIORIDAD 2: Respaldo Pixabay si no hubo clips en YouTube
        if not exito:
            print(f"      ℹ️ No se obtuvo clip en YouTube. Intentando stock de respaldo en Pixabay...")
            url_pix = buscar_clip_pixabay(query)
            if url_pix:
                exito = descargar_archivo_directo(url_pix, destino)
                if exito:
                    print(f"      ✅ Clip descargado desde Pixabay HD ({destino.name})")

        # 3. PRIORIDAD 3: Fondo cinematográfico abstracto en caso extremo
        if not exito:
            print(f"      ⚠️ Generando fondo cinematográfico abstracto para escena {esc.id}...")
            ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
            cmd_emergencia = [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", "color=c=0x111625:s=1080x1920:r=30",
                "-t", f"{dur_pedida:.2f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-an", str(destino)
            ]
            try:
                subprocess.run(cmd_emergencia, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            except Exception:
                pass

    p.marcar("broll", "ok")


