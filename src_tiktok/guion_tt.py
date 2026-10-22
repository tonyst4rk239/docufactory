"""Generador de guiones ultracortos para TikTok / Shorts / Reels (formato 9:16).
Enfocado en retención extrema: Hook de 2 segundos, ritmo acelerado y bucle infinito (seamless loop).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, model_validator

from src import config
from src.edicion import cargar_config_edicion
from src.estado import Proyecto
from src.guion import (
    Guion,
    _contar_palabras_habladas,
    _guion_doblaje_md,
    _montaje_txt,
    validar_json_externo,
)
from src.host_anim import es_mood_oscuro_sin_dinero, normalizar_pose


def _extraer_keyword_automatica(voz: str) -> str:
    limpio = re.sub(r"<[^>]+>", " ", voz or "")
    palabras = re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]{4,}", limpio)
    if not palabras:
        return "SECRETO"
    palabras_ordenadas = sorted(palabras, key=len, reverse=True)
    return palabras_ordenadas[0].upper()


class EscenaTikTok(BaseModel):
    id: int
    voz: str = Field(description="Narración ultrarrápida para corte de 2 a 3 segundos (admite pausas SSML)")
    broll_query_en: str = Field(default="", description="Búsqueda principal en inglés para B-roll")
    broll_queries_en: list[str] = Field(default_factory=list, description="2 a 3 consultas en inglés para B-roll")
    broll_mood_keywords: list[str] = Field(default_factory=list, description="Palabras de mood en inglés")
    broll_avoid_keywords: list[str] = Field(default_factory=list, description="Términos a evitar en inglés")
    texto_destacado: str = Field(default="", description="1 a 2 palabras clave en MAYÚSCULAS para zoom punch y resalte karaoke")
    pose_host: str = Field(default="sorprendido", description="sorprendido, senalando, pensativo, explicando, esceptico, duda, aprobando")
    sfx: str = Field(default="whoosh", description="whoosh, impacto, riser, tension, revelacion, glitch, digital, click, ninguno")
    music_mood: str = Field(default="misterio", description="misterio, tension, epica, curiosidad, calma")
    puesto: Optional[int] = Field(default=None)
    puesto_titulo: Optional[str] = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _normalizar_escena_tt(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        for alias_voz in ("narracion", "texto_narracion", "texto"):
            if alias_voz in d and not d.get("voz"):
                d["voz"] = d[alias_voz]
        if "pose" in d and not d.get("pose_host"):
            d["pose_host"] = d["pose"]
        if "musica" in d and not d.get("music_mood"):
            d["music_mood"] = d["musica"]
        queries = d.get("broll_queries_en")
        q_single = (d.get("broll_query_en") or "").strip()
        if isinstance(queries, list) and queries:
            limpias = [str(q).strip() for q in queries if str(q).strip()]
            d["broll_queries_en"] = limpias
            if not q_single and limpias:
                d["broll_query_en"] = limpias[0]
        elif q_single:
            d["broll_queries_en"] = [q_single]
        if not d.get("texto_destacado"):
            d["texto_destacado"] = _extraer_keyword_automatica(str(d.get("voz") or ""))
        return d


class GuionTikTok(BaseModel):
    titulo: str
    mood: str = "misterio"
    hook: str = ""
    bucle_loop_frase: str = ""
    tono: str = "misterio"
    usar_avatar: bool = True
    miniatura: Optional[dict] = None
    escenas: list[EscenaTikTok]

    @model_validator(mode="before")
    @classmethod
    def _normalizar_guion_tt(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        from src.guion import TONOS_VALIDOS, _ALIAS_TONO
        t_raw = str(d.get("tono") or "misterio").strip().lower()
        t_raw = _ALIAS_TONO.get(t_raw, t_raw)
        if t_raw not in TONOS_VALIDOS:
            raise ValueError(f"tono inválido '{t_raw}'. Usa uno de: {', '.join(TONOS_VALIDOS)}")
        d["tono"] = t_raw
        if isinstance(d.get("usar_avatar"), str):
            d["usar_avatar"] = d["usar_avatar"].strip().lower() not in ("false", "no", "0")
        if not d.get("titulo") and d.get("titulo_trabajo"):
            d["titulo"] = d["titulo_trabajo"]
        escenas = d.get("escenas") or []
        if not d.get("hook") and escenas and isinstance(escenas[0], dict):
            d["hook"] = str(escenas[0].get("voz") or escenas[0].get("narracion") or "")
        if not d.get("bucle_loop_frase") and escenas and isinstance(escenas[-1], dict):
            d["bucle_loop_frase"] = str(escenas[-1].get("voz") or escenas[-1].get("narracion") or "")
        return d


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
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en .env")
    return genai.Client(api_key=config.GEMINI_API_KEY)


def guion_general_a_tiktok(g: Guion) -> GuionTikTok:
    """Convierte un objeto Guion unificado en GuionTikTok preservando queries, mood y poses validadas."""
    escenas_tt: list[EscenaTikTok] = []
    mood_ref = g.mood_original or g.mood or "misterio"
    for e in g.escenas:
        pose_limpia = normalizar_pose(
            e.pose,
            mood=mood_ref if es_mood_oscuro_sin_dinero(mood=mood_ref) else e.music_mood,
            tema=g.titulo_trabajo,
            texto_voz=e.voz,
        )
        kw = e.texto_destacado or e.puesto_titulo or _extraer_keyword_automatica(e.voz)
        escenas_tt.append(
            EscenaTikTok(
                id=e.id,
                voz=e.voz,
                broll_query_en=e.broll_query_en or (e.broll_queries_en[0] if e.broll_queries_en else ""),
                broll_queries_en=list(e.broll_queries_en or ([e.broll_query_en] if e.broll_query_en else [])),
                broll_mood_keywords=list(e.broll_mood_keywords),
                broll_avoid_keywords=list(e.broll_avoid_keywords),
                texto_destacado=kw,
                pose_host=pose_limpia,
                sfx=e.sfx if e.sfx != "ninguno" else "whoosh",
                music_mood=e.music_mood,
                puesto=e.puesto,
                puesto_titulo=e.puesto_titulo,
            )
        )
    hook = g.hook or (escenas_tt[0].voz if escenas_tt else g.titulo_trabajo)
    bucle = g.bucle_loop_frase or (escenas_tt[-1].voz if escenas_tt else "")
    return GuionTikTok(
        titulo=g.titulo_trabajo,
        mood=g.mood,
        hook=hook,
        bucle_loop_frase=bucle,
        tono=getattr(g, "tono", "misterio"),
        usar_avatar=getattr(g, "usar_avatar", True),
        miniatura=g.miniatura.model_dump() if getattr(g, "miniatura", None) else None,
        escenas=escenas_tt,
    )


def importar_guion_tiktok(
    ruta_json: Path,
    reusar: bool = False,
) -> tuple[Proyecto, GuionTikTok, list[str]]:
    """Valida e importa un archivo JSON de guion para formato vertical 9:16 (Reels/TikTok)."""
    guion_obj, errores, avisos = validar_json_externo(ruta_json, formato_esperado="9:16")
    if errores or guion_obj is None:
        detalle = "\n".join(f"  ❌ [{e}]" for e in errores)
        raise ValueError(f"El archivo '{ruta_json}' contiene errores de validación:\n{detalle}")

    guion_obj.formato = "9:16"
    palabras_tot = sum(_contar_palabras_habladas(e.voz) for e in guion_obj.escenas)
    minutos_calc = guion_obj.minutos or round(max(0.25, palabras_tot / 165.0), 2)
    guion_obj.minutos = minutos_calc

    try:
        p = Proyecto.crear(guion_obj.titulo_trabajo, minutos=minutos_calc, lang="es", reusar=reusar)
    except TypeError:
        p = Proyecto.crear(guion_obj.titulo_trabajo, minutos=minutos_calc, lang="es")
    p.datos["formato"] = "9:16"
    p.datos["mood"] = guion_obj.mood
    p.datos["mood_original"] = guion_obj.mood_original
    p.datos["guion_origen"] = str(ruta_json.resolve())

    if hasattr(p, "invalidar_cache_si_guion_cambio"):
        p.invalidar_cache_si_guion_cambio(guion_obj.escenas)

    guion_tt = guion_general_a_tiktok(guion_obj)
    p_guion = p.ruta("guion")
    p_guion.mkdir(parents=True, exist_ok=True)
    (p_guion / "guion_tiktok.json").write_text(
        json.dumps(guion_tt.model_dump(), ensure_ascii=False, indent=2), "utf-8"
    )
    (p_guion / "guion.json").write_text(
        json.dumps(guion_obj.model_dump(), ensure_ascii=False, indent=2), "utf-8"
    )
    (p_guion / "guion_montaje.txt").write_text(_montaje_txt(p, guion_obj), "utf-8")
    (p_guion / "guion_doblaje.md").write_text(_guion_doblaje_md(p, guion_obj), "utf-8")
    p.marcar("guion", "revisar")
    return p, guion_tt, avisos


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
                    for esc in guion.escenas:
                        esc.pose_host = normalizar_pose(esc.pose_host, mood=guion.mood, tema=p.tema, texto_voz=esc.voz)
                    if hasattr(p, "invalidar_cache_si_guion_cambio"):
                        p.invalidar_cache_si_guion_cambio(guion.escenas)
                    p_guion = p.ruta("guion")
                    p_guion.mkdir(parents=True, exist_ok=True)
                    (p_guion / "guion_tiktok.json").write_text(guion.model_dump_json(indent=2), "utf-8")
                    p.marcar("guion", "ok")
                    return guion
            except Exception as e:
                print(f"⚠️ Reintento {intento+1}/3 con {mod}: {e}")
                time.sleep(2)

    raise RuntimeError("No fue posible generar el guion vertical de TikTok.")
