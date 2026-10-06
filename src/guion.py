"""Etapa 1: investigación con grounding + estructuración del guion en JSON de escenas.

Se hace en DOS llamadas porque Gemini no permite combinar la herramienta google_search
con response_schema (salida JSON estricta) en la misma petición.
"""
from __future__ import annotations

import json
from typing import Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from . import config
from .estado import Proyecto

Pose = Literal["neutro", "explicando", "pensativo", "alerta", "eureka", "senalando", "esceptico", "riendo"]
Sfx = Literal["ninguno", "whoosh", "impacto", "tension", "revelacion", "glitch", "ambiente", "digital", "transicion"]
Mood = Literal["misterio", "tension", "epica", "curiosidad", "calma"]
Acto = Literal["gancho", "contexto", "conflicto", "profundizacion", "giro", "resolucion", "cta"]
Lado = Literal["izquierda", "derecha"]


class Escena(BaseModel):
    id: int
    acto: Acto
    voz: str = Field(description="Texto que lee la voz en off. Máximo 25 palabras.")
    pose: Pose
    host_visible: bool
    host_lado: Lado
    broll_query_en: str = Field(description="3-6 palabras EN INGLÉS para buscar en Pexels/Pixabay.")
    broll_descripcion: str = Field(description="Descripción visual concreta del plano ideal, en español.")
    texto_pantalla: str = Field(description="2-4 palabras clave en MAYÚSCULAS, o cadena vacía.")
    sfx: Sfx
    music_mood: Mood
    short_id: Optional[int] = Field(description="1, 2 o 3 si la escena pertenece a un Short; null si no.")
    capitulo: Optional[str] = Field(description="Título de capítulo si esta escena abre uno; null si no.")


class Guion(BaseModel):
    titulo_trabajo: str
    resumen: str
    escenas: list[Escena]


def _cliente() -> genai.Client:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en .env")
    return genai.Client(api_key=config.GEMINI_API_KEY)


# ------------------------------------------------------------------ paso A
PROMPT_INVESTIGACION = """Eres guionista e investigador de un canal de YouTube de documentales de divulgación
llamado en el nicho "cómo funciona el mundo" (ciencia, tecnología, historia de inventos), en español latino neutro.

TEMA: {tema}

1. Investiga el tema con Google Search. Prioriza fuentes primarias, académicas, museos, agencias y medios serios.
2. Escribe un DOSSIER con los hechos clave, fechas, cifras y personajes (cada dato debe ser verificable).
3. Escribe un BORRADOR NARRATIVO completo de aproximadamente {palabras} palabras para voz en off, con esta estructura:
   gancho (primeros 10 s, imposible de ignorar) → contexto → conflicto/problema → profundización → giro → resolución → CTA breve.
   - Inserta un "mini-gancho" (pregunta, dato sorprendente o promesa) aproximadamente cada 150 palabras.
   - Frases cortas, ritmo ágil, tono cercano pero riguroso. Nada de relleno ni frases genéricas.
   - No inventes datos. Si algo es incierto o debatido, dilo explícitamente.
"""


def investigar(tema: str, minutos: float) -> tuple[str, list[dict]]:
    palabras = int(minutos * 60 * config.PALABRAS_POR_SEG)
    resp = _cliente().models.generate_content(
        model=config.MODELO_GUION,
        contents=PROMPT_INVESTIGACION.format(tema=tema, palabras=palabras),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.7,
        ),
    )
    fuentes: list[dict] = []
    meta = resp.candidates[0].grounding_metadata if resp.candidates else None
    if meta and meta.grounding_chunks:
        vistos = set()
        for ch in meta.grounding_chunks:
            if ch.web and ch.web.uri not in vistos:
                vistos.add(ch.web.uri)
                fuentes.append({"titulo": ch.web.title or ch.web.uri, "url": ch.web.uri})
    return resp.text or "", fuentes


# ------------------------------------------------------------------ paso B
PROMPT_ESTRUCTURA = """Convierte el siguiente dossier y borrador en un GUION DE MONTAJE estructurado por escenas.

REGLAS ESTRICTAS:
- Duración objetivo: {minutos} minutos ≈ {palabras} palabras en total, repartidas en ~{n_escenas} escenas.
- Cada escena dura como máximo 10 segundos: el campo "voz" tiene ENTRE 12 y {max_pal} palabras. Nunca más de {max_pal}.
- Conserva los datos del borrador; no inventes nada nuevo.
- Pose del Host según la emoción: problema/duda → pensativo o esceptico; riesgo/peligro → alerta;
  solución/descubrimiento → eureka; explicación → explicando; mostrar algo → senalando; humor → riendo; resto → neutro.
- host_visible = true aprox. en 40% de las escenas (siempre en gancho, giros y CTA); el resto es B-roll a pantalla completa.
  Alterna host_lado para dar variedad.
- broll_query_en: términos visuales concretos y filmables en inglés (ej. "silicon wafer macro cleanroom"), nunca abstractos.
- texto_pantalla: solo en escenas con un dato o palabra clave fuerte; si no, cadena vacía.
- sfx: usa "whoosh"/"transicion" en cambios de acto, "impacto" en datos fuertes, "revelacion" en giros; "ninguno" en la mayoría.
- music_mood: mantenlo estable dentro de cada acto.
- capitulo: pon un título corto en la primera escena de cada acto (después del gancho), null en las demás.
- short_id: marca 2 o 3 secuencias de escenas CONSECUTIVAS (30-50 s cada una, 4-6 escenas) que funcionen solas
  como Short vertical, empezando con un gancho fuerte. Numéralas 1, 2, 3. El resto null.
- ids consecutivos empezando en 1.

MATERIAL:
{material}
"""


def estructurar(material: str, minutos: float) -> Guion:
    palabras = int(minutos * 60 * config.PALABRAS_POR_SEG)
    n_escenas = round(minutos * 60 / 9)
    resp = _cliente().models.generate_content(
        model=config.MODELO_ESTRUCTURA,
        contents=PROMPT_ESTRUCTURA.format(
            minutos=minutos, palabras=palabras, n_escenas=n_escenas,
            max_pal=config.MAX_PALABRAS_ESCENA, material=material,
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Guion,
            temperature=0.4,
        ),
    )
    if resp.parsed is not None:
        return resp.parsed
    return Guion.model_validate_json(resp.text)


# ------------------------------------------------------------------ salida
def _montaje_txt(p: Proyecto, g: Guion) -> str:
    t = 0.0
    lineas = [f"PROYECTO: {p.tema}", "FORMATO: 16:9 (Documental TV)", f"TÍTULO DE TRABAJO: {g.titulo_trabajo}", "-" * 80]
    for e in g.escenas:
        dur = min(len(e.voz.split()) / config.PALABRAS_POR_SEG, config.MAX_SEG_ESCENA)
        ini, fin = t, t + dur
        t = fin
        if e.capitulo:
            lineas.append(f"\n=== CAPÍTULO: {e.capitulo} ===")
        short = f"  [SHORT {e.short_id}]" if e.short_id else ""
        lineas += [
            f"\n{int(ini//60)}:{int(ini%60):02d} - {int(fin//60)}:{int(fin%60):02d} | Escena {e.id} ({e.acto}){short}",
            f"  -> VOICEOFF: \"{e.voz}\"",
            f"  -> VISUAL: " + (f"Host '{e.pose}' a la {e.host_lado}" if e.host_visible else "B-roll a pantalla completa")
            + (f" | TEXTO: {e.texto_pantalla}" if e.texto_pantalla else ""),
            f"  -> B-ROLL: {e.broll_descripcion}  (búsqueda: {e.broll_query_en})",
            f"  -> SFX: {e.sfx} | MÚSICA: {e.music_mood}",
        ]
    lineas.append(f"\nDURACIÓN ESTIMADA: {int(t//60)}:{int(t%60):02d}")
    return "\n".join(lineas)


def validar(g: Guion) -> list[str]:
    avisos = []
    for e in g.escenas:
        n = len(e.voz.split())
        if n > config.MAX_PALABRAS_ESCENA:
            avisos.append(f"Escena {e.id}: {n} palabras (máx {config.MAX_PALABRAS_ESCENA}); la etapa de voz la acortará.")
    shorts = {e.short_id for e in g.escenas if e.short_id}
    if len(shorts) < 2:
        avisos.append(f"Solo se marcaron {len(shorts)} Short(s).")
    return avisos


def etapa_guion(p: Proyecto) -> list[str]:
    minutos = p.datos["minutos"]
    print(f"🔎 Investigando '{p.tema}' con {config.MODELO_GUION} + Google Search…")
    material, fuentes = investigar(p.tema, minutos)
    p.ruta("guion", "investigacion.md").write_text(material, "utf-8")

    print(f"🧱 Estructurando en escenas con {config.MODELO_ESTRUCTURA}…")
    g = estructurar(material, minutos)

    p.ruta("guion", "guion.json").write_text(json.dumps(g.model_dump(), ensure_ascii=False, indent=2), "utf-8")
    p.ruta("guion", "guion_montaje.txt").write_text(_montaje_txt(p, g), "utf-8")
    p.ruta("guion", "fuentes.md").write_text(
        "# Fuentes\n\n" + "\n".join(f"- [{f['titulo']}]({f['url']})" for f in fuentes) + "\n", "utf-8"
    )
    p.marcar("guion", "revisar")
    return validar(g)


def cargar_guion(p: Proyecto) -> Guion:
    """Lee guion.json (incluye las ediciones manuales del usuario)."""
    return Guion.model_validate_json(p.ruta("guion", "guion.json").read_text("utf-8"))
