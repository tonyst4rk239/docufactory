"""Generación de audio de voz en off por escena.

Soporta:
  1. edge-tts (Local / Neural de Microsoft sin cuotas ni límites, voces ultra-naturales: es-MX-JorgeNeural, es-MX-DaliaNeural)
  2. Gemini Flash TTS (vía API con voz Charon/Puck si hay cuota disponible)
Calibra la duración exacta escena por escena.
"""
from __future__ import annotations

import asyncio
import subprocess
import time
import wave
from pathlib import Path
from typing import Optional

import edge_tts
from google import genai
from google.genai import types

from . import config
from .estado import Proyecto
from .guion import cargar_guion, Guion, Escena

# Voces neurales hiperrealistas en español neutro / latino
VOZ_EDGE_DEFAULT = "es-MX-JorgeNeural"  # Tono documental masculino natural


def _convertir_a_wav(origen_audio: Path, destino_wav: Path) -> None:
    """Convierte cualquier formato de audio a WAV PCM 16-bit 24kHz con FFmpeg."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    cmd = [
        ffmpeg, "-y",
        "-i", str(origen_audio),
        "-ar", "24000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(destino_wav)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


async def _sintetizar_edge_tts(texto: str, destino_mp3: Path, voz: str = VOZ_EDGE_DEFAULT) -> None:
    comm = edge_tts.Communicate(texto, voz, rate="+0%")
    await comm.save(str(destino_mp3))


def sintetizar_audio(texto: str, destino_wav: Path) -> float:
    """Sintetiza locución usando edge-tts garantizado (o Gemini TTS de respaldo) y devuelve la duración."""
    temp_mp3 = destino_wav.with_suffix(".temp.mp3")
    try:
        # Método principal: Ultra-fiable sin cuotas de rate-limit
        asyncio.run(_sintetizar_edge_tts(texto, temp_mp3))
        _convertir_a_wav(temp_mp3, destino_wav)
        if temp_mp3.exists():
            temp_mp3.unlink()
        return obtener_duracion_wav(destino_wav)
    except Exception as e:
        print(f"⚠️ Error sintetizando con EdgeTTS ({e}). Intentando con Gemini TTS...")

    # Respaldo: Gemini Flash TTS
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = client.models.generate_content(
        model="gemini-3.8-flash-tts",
        contents=f"Narra con tono documental: {texto}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
                )
            ),
        ),
    )
    for part in resp.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            destino_wav.write_bytes(part.inline_data.data)
            return obtener_duracion_wav(destino_wav)

    raise RuntimeError("No fue posible generar el audio de la escena.")


def obtener_duracion_wav(ruta_wav: Path) -> float:
    """Devuelve la duración exacta en segundos de un archivo WAV."""
    with wave.open(str(ruta_wav), "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate()
        return round(frames / float(rate), 2)


def etapa_voz(p: Proyecto, regenerar: bool = False) -> dict[int, float]:
    """Genera el audio por escena. Devuelve un mapeo {escena_id: duracion_segundos}."""
    guion = cargar_guion(p)
    carpeta_voz = p.ruta("voz")
    carpeta_voz.mkdir(exist_ok=True, parents=True)

    duraciones: dict[int, float] = {}
    total_escenas = len(guion.escenas)

    print(f"🎙️ Generando locución neural para {total_escenas} escenas con voz '{VOZ_EDGE_DEFAULT}'...")

    for i, escena in enumerate(guion.escenas, 1):
        archivo_wav = carpeta_voz / f"escena_{escena.id:03d}.wav"

        if archivo_wav.exists() and not regenerar:
            dur = obtener_duracion_wav(archivo_wav)
            duraciones[escena.id] = dur
            print(f"   [{i}/{total_escenas}] Escena {escena.id}: Reutilizando ({dur}s)")
            continue

        try:
            dur = sintetizar_audio(escena.voz, archivo_wav)
            duraciones[escena.id] = dur
            print(f"   [{i}/{total_escenas}] Escena {escena.id}: {dur}s ✅ -> {archivo_wav.name}")
        except Exception as e:
            print(f"   ❌ Error en escena {escena.id}: {e}")

    p.marcar("voz", "ok")
    duracion_total = sum(duraciones.values())
    print(f"✨ Locución completada. Duración total: {int(duracion_total//60)}m {int(duracion_total%60)}s")
    return duraciones
