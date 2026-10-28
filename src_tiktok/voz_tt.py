"""Voz de los Reels/Shorts verticales (9:16).

Motor seleccionable con la variable VOZ_REEL (en .env o el entorno):
    VOZ_REEL=gemini:Charon            -> Gemini TTS, voz Charon (predeterminado)
    VOZ_REEL=edge:es-MX-JorgeNeural   -> Edge-TTS Jorge (+12 %), la voz anterior
    (también valen "gemini", "edge", "jorge")
Si Gemini falla o agota la cuota gratis (429) en cualquier escena, TODO el Reel se rehace con
Edge es-MX-JorgeNeural para no mezclar voces. La voz usada queda en consola, en
proyecto.json -> voz_reel y en voz/VOZ_USADA.txt.
El audio se guarda por escena (voz/escena_NNN.mp3) para que los subtítulos sigan alineados, y
se reutiliza entre `preparar` y `renderizar` si el texto no cambió (ahorra peticiones a Gemini).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import edge_tts

from src import config
from src.estado import Proyecto
from src.voz import preparar_texto_con_pausas
from src_tiktok.guion_tt import GuionTikTok

VOICE_TIKTOK = "es-MX-JorgeNeural"  # Respaldo: voz enérgica y misteriosa
RATE_TIKTOK = "+12%"                # Ritmo acelerado de TikTok para máxima retención
PITCH_TIKTOK = "-1Hz"
VOZ_REEL_DEFAULT = "gemini:Charon"
META_VOZ = "voz_meta.json"


@dataclass(frozen=True)
class VozReel:
    motor: str  # "gemini" | "edge"
    voz: str

    @property
    def etiqueta(self) -> str:
        return f"{self.motor}:{self.voz}"


RESPALDO = VozReel("edge", VOICE_TIKTOK)


def resolver_voz_reel(valor: Optional[str] = None) -> VozReel:
    v = (valor if valor is not None else os.getenv("VOZ_REEL", VOZ_REEL_DEFAULT) or VOZ_REEL_DEFAULT).strip()
    motor, _, voz = v.partition(":")
    motor = motor.strip().lower()
    voz = voz.strip()
    if motor in ("jorge", "edge"):
        return VozReel("edge", voz or VOICE_TIKTOK)
    if motor in ("gemini", "charon"):
        return VozReel("gemini", voz or "Charon")
    print(f"   ⚠️ VOZ_REEL='{v}' no reconocida; uso {VOZ_REEL_DEFAULT}")
    return VozReel("gemini", "Charon")


def _huella(voz: VozReel, tono: str, texto: str) -> str:
    return hashlib.sha1(f"{voz.etiqueta}|{tono}|{texto}".encode("utf-8")).hexdigest()[:16]


# ---------------- Edge ----------------
async def _sintetizar_escena(texto: str, destino: Path, voz: str = VOICE_TIKTOK):
    texto_limpio = preparar_texto_con_pausas(texto)
    com = edge_tts.Communicate(texto_limpio, voz, rate=RATE_TIKTOK, pitch=PITCH_TIKTOK)
    await com.save(str(destino))


def _sintetizar_todo_edge(guion: GuionTikTok, carpeta_voz: Path, voz: str) -> None:
    async def _procesar_todas():
        await asyncio.gather(*[
            _sintetizar_escena(esc.voz, carpeta_voz / f"escena_{esc.id:03d}.mp3", voz) for esc in guion.escenas
        ])
    asyncio.run(_procesar_todas())


# ---------------- Gemini ----------------
def _sintetizar_todo_gemini(guion: GuionTikTok, carpeta_voz: Path, voz: str, sintetizar: Optional[Callable] = None) -> int:
    """Sintetiza escena por escena (en secuencia, para respetar el límite por minuto). Devuelve nº de escenas."""
    if sintetizar is None:
        from src_tiktok.voz_gemini import sintetizar_escena_gemini as sintetizar
    tono = getattr(guion, "tono", "misterio") or "misterio"
    total = len(guion.escenas)
    for i, esc in enumerate(guion.escenas, 1):
        dur = sintetizar(esc.voz, tono, carpeta_voz / f"escena_{esc.id:03d}.mp3", voz=voz)
        print(f"   [{i}/{total}] Escena {esc.id}: {dur:.2f}s (Gemini {voz})")
    return total


def _duracion(ffprobe: str, archivo: Path) -> float:
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(archivo)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return float(res.stdout.strip())


def _cache_valida(carpeta_voz: Path, guion: GuionTikTok) -> Optional[dict]:
    ruta = carpeta_voz / META_VOZ
    if not ruta.exists() or os.getenv("VOZ_REEL_REGENERAR", "").strip() in ("1", "true", "si", "sí"):
        return None
    try:
        meta = json.loads(ruta.read_text(encoding="utf-8"))
        usada = VozReel(meta["motor"], meta["voz"])
    except (ValueError, KeyError):
        return None
    tono = getattr(guion, "tono", "misterio") or "misterio"
    huellas = meta.get("escenas", {})
    for esc in guion.escenas:
        if huellas.get(str(esc.id)) != _huella(usada, tono, esc.voz):
            return None
        if not (carpeta_voz / f"escena_{esc.id:03d}.mp3").exists():
            return None
    return meta


def etapa_voz_tiktok(
    p: Proyecto,
    guion: GuionTikTok,
    *,
    sintetizar_gemini: Optional[Callable] = None,
    sintetizar_edge: Optional[Callable] = None,
) -> dict[int, float]:
    carpeta_voz = p.ruta("voz")
    carpeta_voz.mkdir(parents=True, exist_ok=True)
    ffprobe = config.ffmpeg_bin("ffprobe") or "ffprobe"
    tono = getattr(guion, "tono", "misterio") or "misterio"
    sint_edge = sintetizar_edge or _sintetizar_todo_edge

    meta = _cache_valida(carpeta_voz, guion)
    if meta:
        usada = VozReel(meta["motor"], meta["voz"])
        motivo = meta.get("motivo_respaldo")
        print(f"🎙️ Reutilizando la locución ya generada ({usada.etiqueta}); el texto no cambió.")
    else:
        pedida = resolver_voz_reel()
        usada, motivo = pedida, None
        if pedida.motor == "gemini":
            print(f"🎙️ Generando voces del Reel con Gemini TTS ({pedida.voz}, tono '{tono}')...")
            try:
                _sintetizar_todo_gemini(guion, carpeta_voz, pedida.voz, sintetizar_gemini)
            except Exception as e:  # cualquier falla -> respaldo completo, sin mezclar voces
                from src_tiktok.voz_gemini import GeminiCuotaAgotada
                tipo = "cuota agotada" if isinstance(e, GeminiCuotaAgotada) else "falla"
                motivo = f"Gemini {tipo}: {str(e)[:160]}"
                print(f"   ⚠️ {motivo}. Rehago TODO el Reel con el respaldo {RESPALDO.voz}.")
                usada = RESPALDO
        if usada.motor == "edge":
            print(f"🎙️ Generando voces del Reel con Edge-TTS {usada.voz} ({RATE_TIKTOK})...")
            sint_edge(guion, carpeta_voz, usada.voz)
        meta = {
            "motor": usada.motor,
            "voz": usada.voz,
            "pedida": pedida.etiqueta,
            "motivo_respaldo": motivo,
            "escenas": {str(e.id): _huella(usada, tono, e.voz) for e in guion.escenas},
        }
        (carpeta_voz / META_VOZ).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    duraciones: dict[int, float] = {}
    for esc in guion.escenas:
        duraciones[esc.id] = _duracion(ffprobe, carpeta_voz / f"escena_{esc.id:03d}.mp3")

    resumen = f"{usada.etiqueta}" + (f" (RESPALDO: {motivo})" if motivo else "")
    print(f"🎙️ VOZ USADA EN EL REEL: {resumen}")
    (carpeta_voz / "VOZ_USADA.txt").write_text(resumen + "\n", encoding="utf-8")
    p.datos["voz_reel"] = {"motor": usada.motor, "voz": usada.voz, "pedida": meta.get("pedida"),
                           "motivo_respaldo": motivo}
    p.marcar("voz", "ok")
    return duraciones
