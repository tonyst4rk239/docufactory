"""Motor de voz Gemini TTS (voz "Charon") para los Reels verticales.

- Una petición por escena (así los subtítulos siguen alineados por escena, igual que con Edge).
- Instrucción de actuación según el `tono` de Pluma, siempre con ritmo ágil.
- Etiquetas en línea admitidas: [susurro] y [pausa corta] ([pausa] equivale a [pausa corta]).
  Se le pasan a Gemini como dirección de actuación; cualquier otra etiqueta entre corchetes se quita.
- Gemini deja silencios largos cuando se le pide suspenso: se recortan a ~0.5 s.
- Errores tipados para que voz_tt decida el respaldo (Edge es-MX-JorgeNeural):
    GeminiCuotaAgotada  -> 429 de cuota diaria (o 429 persistente)
    GeminiTTSError      -> cualquier otra falla (red, respuesta sin audio, audio anómalo)
La clave sale de config.GEMINI_API_KEY (.env) y nunca se imprime.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import time
import wave
from pathlib import Path
from typing import Callable, Optional

import requests

from src import config
from src.voz import RE_TAG_ACTUACION, quitar_tags_actuacion

MODELO_TTS = os.getenv("GEMINI_TTS_MODELO", "gemini-2.5-flash-preview-tts")
URL_TTS = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
SAMPLE_RATE = 24000

# Recorte de pausas: Gemini deja silencios de 2-3 s cuando se le pide suspenso. Toda pausa bajo
# -35 dB se deja en ~0.5 s (en ffmpeg >= 6.1 el silencio conservado es stop_duration + stop_silence).
# Además se deja sólo 50 ms de aire al inicio y 200 ms al final de cada escena para que los cortes
# entre escenas no se sientan muertos.
FILTRO_PAUSAS = (
    "silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB:start_silence=0.05,"
    "silenceremove=stop_periods=-1:stop_duration=0.1:stop_threshold=-35dB:stop_silence=0.4,"
    "areverse,silenceremove=start_periods=1:start_duration=0:start_threshold=-45dB:start_silence=0.2,areverse"
)

_BASE = (
    "Eres narrador de un Reel documental en YouTube y TikTok, español mexicano. "
    "Ritmo ágil y constante, sin arrastrar las palabras ni hacer pausas largas. "
)
_ETIQUETAS = (
    " Si el texto trae [susurro], baja la voz casi a susurro en esa frase; si trae [pausa corta], "
    "haz una pausa breve y tensa. Nunca leas en voz alta lo que va entre corchetes. "
    "Lee solo el texto que sigue, sin agregar nada."
)

INSTRUCCIONES_TONO: dict[str, str] = {
    "misterio": _BASE + "Con tensión de documental de misterio: voz grave y contenida, tensión creciente, "
                "una pausa corta antes del dato clave.",
    "investigacion": _BASE + "Voz firme y segura, como periodista que revela pruebas; claridad en cifras y nombres.",
    "controversia": _BASE + "Tono incisivo, con ironía leve, como quien desmonta un mito con datos.",
    "humor": _BASE + "Tono ligero y sonriente, con remates bien marcados, sin perder credibilidad.",
    "epico": _BASE + "Tono solemne y poderoso que crece hacia el final de la frase.",
    "default": _BASE + "Tono de documental cercano y seguro, con energía y curiosidad.",
}
# Alias: los tonos válidos de Pluma (src/guion.TONOS_VALIDOS) más sinónimos comunes
ALIAS_TONO = {
    "misterio": "misterio", "leyenda": "misterio", "terror": "misterio", "paranormal": "misterio",
    "investigacion": "investigacion", "investigación": "investigacion", "curiosidad": "investigacion",
    "polemica": "controversia", "polémica": "controversia", "controversia": "controversia",
    "humor": "humor", "comedia": "humor",
    "epico": "epico", "épico": "epico", "drama": "epico",
}


class GeminiTTSError(RuntimeError):
    """Falla de Gemini TTS que justifica usar la voz de respaldo."""


class GeminiCuotaAgotada(GeminiTTSError):
    """429: se agotó la cuota (nivel gratis) de Gemini TTS."""


def instruccion_para_tono(tono: Optional[str]) -> str:
    clave = ALIAS_TONO.get(str(tono or "").strip().lower(), "default")
    return INSTRUCCIONES_TONO[clave] + _ETIQUETAS


def _break_a_puntuacion(m: re.Match) -> str:
    attr = m.group(1) or ""
    ms = 400.0
    m_ms = re.search(r"(\d+(?:\.\d+)?)\s*ms", attr, re.IGNORECASE)
    m_s = re.search(r"(\d+(?:\.\d+)?)\s*s\b", attr, re.IGNORECASE)
    if m_ms:
        ms = float(m_ms.group(1))
    elif m_s:
        ms = float(m_s.group(1)) * 1000.0
    return " [pausa corta] " if ms >= 650 else ("… " if ms >= 300 else ", ")


def texto_para_gemini(texto: str) -> str:
    """Texto a enviar: SSML -> puntuación, conserva sólo [susurro] y [pausa corta]."""
    t = re.sub(r"<\s*(?:break|pause)\b([^>]*)/?\s*>", _break_a_puntuacion, texto or "", flags=re.IGNORECASE)
    t = re.sub(r"<[^>]+>", " ", t)

    def _tag(m: re.Match) -> str:
        interior = re.sub(r"\s+", " ", m.group(0)[1:-1]).strip().lower()
        if interior == "susurro":
            return " [susurro] "
        if interior in ("pausa", "pausa corta"):
            return " [pausa corta] "
        return " "

    t = RE_TAG_ACTUACION.sub(_tag, t)
    t = re.sub(r"\s+([,.;:!?…])", r"\1", t)
    t = re.sub(r"(?:…|\.){2,}", "…", t)
    t = re.sub(r"[,\s]*,", ",", t)
    return re.sub(r"\s+", " ", t).strip()


def armar_peticion(texto: str, tono: Optional[str], voz: str) -> dict:
    prompt = instruccion_para_tono(tono) + "\n\n" + texto_para_gemini(texto)
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}},
        },
    }


def _parsear_429(resp: requests.Response) -> tuple[bool, float]:
    """Devuelve (es_cuota_diaria, segundos_de_espera_sugeridos)."""
    try:
        err = resp.json().get("error", {})
    except ValueError:
        return False, 20.0
    diaria = False
    espera = 20.0
    for det in err.get("details", []) or []:
        tipo = str(det.get("@type", ""))
        if tipo.endswith("QuotaFailure"):
            for v in det.get("violations", []) or []:
                ident = f"{v.get('quotaId', '')} {v.get('quotaMetric', '')}"
                if "PerDay" in ident or "per_day" in ident.lower():
                    diaria = True
        elif tipo.endswith("RetryInfo"):
            m = re.match(r"([\d.]+)s", str(det.get("retryDelay", "")))
            if m:
                espera = float(m.group(1))
    if "per day" in str(err.get("message", "")).lower():
        diaria = True
    return diaria, espera


def pedir_pcm(
    texto: str,
    tono: Optional[str],
    voz: str = "Charon",
    *,
    reintentos_429: int = 3,
    espera_max_s: float = 65.0,
    dormir: Callable[[float], None] = time.sleep,
    post: Callable[..., requests.Response] = requests.post,
) -> bytes:
    """Pide el audio a Gemini y devuelve PCM 16-bit mono 24 kHz."""
    clave = config.GEMINI_API_KEY
    if not clave:
        raise GeminiTTSError("GEMINI_API_KEY no está configurada en .env")
    url = URL_TTS.format(modelo=MODELO_TTS)
    cuerpo = armar_peticion(texto, tono, voz)
    intentos_429 = 0
    intentos_vacios = 0
    while True:
        try:
            resp = post(url, json=cuerpo, headers={"x-goog-api-key": clave}, timeout=120)
        except requests.RequestException as e:
            raise GeminiTTSError(f"error de red con Gemini TTS: {type(e).__name__}") from None
        if resp.status_code == 429:
            diaria, espera = _parsear_429(resp)
            if diaria:
                raise GeminiCuotaAgotada("429: cuota diaria del nivel gratis agotada")
            intentos_429 += 1
            if intentos_429 > reintentos_429:
                raise GeminiCuotaAgotada("429 persistente (límite por minuto)")
            dormir(min(espera_max_s, espera + 1.0))
            continue
        if resp.status_code != 200:
            raise GeminiTTSError(f"Gemini TTS respondió HTTP {resp.status_code}")
        try:
            data = resp.json()
            b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
            pcm = base64.b64decode(b64)
        except (ValueError, KeyError, IndexError, TypeError):
            pcm = b""
        if len(pcm) >= SAMPLE_RATE:  # al menos ~0.5 s de audio
            return pcm
        intentos_vacios += 1
        if intentos_vacios > 1:
            raise GeminiTTSError("Gemini TTS devolvió una respuesta sin audio")


def duracion_maxima_razonable(texto: str) -> float:
    """Tope para detectar audio anómalo (Gemini a veces alucina silencios o ruido largo)."""
    n = len(quitar_tags_actuacion(re.sub(r"<[^>]+>", " ", texto or "")).split())
    return max(6.0, n * 0.9 + 3.0)


def _duracion_mp3(ruta: Path) -> float:
    ffprobe = config.ffmpeg_bin("ffprobe") or "ffprobe"
    res = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(ruta)],
        capture_output=True, text=True,
    )
    return float(res.stdout.strip())


def pcm_a_mp3(pcm: bytes, destino_mp3: Path, tempo: float = 1.0) -> float:
    """Guarda el PCM, recorta pausas largas y exporta mp3 (24 kHz mono). Devuelve la duración."""
    destino_mp3 = Path(destino_mp3)
    destino_mp3.parent.mkdir(parents=True, exist_ok=True)
    wav_tmp = destino_mp3.with_suffix(".gemini.wav")
    with wave.open(str(wav_tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    filtros = FILTRO_PAUSAS
    if abs(tempo - 1.0) > 0.005:
        filtros += f",atempo={tempo:.3f}"
    ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav_tmp), "-af", filtros,
             "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "libmp3lame", "-b:a", "128k", str(destino_mp3)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    finally:
        if wav_tmp.exists():
            wav_tmp.unlink()
    return _duracion_mp3(destino_mp3)


def sintetizar_escena_gemini(texto: str, tono: Optional[str], destino_mp3: Path, voz: str = "Charon", **kw) -> float:
    """Sintetiza una escena con Gemini y la deja en mp3. Reintenta una vez si el audio sale anómalo."""
    tempo = float(os.getenv("GEMINI_TTS_TEMPO", "1.0") or 1.0)
    tope = duracion_maxima_razonable(texto)
    for intento in range(2):
        pcm = pedir_pcm(texto, tono, voz, **kw)
        dur = pcm_a_mp3(pcm, destino_mp3, tempo=tempo)
        if dur <= tope:
            return dur
    raise GeminiTTSError(f"audio anómalo de Gemini ({dur:.1f}s para un tope de {tope:.1f}s)")
