"""Generador de guiones ultracortos para TikTok / Shorts / Reels (formato 9:16).
Enfocado en retención extrema: Hook de 2 segundos, ritmo acelerado y bucle infinito (seamless loop).
"""
from __future__ import annotations

import json
import time
from typing import Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from src import config
from src.edicion import cargar_config_edicion
from src.estado import Proyecto


class EscenaTikTok(BaseModel):
    id: int
    voz: str = Field(description="Narración ultrarrápida para corte de 2 a 3 segundos (5 a 9 palabras máximo)")
    broll_query_en: str = Field(description="Búsqueda para clips reales de redes sociales, noticias de archivo, entrevistas o metraje viral en YouTube/TikTok (ej: 'diddy court hearing footage news', 'diddy mansion fbi raid abc')")
    texto_destacado: str = Field(description="1 a 2 palabras clave en MAYÚSCULAS para zoom punch y resalte karaoke")
    pose_host: str = Field(default="sorprendido", description="sorprendido, senalando, pensativo, explicando, esceptico, duda, aprobando")
    sfx: str = Field(default="whoosh", description="whoosh, impacto, tension, revelacion, glitch, teclado, ninguno")


class GuionTikTok(BaseModel):
    titulo: str
    hook: str
    bucle_loop_frase: str
    escenas: list[EscenaTikTok]


PROMPT_TIKTOK = """Crea un GUION VERTICAL PARA TIKTOK / SHORTS / REELS DE ALTA RETENCIÓN (Duración exacta: {segundos} segundos).

ESTRUCTURA PSICOLÓGICA DE REELS 9:16 (CORTES RÁPIDOS DE 2-3 SEGUNDOS):
1. SEGUNDO 0-2 (EL HOOK): La primera frase DEBE ser una pregunta paradójica, un secreto prohibido o un hecho impactante que impida hacer scroll.
2. CORTES ULTRARRÁPIDOS (2 A 3 SEGUNDOS): Divide el video en {num_escenas} micro-escenas de 2 a 3 segundos cada una (cada escena debe tener estrictamente entre 5 y 9 palabras).
3. BUCLE Y CIERRE COMPLETO: La última escena DEBE ser una frase u oración COMPLETA y contundente (una pregunta de remate que invite a debatir en comentarios). NUNCA dejes oraciones inconclusas ni cortes con puntos suspensivos.
4. TEXTO DESTACADO (KEYWORD): 1 a 2 palabras clave por escena en MAYÚSCULAS que coincidan con palabras de `voz` para activar el zoom punch y el resalte karaoke palabra por palabra.
5. CLIPS REALES DE REDES EN `broll_query_en`: NUNCA uses conceptos abstractos genéricos. Usa términos precisos en inglés (3-5 palabras) para encontrar metraje visual concreto y oscuro.

TEMA:
{tema}
"""


def _cliente() -> genai.Client:
    return genai.Client(api_key=config.GEMINI_API_KEY)


def generar_guion_tiktok(p: Proyecto, segundos: int = 30) -> GuionTikTok:
    client = _cliente()
    cfg = cargar_config_edicion()
    c_cfg = cfg.get("reels_9_16", {}).get("cortes_rapidos", {})
    dur_media_corte = (float(c_cfg.get("min_s", 2.0)) + float(c_cfg.get("max_s", 3.0))) / 2.0
    num_escenas = max(8, int(round(segundos / max(1.8, dur_media_corte))))
    prompt = PROMPT_TIKTOK.format(segundos=segundos, num_escenas=num_escenas, tema=p.tema)

    modelos = [config.MODELO_ESTRUCTURA, "gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
    for mod in modelos:
        for intento in range(3):
            try:
                resp = client.models.generate_content(
                    model=mod,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GuionTikTok,
                        temperature=0.7,
                    ),
                )
                if resp.parsed:
                    guion = resp.parsed
                    # Guardar en proyecto
                    p_guion = p.ruta("guion")
                    p_guion.mkdir(parents=True, exist_ok=True)
                    (p_guion / "guion_tiktok.json").write_text(guion.model_dump_json(indent=2), "utf-8")
                    p.marcar("guion", "ok")
                    return guion
            except Exception as e:
                print(f"⚠️ Reintento {intento+1}/3 con {mod}: {e}")
                time.sleep(2)

    raise RuntimeError("No fue posible generar el guion vertical de TikTok.")
