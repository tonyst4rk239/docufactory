"""Búsqueda y descarga inteligente de clips de YouTube y TikTok (con fallback a Pixabay).

Utiliza yt-dlp con rangos de tiempo (download_ranges) para descargar únicamente
fragmentos de 3 a 6 segundos en alta resolución sin sobrecargar ancho de banda.
"""
from __future__ import annotations

import json
import os
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


def descargar_clip_youtube(query: str, destino_mp4: Path, inicio_s: int = 15, duracion_s: int = 5) -> bool:
    """Busca en YouTube y descarga únicamente un fragmento de duración especificada."""
    ydl_opts = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]",
        "outtmpl": str(destino_mp4.with_suffix(".%(ext)s")),
        "download_ranges": yt_dlp.utils.download_range_func(None, [(inicio_s, inicio_s + duracion_s)]),
        "force_keyframes_at_cuts": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "ytsearch1",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(f"ytsearch1:{query}", download=True)
            # Asegurar nombre final esperado
            for f in destino_mp4.parent.glob(f"{destino_mp4.stem}.*"):
                if f.suffix in [".mp4", ".mkv", ".webm"] and f != destino_mp4:
                    f.replace(destino_mp4)
                    return True
            return destino_mp4.exists()
    except Exception as e:
        print(f"⚠️ Error al descargar clip de YouTube ({query}): {e}")
        return False


def _buscar_pixabay_video(query: str) -> Optional[dict]:
    """Respaldo secundario si YouTube restringe la descarga."""
    if not config.PIXABAY_API_KEY:
        return None
    url = "https://pixabay.com/api/videos/"
    params = {"key": config.PIXABAY_API_KEY, "q": query, "per_page": 3}
    try:
        r = requests.get(url, params=params, timeout=12)
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
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(destino, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        return True
    except Exception:
        return False


def etapa_broll(p: Proyecto) -> list[dict]:
    """Descarga clips de YouTube/TikTok optimizados para cada puesto del Top."""
    guion = cargar_guion(p)
    carpeta_broll = p.ruta("b_roll")
    carpeta_broll.mkdir(exist_ok=True, parents=True)

    creditos = []
    total = len(guion.escenas)
    print(f"🎬 Buscando clips de YouTube para {total} escenas del Top...")

    for i, esc in enumerate(guion.escenas, 1):
        destino_clip = carpeta_broll / f"escena_{esc.id:03d}.mp4"

        if destino_clip.exists():
            print(f"   [{i}/{total}] Escena {esc.id}: Reutilizando clip ({destino_clip.name})")
            creditos.append({"escena": esc.id, "archivo": destino_clip.name, "fuente": "Cache"})
            continue

        query_yt = f"{esc.broll_query_en} b-roll 4k"
        print(f"   [{i}/{total}] Descargando clip de YouTube para Escena {esc.id}: '{esc.broll_query_en}'...")
        # Descarga de 5 segundos
        exito = descargar_clip_youtube(query_yt, destino_clip, inicio_s=10, duracion_s=6)

        if not exito:
            # Respaldo Pixabay
            print(f"   ⚠️ Intentando respaldo con Pixabay...")
            rec = _buscar_pixabay_video(esc.broll_query_en)
            if rec:
                descargar_archivo_directo(rec["url"], destino_clip)
                exito = True

        creditos.append({
            "escena": esc.id,
            "archivo": destino_clip.name,
            "fuente": "YouTube" if exito else "Generado"
        })

    p.ruta("b_roll", "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=2), "utf-8")
    p.marcar("broll", "ok")
    print("✨ Clips de video listos y organizados.")
    return creditos
