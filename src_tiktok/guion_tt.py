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
from src.estado import Proyecto


class EscenaTikTok(BaseModel):
    id: int
    voz: str = Field(description="Narración ultrarrápida (5 a 12 palabras)")
    broll_query_en: str = Field(description="Búsqueda para clips reales de redes sociales, noticias de archivo, entrevistas o metraje viral en YouTube/TikTok (ej: 'diddy court hearing footage news', 'diddy mansion fbi raid abc')")
    texto_destacado: str = Field(description="1 a 3 palabras clave en mayúsculas para subtítulo gigante")
    pose_host: str = Field(default="sorprendido", description="sorprendido, senalando, pensativo, explicando, esceptico, duda, aprobando")
    sfx: str = Field(default="whoosh", description="whoosh, impacto, tension, revelacion, glitch, teclado, ninguno")


class GuionTikTok(BaseModel):
    titulo: str
    hook: str
    bucle_loop_frase: str
    escenas: list[EscenaTikTok]


PROMPT_TIKTOK = """Crea un GUION VERTICAL PARA TIKTOK / SHORTS DE ALTA RETENCIÓN (Duración exacta: {segundos} segundos).

ESTRUCTURA PSICOLÓGICA DE TIKTOK:
1. SEGUNDO 0-2 (EL HOOK): La primera frase DEBE ser una pregunta paradójica, un secreto prohibido o un hecho impactante que impida hacer scroll.
2. RITMO VERTIGINOSO: Divide el video en {num_escenas} micro-escenas de 2 a 3 segundos cada una (cada escena tiene entre 6 y 14 palabras).
3. BUCLE Y CIERRE COMPLETO: La última escena DEBE ser una frase u oración COMPLETA y contundente (una pregunta de remate que invite a debatir en comentarios). NUNCA dejes oraciones inconclusas ni cortes con puntos suspensivos (ej: NO pongas 'Y la gran pregunta es...'). Debe ser un remate sólido que además conecte temáticamente con el inicio.
4. TEXTO DESTACADO: 1 a 3 palabras contundentes por escena en mayúsculas para quemar en el centro de la pantalla.
5. CLIPS REALES DE REDES EN `broll_query_en`: NUNCA uses conceptos abstractos genéricos (como 'prison' o 'money'). Usa términos precisos en inglés para encontrar metraje REAL en YouTube / TikTok / noticias de archivo sobre los personajes y eventos reales del tema (ej: 'diddy combs arrested footage news', 'sean combs miami raid helicopter abc', 'diddy white party celebrity guests video', 'diddy courtroom trial news').

TEMA:
{tema}
"""


def _cliente() -> genai.Client:
    return genai.Client(api_key=config.GEMINI_API_KEY)


def generar_guion_tiktok(p: Proyecto, segundos: int = 30) -> GuionTikTok:
    client = _cliente()
    num_escenas = max(7, round(segundos / 3.0))
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
