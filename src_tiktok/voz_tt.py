"""Generador de voz Edge-TTS ultrarrápida (~175 ppm) para formato TikTok/Shorts."""
from __future__ import annotations

import asyncio
from pathlib import Path
import edge_tts
from src.estado import Proyecto
from src.voz import preparar_texto_con_pausas
from src_tiktok.guion_tt import GuionTikTok


VOICE_TIKTOK = "es-MX-JorgeNeural"  # Voz enérgica y misteriosa
RATE_TIKTOK = "+12%"                # Ritmo acelerado de TikTok para máxima retención
PITCH_TIKTOK = "-1Hz"


async def _sintetizar_escena(texto: str, destino: Path):
    texto_limpio = preparar_texto_con_pausas(texto)
    com = edge_tts.Communicate(texto_limpio, VOICE_TIKTOK, rate=RATE_TIKTOK, pitch=PITCH_TIKTOK)
    await com.save(str(destino))


def etapa_voz_tiktok(p: Proyecto, guion: GuionTikTok) -> dict[int, float]:
    carpeta_voz = p.ruta("voz")
    carpeta_voz.mkdir(parents=True, exist_ok=True)
    duraciones: dict[int, float] = {}

    import subprocess
    from src import config

    ffprobe = config.ffmpeg_bin("ffprobe")

    async def _procesar_todas():
        tareas = []
        for esc in guion.escenas:
            salida = carpeta_voz / f"escena_{esc.id:03d}.mp3"
            tareas.append(_sintetizar_escena(esc.voz, salida))
        await asyncio.gather(*tareas)

    print(f"🎙️ Generando voces de TikTok a ritmo acelerado ({RATE_TIKTOK})...")
    asyncio.run(_procesar_todas())

    for esc in guion.escenas:
        archivo = carpeta_voz / f"escena_{esc.id:03d}.mp3"
        cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(archivo)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        dur = float(res.stdout.strip())
        duraciones[esc.id] = dur

    p.marcar("voz", "ok")
    return duraciones
