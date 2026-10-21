"""Etapa 1: investigación con grounding + estructuración del guion en JSON de escenas.

Se hace en DOS llamadas porque Gemini no permite combinar la herramienta google_search
con response_schema (salida JSON estricta) en la misma petición.
"""
from __future__ import annotations

import json
import time
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
    return genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=types.HttpOptions(client_args={"verify": False}),
    )


# ------------------------------------------------------------------ paso A
PROMPT_INVESTIGACION = """Eres guionista y creador de contenido de YouTube especializado en rankings y TOPS DINÁMICOS
(estilo 'Los 5 casos más impresionantes...', 'Top 5 tecnologías que cambiarán el mundo', etc.), en español latino neutro.

TEMA: {tema}

1. Investiga y selecciona un TOP 5 (o Top 7) riguroso, fascinante y de alto impacto sobre este tema.
2. Organiza los puestos en cuenta regresiva desde el puesto menos conocido/curioso (#5) hasta el número 1 indiscutible (#1).
3. Escribe un BORRADOR NARRATIVO de aproximadamente {palabras} palabras con esta estructura:
   - Gancho inicial breve (10 segundos): Plantea el misterio o la pregunta central del ranking.
   - Puestos #5, #4, #3, #2 y #1: Cada puesto debe explicar claramente de qué se trata, por qué merece su posición y un dato sorprendente.
   - Conclusión / Pregunta al espectador (10 segundos) para generar comentarios.
   - Frases ágiles, sin relleno, vocabulario directo y entretenido.
"""


def investigar(tema: str, minutos: float) -> tuple[str, list[dict]]:
    palabras = int(minutos * 60 * config.PALABRAS_POR_SEG)
    prompt = PROMPT_INVESTIGACION.format(tema=tema, palabras=palabras)
    client = _cliente()
    fuentes: list[dict] = []

    # Intento 1: Con Google Search grounding
    try:
        resp = client.models.generate_content(
            model=config.MODELO_GUION,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.7,
            ),
        )
        meta = resp.candidates[0].grounding_metadata if resp.candidates else None
        if meta and meta.grounding_chunks:
            vistos = set()
            for ch in meta.grounding_chunks:
                if ch.web and ch.web.uri not in vistos:
                    vistos.add(ch.web.uri)
                    fuentes.append({"titulo": ch.web.title or ch.web.uri, "url": ch.web.uri})
        return resp.text or "", fuentes
    except Exception as e:
        print(f"⚠️ Aviso: Grounding no disponible ({e}). Generando con conocimiento interno...")

    # Intento 2: Fallback con modelos disponibles
    modelos_candidatos = [config.MODELO_GUION, "gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
    for mod in modelos_candidatos:
        for intento in range(2):
            try:
                resp = client.models.generate_content(
                    model=mod,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.7),
                )
                return resp.text or "", [{"titulo": "Investigación Curada Gemini AI", "url": "https://ai.google.dev"}]
            except Exception as e:
                print(f"⚠️ Reintento {intento+1}/2 con {mod} en investigación: {e}")
                time.sleep(2)

    raise RuntimeError("No fue posible generar el guion tras varios intentos.")


# ------------------------------------------------------------------ paso B
PROMPT_ESTRUCTURA = """Convierte la investigación en un GUION DE MONTAJE para un video formato TOP / RANKING.

REGLAS ESTRICTAS DE FORMATO TOP:
- Cada escena dura MÁXIMO 10 segundos: el campo "voz" tiene ENTRE 12 y {max_pal} palabras.
- Organiza los puestos en cuenta regresiva (#5, #4, #3, #2, #1).
- En la PRIMERA escena de cada puesto, pon en "texto_pantalla" el cartel del puesto en mayúsculas (ej: "#5: NOMBRE DEL CASO").
  En las demás escenas de ese mismo puesto, pon "texto_pantalla" en blanco ("").
- NO agregues subtítulos de la narración en "texto_pantalla". Solo el título del puesto.
- Pose del Host:
  * Cuando se introduce un nuevo puesto (#5, #4...): 'senalando' o 'alerta' o 'eureka'.
  * Durante las explicaciones técnicas: 'explicando' o 'pensativo'.
  * En la intro/cierre: 'neutro' o 'riendo'.
- host_visible: true al anunciar cada puesto (#X) y en la conclusión; pon host_visible = false cuando se deba ver el clip a pantalla completa.
- broll_query_en: IMPORTANTE: incluye términos específicos y precisos en inglés para descargar clips REALES de archivo, noticias, entrevistas, celebridades y juicios (ej: "Sean Diddy Combs court hearing press conference", "Diddy mansion raid footage news", "celebrities red carpet party Sean Combs").
- sfx: pon 'whoosh' o 'transicion' al entrar a un nuevo puesto (#X); pon 'ninguno' en el resto.

MATERIAL:
{material}
"""


def estructurar(material: str, minutos: float) -> Guion:
    palabras = int(minutos * 60 * config.PALABRAS_POR_SEG)
    # Calibrar para que alcance exactamente la duración solicitada (cada escena dura ~9.5s)
    n_escenas = max(5, round(minutos * 60 / 9.5))
    prompt = PROMPT_ESTRUCTURA.format(
        minutos=minutos, palabras=palabras, n_escenas=n_escenas,
        max_pal=config.MAX_PALABRAS_ESCENA, material=material,
    )
    prompt += f"\n\nATENCIÓN OBLIGATORIA: El video debe durar {minutos} minutos exactos. Debes generar AL MENOS {n_escenas} escenas en total (aproximadamente {max(3, n_escenas // 5)} escenas detalladas por cada puesto del Top). NO RESUMAS en pocas escenas."
    client = _cliente()
    # Lista de modelos de respaldo para evitar fallos por 503 (alta demanda)
    modelos_candidatos = [config.MODELO_ESTRUCTURA, "gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
    for mod in modelos_candidatos:
        for intento in range(3):
            try:
                resp = client.models.generate_content(
                    model=mod,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=Guion,
                        temperature=0.4,
                    ),
                )
                if resp.parsed is not None:
                    return resp.parsed
                return Guion.model_validate_json(resp.text)
            except Exception as e:
                print(f"⚠️ Reintento {intento+1}/3 con modelo {mod} tras aviso: {e}")
                time.sleep(3)

    raise RuntimeError("No se pudo estructurar el guion tras múltiples intentos.")


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

    if p.datos.get("sin_host", False):
        for e in g.escenas:
            e.host_visible = False

    p.ruta("guion", "guion.json").write_text(json.dumps(g.model_dump(), ensure_ascii=False, indent=2), "utf-8")
    p.ruta("guion", "guion_montaje.txt").write_text(_montaje_txt(p, g), "utf-8")
    p.ruta("guion", "guion_doblaje.md").write_text(_guion_doblaje_md(p, g), "utf-8")
    p.ruta("guion", "fuentes.md").write_text(
        "# Fuentes\n\n" + "\n".join(f"- [{f['titulo']}]({f['url']})" for f in fuentes) + "\n", "utf-8"
    )
    p.marcar("guion", "revisar")
    return validar(g)


def _guion_doblaje_md(p: Proyecto, g: Guion) -> str:
    """Genera guía de locución profesional para doblaje humano / teleprompter."""
    tonos_por_pose = {
        "neutro": "Tono profesional, narración fluida y aplomada",
        "explicando": "Tono didáctico, enfatizar conceptos técnicos",
        "pensativo": "Tono reflexivo, ritmo pausado, sospecha",
        "alerta": "Tono de urgencia, tensión y respiración marcada",
        "eureka": "Tono entusiasta, revelación, volumen ascendente",
        "senalando": "Tono asertivo, dirección clara hacia el dato",
        "esceptico": "Tono interrogativo, ligera ironía o duda",
        "riendo": "Tono ligero, empatía, sonrisa en la voz",
    }
    lineas = [
        f"# 🎙️ Guion de Locución y Doblaje Profesional: {p.tema}",
        f"> **Proyecto:** `{p.datos.get('slug')}` | **Duración objetivo:** {p.datos.get('minutos', 1.0)} min",
        "> **Instrucción para el locutor:** Respete los tiempos de entrada indicados para mantener la sincronización con el montaje visual.",
        "\n---\n"
    ]
    t = 0.0
    for e in g.escenas:
        palabras = e.voz.split()
        conteo = len(palabras)
        dur_est = min(conteo / config.PALABRAS_POR_SEG, config.MAX_SEG_ESCENA)
        ini_str = f"{int(t//60):02d}:{int(t%60):02d}"
        fin_str = f"{int((t+dur_est)//60):02d}:{int((t+dur_est)%60):02d}"
        tono = tonos_por_pose.get(e.pose, "Tono documental neutro")
        
        # Resaltar en negrita la palabra clave o texto en pantalla
        texto_destacado = e.voz
        if e.texto_pantalla and e.texto_pantalla.lower() in e.voz.lower():
            # resaltar si coincide
            idx = e.voz.lower().find(e.texto_pantalla.lower())
            if idx != -1:
                pal_orig = e.voz[idx:idx+len(e.texto_pantalla)]
                texto_destacado = e.voz[:idx] + f"**{pal_orig}**" + e.voz[idx+len(e.texto_pantalla):]

        lineas.append(f"### Escena {e.id:02d} `[{ini_str} - {fin_str}]` *(~{dur_est:.1f}s | {conteo} palabras)*")
        lineas.append(f"> **Dirección de voz:** [{tono}]")
        if e.texto_pantalla:
            lineas.append(f"> **Palabra en pantalla:** `{e.texto_pantalla}`")
        lineas.append(f"\n> **LOCUCIÓN:**\n> \"{texto_destacado}\"\n")
        lineas.append("---\n")
        t += dur_est

    return "\n".join(lineas)


def cargar_guion(p: Proyecto) -> Guion:
    """Lee guion.json (incluye las ediciones manuales del usuario)."""
    return Guion.model_validate_json(p.ruta("guion", "guion.json").read_text("utf-8"))
