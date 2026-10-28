"""Generación de audio de voz en off por escena con entonación documental y mastering.

Aplica:
  1. Preparación de texto con micropausas automáticas (comas -> 180ms, puntos -> 420ms).
  2. Motor Edge-TTS con es-MX-JorgeNeural (speaking_rate +3%, pitch -1Hz / resonancia sobria).
  3. Masterizado y normalización FFmpeg con filtro loudnorm (I=-16 LUFS, TP=-1.5 dB, LRA=11)
     y filtro paso alto suave (highpass=f=80).
"""
from __future__ import annotations

import asyncio
import re
import subprocess
import time
import wave
from pathlib import Path
from typing import Optional

import edge_tts

from . import config
from .estado import Proyecto
from .guion import cargar_guion, Guion, Escena

VOZ_DEFAULT = "es-US-AlonsoNeural"


# Etiquetas de actuación en línea que Pluma puede poner en `voz` (ej. "[susurro]", "[pausa corta]").
# Nunca se pronuncian ni salen en subtítulos: los motores que no las entienden las quitan.
RE_TAG_ACTUACION = re.compile(r"\[\s*[^\[\]\n]{1,40}?\s*\]")
RE_TAG_PAUSA = re.compile(r"\[\s*pausa(?:\s+corta)?\s*\]", re.IGNORECASE)


def quitar_tags_actuacion(texto: str) -> str:
    """Quita las etiquetas de actuación entre corchetes ([susurro], [pausa corta], ...)."""
    t = RE_TAG_ACTUACION.sub(" ", texto or "")
    t = re.sub(r"\s+([,.;:!?…])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def limpiar_tags_ssml(texto: str) -> str:
    """Elimina etiquetas SSML (<break .../>, <emphasis>, etc.) y de actuación ([susurro]) dejando el texto limpio."""
    t = re.sub(r"<[^>]+>", " ", texto or "")
    return quitar_tags_actuacion(t)


def _reemplazar_break_ssml(match: re.Match) -> str:
    attr = match.group(1) or ""
    m_ms = re.search(r"(\d+(?:\.\d+)?)\s*ms", attr, re.IGNORECASE)
    m_s = re.search(r"(\d+(?:\.\d+)?)\s*s\b", attr, re.IGNORECASE)
    ms = 400.0
    if m_ms:
        ms = float(m_ms.group(1))
    elif m_s:
        ms = float(m_s.group(1)) * 1000.0
    if ms >= 650:
        return "... ... "
    if ms >= 300:
        return "... "
    return ", "


def preparar_texto_con_pausas(texto: str) -> str:
    """Prepara el texto convirtiendo etiquetas SSML <break/> e inyectando pausas de ritmo documental."""
    t = re.sub(r"<\s*(?:break|pause)\b([^>]*)/?\s*>", _reemplazar_break_ssml, texto or "", flags=re.IGNORECASE)
    t = re.sub(r"<[^>]+>", " ", t)
    # Etiquetas de actuación: "[pausa corta]" se vuelve respiro; las demás ("[susurro]") se quitan
    t = RE_TAG_PAUSA.sub("... ", t)
    t = quitar_tags_actuacion(t)
    # Asegurar espacios limpios tras signos de puntuación
    t = re.sub(r"\s+", " ", t).strip()
    # Puntos suspensivos para dar respiro reflexivo en puntos seguidos
    t = t.replace(". ", "... ")
    t = re.sub(r"(?:\.\.\.\s*){2,}", "... ", t)
    t = re.sub(r"(?:…|\.){2,}", "...", t)
    t = t.replace(", ", ", ")
    return t


def normalizar_audio_ffmpeg(origen_audio: Path, destino_wav: Path, pad_inicio_s: float = 0.0) -> None:
    """Aplica filtro loudnorm (-16 LUFS, TP=-1.5 dB, LRA=11) y highpass=f=80, con opción de pre-roll silence."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    filtros = ["highpass=f=80"]
    if pad_inicio_s > 0:
        delay_ms = int(pad_inicio_s * 1000)
        filtros.append(f"adelay={delay_ms}|{delay_ms}")
    filtros.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    cmd = [
        ffmpeg, "-y",
        "-i", str(origen_audio),
        "-af", ",".join(filtros),
        "-ar", "24000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(destino_wav)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


async def _sintetizar_edge_tts(texto: str, destino_mp3: Path, voz: str = VOZ_DEFAULT) -> None:
    # Calibración: rate -3%, pitch -4Hz para misterio, presencia grave y suspenso cinematográfico
    comm = edge_tts.Communicate(texto, voz, rate="-3%", pitch="-4Hz")
    await comm.save(str(destino_mp3))


def sintetizar_y_masterizar_escena(texto: str, destino_wav: Path, pad_inicio_s: float = 0.0) -> float:
    """Sintetiza la escena con modulación y aplica masterizado con loudnorm."""
    texto_modulado = preparar_texto_con_pausas(texto)
    temp_raw_mp3 = destino_wav.with_suffix(".raw.mp3")
    try:
        asyncio.run(_sintetizar_edge_tts(texto_modulado, temp_raw_mp3))
        normalizar_audio_ffmpeg(temp_raw_mp3, destino_wav, pad_inicio_s=pad_inicio_s)
        if temp_raw_mp3.exists():
            temp_raw_mp3.unlink()
        return obtener_duracion_wav(destino_wav)
    except Exception as e:
        if temp_raw_mp3.exists():
            temp_raw_mp3.unlink()
        raise RuntimeError(f"Error sintetizando escena: {e}")


def obtener_duracion_wav(ruta_wav: Path) -> float:
    """Devuelve la duración exacta en segundos de un archivo WAV."""
    with wave.open(str(ruta_wav), "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate()
        return round(frames / float(rate), 2)


def etapa_voz(p: Proyecto, regenerar: bool = False) -> dict[int, float]:
    """Genera y masteriza el audio por escena. Devuelve un mapeo {escena_id: duracion_segundos}."""
    guion = cargar_guion(p)
    carpeta_voz = p.ruta("voz")
    carpeta_voz.mkdir(exist_ok=True, parents=True)

    duraciones: dict[int, float] = {}
    total_escenas = len(guion.escenas)

    print(f"🎙️ Generando locución masterizada (-16 LUFS, loudnorm) para {total_escenas} escenas...")

    for i, escena in enumerate(guion.escenas, 1):
        archivo_wav = carpeta_voz / f"escena_{escena.id:03d}.wav"
        pad = 0.45 if i == 1 else 0.0

        if archivo_wav.exists() and not regenerar:
            dur = obtener_duracion_wav(archivo_wav)
            duraciones[escena.id] = dur
            print(f"   [{i}/{total_escenas}] Escena {escena.id}: Reutilizando ({dur}s)")
            continue

        try:
            dur = sintetizar_y_masterizar_escena(escena.voz, archivo_wav, pad_inicio_s=pad)
            duraciones[escena.id] = dur
            print(f"   [{i}/{total_escenas}] Escena {escena.id}: {dur}s (Masterizado) -> {archivo_wav.name}")
        except Exception as e:
            print(f"   ❌ Error en escena {escena.id}: {e}")

    duracion_total = round(sum(duraciones.values()), 2)
    minutos_pedidos = float(p.datos.get("minutos", 1.0))
    objetivo_s = round(minutos_pedidos * 60.0, 2)
    desviacion_s = round(duracion_total - objetivo_s, 2)
    desviacion_pct = round((desviacion_s / objetivo_s) * 100.0, 1) if objetivo_s > 0 else 0.0
    total_palabras = sum(len(limpiar_tags_ssml(e.voz).split()) for e in guion.escenas)
    wpm_efectivo = round(total_palabras / (duracion_total / 60.0), 1) if duracion_total > 0 else 0.0
    margen_s = max(6.0, objetivo_s * config.TOLERANCIA_DURACION)
    dentro_rango = abs(desviacion_s) <= margen_s

    p.datos["validacion_duracion"] = {
        "minutos_pedidos": minutos_pedidos,
        "objetivo_s": objetivo_s,
        "real_s": duracion_total,
        "desviacion_s": desviacion_s,
        "desviacion_pct": desviacion_pct,
        "palabras_totales": total_palabras,
        "wpm_efectivo": wpm_efectivo,
        "dentro_de_rango": dentro_rango,
    }
    p.marcar("voz", "ok")

    signo = "+" if desviacion_s >= 0 else ""
    print(
        f"✨ Masterización de voz completada. Duración real: {int(duracion_total//60)}m {int(duracion_total%60):02d}s "
        f"({duracion_total:.1f}s) | Objetivo: {int(objetivo_s//60)}m {int(objetivo_s%60):02d}s ({objetivo_s:.1f}s) "
        f"| Ritmo real: {wpm_efectivo} pal/min ({total_palabras} palabras)"
    )
    if dentro_rango:
        print(f"   ✅ Duración post-TTS dentro de tolerancia ({signo}{desviacion_s:.1f}s / {signo}{desviacion_pct}%).")
    else:
        print(
            f"   ⚠️ Aviso de duración post-TTS: la locución difiere en {signo}{desviacion_s:.1f}s "
            f"({signo}{desviacion_pct}%) respecto a los {minutos_pedidos} min solicitados "
            f"(registrado en proyecto.json -> validacion_duracion)."
        )
    return duraciones
