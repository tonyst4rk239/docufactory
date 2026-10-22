"""Etapa 1: investigación con grounding + estructuración del guion en JSON de escenas.

Se hace en DOS llamadas porque Gemini no permite combinar la herramienta google_search
con response_schema (salida JSON estricta) en la misma petición.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError, model_validator

from . import config
from .estado import Proyecto
from .host_anim import es_mood_oscuro_sin_dinero, normalizar_pose

Pose = Literal[
    "explicando", "pensativo", "sorprendido", "esceptico", "dinero", "aprobando", "duda", "senalando",
    # Alias retrocompatibles para guion.json existentes:
    "neutro", "alerta", "eureka", "riendo",
]
Sfx = Literal[
    "ninguno", "whoosh", "impacto", "impact", "riser", "tension", "revelacion",
    "glitch", "ambiente", "digital", "click", "transicion"
]
Mood = Literal["misterio", "tension", "epica", "curiosidad", "calma"]
FormatoVideo = Literal["16:9", "9:16"]
Acto = Literal["gancho", "contexto", "conflicto", "profundizacion", "giro", "resolucion", "cta"]
Lado = Literal["izquierda", "derecha"]

_MAPA_MOOD_CANONICO: dict[str, Mood] = {
    "misterio": "misterio",
    "tension": "tension",
    "tensión": "tension",
    "terror": "tension",
    "horror": "tension",
    "crimen": "misterio",
    "suspenso": "tension",
    "epica": "epica",
    "épica": "epica",
    "epico": "epica",
    "curiosidad": "curiosidad",
    "ciencia": "curiosidad",
    "calma": "calma",
}

_MAPA_SFX_CANONICO: dict[str, Sfx] = {
    "ninguno": "ninguno",
    "none": "ninguno",
    "": "ninguno",
    "whoosh": "whoosh",
    "transicion": "transicion",
    "impacto": "impacto",
    "impact": "impacto",
    "riser": "riser",
    "tension": "tension",
    "tensión": "tension",
    "revelacion": "revelacion",
    "revelación": "revelacion",
    "glitch": "glitch",
    "ambiente": "ambiente",
    "digital": "digital",
    "teclado": "digital",
    "click": "click",
}


class YouTubeMetadata(BaseModel):
    titulos: list[str] = Field(default_factory=list, description="1 a 3 títulos sugeridos para YouTube.")
    descripcion: str = Field(default="", description="Descripción optimizada para YouTube.")
    tags: list[str] = Field(default_factory=list, description="Lista de etiquetas/tags para YouTube.")

    @model_validator(mode="before")
    @classmethod
    def _normalizar_yt(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "titulo" in d and "titulos" not in d:
            t_val = d.pop("titulo")
            d["titulos"] = [t_val] if isinstance(t_val, str) else list(t_val or [])
        if isinstance(d.get("titulos"), str):
            d["titulos"] = [t.strip() for t in d["titulos"].splitlines() if t.strip()]
        if isinstance(d.get("tags"), str):
            d["tags"] = [t.strip() for t in d["tags"].split(",") if t.strip()]
        return d


class CapituloGuion(BaseModel):
    escena_id: Optional[int] = Field(default=None, description="ID de la escena donde inicia el capítulo.")
    titulo: str = Field(description="Nombre del capítulo.")
    timestamp: Optional[str] = Field(default=None, description="Marca de tiempo opcional (ej. '00:00').")

    @model_validator(mode="before")
    @classmethod
    def _normalizar_cap(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"titulo": data}
        if isinstance(data, dict):
            d = dict(data)
            if "nombre" in d and "titulo" not in d:
                d["titulo"] = d["nombre"]
            if "escena" in d and "escena_id" not in d:
                d["escena_id"] = d["escena"]
            return d
        return data


class ClipFuente(BaseModel):
    """Fragmento real (viral / redes) que se muestra transformado como panel 'EVIDENCIA'."""
    url: str = Field(description="URL del video original (YouTube, X, Facebook, TikTok o cualquier sitio soportado por yt-dlp).")
    inicio: float = Field(default=0.0, description="Segundo de inicio del fragmento.")
    duracion: float = Field(default=4.0, description="Duración del fragmento en segundos (se recorta a 3-6 s).")
    credito: str = Field(default="", description="Crédito visible en pantalla: 'Fuente: <credito>'.")
    etiqueta: str = Field(default="EVIDENCIA", description="Etiqueta superior del panel.")
    resaltar: Optional[list[float]] = Field(default=None, description="Caja de resalte opcional [x, y, w, h] en fracciones 0-1 del fragmento.")
    estilo: str = Field(default="evidencia", description="Presentación: evidencia | completo | dividido | congelado.")
    recorte: Optional[list[float]] = Field(default=None, description="Recorte previo [x, y, w, h] en fracciones 0-1 (quita barras, textos o marcos del original).")


class Escena(BaseModel):
    id: int
    acto: Acto = "contexto"
    voz: str = Field(description="Texto que lee la voz en off (admite pausas SSML <break time='400ms'/>).")
    pose: Pose = "explicando"
    host_visible: bool = True
    host_lado: Lado = "izquierda"
    broll_query_en: str = Field(default="", description="Consulta principal (3-5 palabras EN INGLÉS) para buscar en Pexels/Pixabay/YouTube.")
    broll_queries_en: list[str] = Field(
        default_factory=list,
        description="2 a 3 consultas en inglés concretas y filmables (de más específica a visualmente equivalente) para Pexels/Pixabay.",
    )
    broll_mood_keywords: list[str] = Field(
        default_factory=list,
        description="2 a 4 palabras de atmósfera/mood en inglés (ej. ['dark', 'cinematic', 'night', 'mysterious', 'archival']).",
    )
    broll_avoid_keywords: list[str] = Field(
        default_factory=list,
        description="3 a 6 términos en inglés que deben rechazarse si aparecen en los tags porque chocan con el mood o son falsos amigos visuales.",
    )
    broll_descripcion: str = Field(default="", description="Descripción visual concreta del plano ideal, en español.")
    puesto: Optional[int] = Field(
        default=None,
        description="Número del puesto del ranking (N..1) si esta escena inicia o pertenece a ese puesto; null en intro/outro.",
    )
    puesto_titulo: Optional[str] = Field(
        default=None,
        description="Título corto en MAYÚSCULAS (2-5 palabras, sin el #N) cuando esta escena INICIA un puesto del ranking; null en las demás escenas.",
    )
    texto_pantalla: str = Field(default="", description="Cartel de puesto '#N: TITULO DEL PUESTO' en la primera escena de cada puesto, o cadena vacía.")
    texto_destacado: str = Field(default="", description="1 a 2 palabras clave en MAYÚSCULAS para zoom punch y resalte karaoke en 9:16.")
    sfx: Sfx = "ninguno"
    music_mood: Mood = "misterio"
    short_id: Optional[int] = Field(default=None, description="1, 2 o 3 si la escena pertenece a un Short; null si no.")
    capitulo: Optional[str] = Field(default=None, description="Título de capítulo si esta escena abre uno; null si no.")
    clips_fuente: list[ClipFuente] = Field(default_factory=list, description="Fragmentos reales (3-6 s) priorizados sobre el B-roll libre.")

    @model_validator(mode="before")
    @classmethod
    def _normalizar_campos_escena(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        # Alias de narración
        for alias_voz in ("narracion", "texto_narracion", "texto", "locucion"):
            if alias_voz in d and not d.get("voz"):
                d["voz"] = d[alias_voz]
        # Alias de pose
        for alias_pose in ("pose_host", "host_pose"):
            if alias_pose in d and not d.get("pose"):
                d["pose"] = d[alias_pose]
        if isinstance(d.get("pose"), str):
            p_raw = d["pose"].strip().lower().translate(str.maketrans("áéíóú", "aeiou"))
            if p_raw == "señalando":
                p_raw = "senalando"
            d["pose"] = config.POSE_ALIASES.get(p_raw, p_raw)
        # Alias de música
        for alias_mus in ("musica", "musica_mood", "mood_musica", "mood"):
            if alias_mus in d and not d.get("music_mood"):
                d["music_mood"] = d[alias_mus]
        if isinstance(d.get("music_mood"), str):
            m_raw = d["music_mood"].strip().lower()
            if m_raw in _MAPA_MOOD_CANONICO:
                d["music_mood"] = _MAPA_MOOD_CANONICO[m_raw]
        # Alias de SFX
        if isinstance(d.get("sfx"), str):
            s_raw = d["sfx"].strip().lower()
            if s_raw in _MAPA_SFX_CANONICO:
                d["sfx"] = _MAPA_SFX_CANONICO[s_raw]
        # Sincronizar broll_queries_en <-> broll_query_en
        queries = d.get("broll_queries_en")
        q_single = (d.get("broll_query_en") or "").strip()
        if isinstance(queries, list) and queries:
            queries_limpias = [str(q).strip() for q in queries if str(q).strip()]
            d["broll_queries_en"] = queries_limpias
            if not q_single and queries_limpias:
                d["broll_query_en"] = queries_limpias[0]
        elif q_single:
            d["broll_queries_en"] = [q_single]
        if not d.get("broll_descripcion"):
            d["broll_descripcion"] = d.get("broll_query_en") or "Plano documental de archivo"
        # Inferir acto si no viene en JSON externo
        if not d.get("acto"):
            if d.get("id") == 1 and not d.get("puesto"):
                d["acto"] = "gancho"
            elif d.get("puesto_titulo"):
                d["acto"] = "conflicto"
            elif d.get("puesto"):
                d["acto"] = "profundizacion"
            else:
                d["acto"] = "resolucion"
        return d


class Guion(BaseModel):
    titulo_trabajo: str = Field(description="Título principal del proyecto o video.")
    formato: FormatoVideo = Field(default="16:9", description="Formato de salida: '16:9' (Documental) o '9:16' (Reel/Short).")
    mood: Mood = Field(default="misterio", description="Mood general del guion: misterio, tension, epica, curiosidad o calma.")
    mood_original: str = Field(default="misterio", description="Mood nominal original del archivo importado (ej. misterio, terror, crimen, tension).")
    top_n: Optional[int] = Field(default=None, description="Cantidad de puestos del ranking (ej. 3, 5, 7).")
    minutos: Optional[float] = Field(default=None, description="Duración objetivo en minutos.")
    resumen: str = Field(default="", description="Resumen ejecutivo o sinopsis del documental.")
    youtube_metadata: Optional[YouTubeMetadata] = Field(default=None, description="Metadatos para publicación en YouTube.")
    capitulos: list[CapituloGuion] = Field(default_factory=list, description="Lista de capítulos del video.")
    hook: Optional[str] = Field(default=None, description="Frase gancho inicial (especialmente útil en 9:16).")
    bucle_loop_frase: Optional[str] = Field(default=None, description="Frase de cierre para bucle en 9:16.")
    fuentes_video: list[dict] = Field(default_factory=list, description="Lista opcional de videos fuente del episodio (url, credito, descripcion).")
    escenas: list[Escena]

    @model_validator(mode="before")
    @classmethod
    def _normalizar_raiz_guion(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if not d.get("titulo_trabajo") and d.get("titulo"):
            d["titulo_trabajo"] = d["titulo"]
        if not d.get("youtube_metadata") and d.get("metadatos_youtube"):
            d["youtube_metadata"] = d["metadatos_youtube"]
        mood_raw = str(d.get("mood") or "misterio").strip().lower()
        d["mood_original"] = mood_raw
        d["mood"] = _MAPA_MOOD_CANONICO.get(mood_raw, mood_raw)
        if not d.get("resumen"):
            yt = d.get("youtube_metadata")
            if isinstance(yt, dict) and yt.get("descripcion"):
                d["resumen"] = str(yt["descripcion"])
            else:
                d["resumen"] = str(d.get("titulo_trabajo") or "")
        # Propagar mood general y capítulos a las escenas si no tienen uno propio
        caps_map: dict[int, str] = {}
        for c in d.get("capitulos") or []:
            if isinstance(c, dict) and c.get("escena_id") and (c.get("titulo") or c.get("nombre")):
                caps_map[int(c["escena_id"])] = str(c.get("titulo") or c.get("nombre"))
        escenas_in = d.get("escenas")
        if isinstance(escenas_in, list):
            escenas_norm = []
            for idx, esc in enumerate(escenas_in, 1):
                if isinstance(esc, dict):
                    e_copy = dict(esc)
                    if "id" not in e_copy:
                        e_copy["id"] = idx
                    if not e_copy.get("music_mood") and not e_copy.get("musica"):
                        e_copy["music_mood"] = d["mood"]
                    if not e_copy.get("capitulo") and e_copy["id"] in caps_map:
                        e_copy["capitulo"] = caps_map[e_copy["id"]]
                    escenas_norm.append(e_copy)
                else:
                    escenas_norm.append(esc)
            d["escenas"] = escenas_norm
        return d


def extraer_top_n(tema: str, minutos: float = 8.5) -> int:
    """Extrae N si el tema especifica 'Top N' / 'Los N...'; si no, calcula N según la duración."""
    if tema:
        m = re.search(r"\b(?:top|ranking|los|las|mis)\s+(\d{1,2})\b", tema, re.IGNORECASE)
        if not m:
            m = re.search(r"^\s*(\d{1,2})\s+[a-záéíóúñ]{3,}", tema, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 15:
                return n
    if minutos <= 2.5:
        return 3
    if minutos <= 9.5:
        return 5
    return max(3, min(10, round(minutos / 1.6)))


def _formatear_lista_puestos(top_n: int) -> str:
    puestos = [f"#{i}" for i in range(top_n, 0, -1)]
    if len(puestos) <= 1:
        return puestos[0] if puestos else "#1"
    return ", ".join(puestos[:-1]) + f" y {puestos[-1]}"


def _limpiar_titulo_puesto(texto: str, r: int) -> str:
    """Extrae un título corto en MAYÚSCULAS limpio sin el prefijo TOP #N."""
    limpio = re.sub(r"^(?:TOP\s*)?(?:PUESTO\s*)?#?\s*\d+\s*[:\-\.\–—]*\s*", "", (texto or "").strip(), flags=re.IGNORECASE)
    limpio = re.sub(r"\s+", " ", limpio).strip(" .,:;-—\"'«»¡!¿?")
    if not limpio:
        return f"PUESTO {r}"
    palabras = limpio.split()
    if len(palabras) > 6:
        limpio = " ".join(palabras[:5])
    return limpio.upper()


def asegurar_tarjetas_top(guion_obj: Guion, top_n: int) -> Guion:
    """Garantiza que cada puesto del ranking (#N..#1) tenga una escena de apertura con puesto, puesto_titulo y texto_pantalla '#N: TITULO'."""
    escenas = guion_obj.escenas
    if not escenas or top_n < 1:
        return guion_obj

    # Ajustar top_n si hay menos escenas que puestos
    max_puestos_posibles = max(1, len(escenas))
    top_n_efectivo = min(top_n, max_puestos_posibles)
    puestos_esperados = list(range(top_n_efectivo, 0, -1))

    # Paso 1: Detectar inicios de puesto explícitos (por esc.puesto, texto_pantalla o capitulo)
    inicio_por_puesto: dict[int, int] = {}  # puesto -> índice en escenas
    for idx, esc in enumerate(escenas):
        candidato_r: Optional[int] = None
        if esc.puesto and 1 <= esc.puesto <= top_n_efectivo:
            candidato_r = esc.puesto
        else:
            for fuente in (esc.texto_pantalla or "", esc.capitulo or ""):
                m = re.search(r"(?:#|top\s*#?|puesto\s*#?)\s*(\d{1,2})\b", fuente, re.IGNORECASE)
                if m:
                    val = int(m.group(1))
                    if 1 <= val <= top_n_efectivo:
                        candidato_r = val
                        break
        if candidato_r is not None and candidato_r not in inicio_por_puesto:
            inicio_por_puesto[candidato_r] = idx

    # Paso 2: Intentar detectar en la locución ("puesto 3", "número 2", "#1") si faltan puestos
    if len(inicio_por_puesto) < len(puestos_esperados):
        usados_idx = set(inicio_por_puesto.values())
        for r in puestos_esperados:
            if r in inicio_por_puesto:
                continue
            patron_voz = re.compile(
                rf"(?:#\s*{r}\b|\b(?:puesto|n[úu]mero|top|lugar|caso)\s+{r}\b)",
                re.IGNORECASE,
            )
            for idx, esc in enumerate(escenas):
                if idx in usados_idx:
                    continue
                if patron_voz.search(esc.voz or ""):
                    inicio_por_puesto[r] = idx
                    usados_idx.add(idx)
                    break

    # Paso 3: Si aún falta algún puesto, asignarlo determinísticamente en orden regresivo (#N..#1)
    if len(inicio_por_puesto) < len(puestos_esperados):
        # Reservamos la escena 0 como gancho si hay suficientes escenas, y la última como cierre si hay margen
        ini_cuerpo = 1 if len(escenas) > top_n_efectivo + 1 else 0
        fin_cuerpo = len(escenas) - 1 if len(escenas) > top_n_efectivo + 2 else len(escenas)
        indices_cuerpo = list(range(ini_cuerpo, fin_cuerpo))
        if len(indices_cuerpo) < top_n_efectivo:
            indices_cuerpo = list(range(len(escenas)))

        # Reasignación ordenada para preservar cuenta regresiva estricta (#N -> ... -> #1)
        paso = len(indices_cuerpo) / float(top_n_efectivo)
        inicio_por_puesto.clear()
        for i, r in enumerate(puestos_esperados):
            idx_elegido = indices_cuerpo[min(len(indices_cuerpo) - 1, int(round(i * paso)))]
            # Evitar colisión si dos caen en el mismo índice
            while idx_elegido in inicio_por_puesto.values() and idx_elegido + 1 < len(escenas):
                idx_elegido += 1
            inicio_por_puesto[r] = idx_elegido

    # Paso 4: Normalizar campos en las escenas de inicio de cada puesto y limpiar duplicados
    idx_a_puesto_inicio = {idx: r for r, idx in inicio_por_puesto.items()}
    puesto_actual: Optional[int] = None
    for idx, esc in enumerate(escenas):
        if idx in idx_a_puesto_inicio:
            r = idx_a_puesto_inicio[idx]
            puesto_actual = r
            esc.puesto = r
            fuente_titulo = esc.puesto_titulo or esc.texto_pantalla or esc.capitulo or esc.voz
            titulo_limpio = _limpiar_titulo_puesto(fuente_titulo, r)
            esc.puesto_titulo = titulo_limpio
            esc.texto_pantalla = f"#{r}: {titulo_limpio}"
            if esc.sfx == "ninguno":
                esc.sfx = "whoosh"
        else:
            if esc.acto == "cta":
                puesto_actual = None
            esc.puesto = puesto_actual
            esc.puesto_titulo = None
            # Si una escena secundaria repetía un cartel #N, lo vaciamos para no duplicar la tarjeta del puesto
            if esc.texto_pantalla and re.search(r"(?:#|top\s*#?|puesto\s*#?)\s*\d+", esc.texto_pantalla, re.IGNORECASE):
                esc.texto_pantalla = ""

    return guion_obj


def _cliente() -> genai.Client:
    if not config.GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en .env")
    return genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options=types.HttpOptions(client_args={"verify": False}),
    )


# ------------------------------------------------------------------ paso A
PROMPT_INVESTIGACION = """Eres guionista y creador de contenido de YouTube especializado en rankings y TOPS DINÁMICOS
(estilo 'Los casos más impresionantes...', 'Top tecnologías que cambiarán el mundo', etc.), en español latino neutro.

TEMA: {tema}

1. Investiga y selecciona un TOP {top_n} riguroso, fascinante y de alto impacto sobre este tema.
2. Organiza los puestos en cuenta regresiva desde el puesto #{top_n} hasta el número 1 indiscutible (#1): {lista_puestos}.
3. Escribe un BORRADOR NARRATIVO de aproximadamente {palabras} palabras con esta estructura:
   - Gancho inicial breve: Plantea el misterio o la pregunta central del ranking.
   - Puestos {lista_puestos}: Cada puesto debe explicar claramente de qué se trata, por qué merece su posición y un dato sorprendente.
   - Conclusión / Pregunta al espectador para generar comentarios.
   - Frases ágiles, sin relleno, vocabulario directo y entretenido.
"""


def investigar(tema: str, minutos: float) -> tuple[str, list[dict]]:
    palabras = int(round(minutos * config.PALABRAS_POR_MIN))
    top_n = extraer_top_n(tema, minutos)
    lista_puestos = _formatear_lista_puestos(top_n)
    prompt = PROMPT_INVESTIGACION.format(tema=tema, palabras=palabras, top_n=top_n, lista_puestos=lista_puestos)
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
PROMPT_ESTRUCTURA = """Convierte la investigación en un GUION DE MONTAJE para un video formato TOP / RANKING (TOP {top_n}).

REGLAS ESTRICTAS DE FORMATO TOP Y DURACIÓN:
- Presupuesto estricto de locución: el video dura {minutos} minuto(s), lo que equivale a **{palabras} palabras en total** (rango permitido: entre {palabras_min} y {palabras_max} palabras sumando el campo "voz" de TODAS las escenas, calculado a {ppm} palabras/minuto considerando las pausas de puntuación).
- Genera aproximadamente {n_escenas} escenas en total. Cada escena dura entre 5 y 8 segundos: el campo "voz" debe tener ENTRE 12 y {max_pal} palabras. ¡NO excedas las {palabras_max} palabras totales!
- El ranking tiene exactamente {top_n} puestos en cuenta regresiva ({lista_puestos}).
- Tarjetas TOP #N obligatorias:
  * En la PRIMERA escena de cada puesto ({lista_puestos}), asigna:
    - `puesto`: el número entero del puesto (ej. {top_n}, ..., 1).
    - `puesto_titulo`: título corto en MAYÚSCULAS de 2 a 5 palabras sin el número (ej. "EL INCIDENTE DEL PASO DYATLOV").
    - `texto_pantalla`: el cartel con formato exacto `"#N: TITULO DEL PUESTO"` en mayúsculas (ej. `"#{top_n}: EL INCIDENTE DYATLOV"`).
  * En las demás escenas de continuación de ese mismo puesto, pon `puesto` con el número del puesto actual, `puesto_titulo` en null y `texto_pantalla` en blanco (`""`).
  * En la escena de gancho inicial o conclusión/CTA, pon `puesto` en null y `puesto_titulo` en null.
- NO agregues subtítulos de la narración en "texto_pantalla". Solo el cartel de inicio de cada puesto.
- Pose del Host (campo `pose`, sugerida por escena según la emoción y el mood):
  * Poses disponibles: `'explicando'` (manos abiertas conversando), `'pensativo'` (mano en la barbilla reflexionando), `'sorprendido'` (impacto/asombro), `'esceptico'` (brazos cruzados analítico), `'duda'` (encogiendo hombros ante una incógnita), `'senalando'` (apuntando al dato o puesto), `'aprobando'` (pulgares arriba, solo cierres positivos), `'dinero'` (billetes en mano).
  * Cuando se introduce un nuevo puesto (#N): `'senalando'` o `'sorprendido'`.
  * En misterios sin resolver, paradojas o preguntas abiertas: `'duda'`, `'pensativo'` o `'esceptico'`.
  * En explicaciones o contexto documental: `'explicando'`.
  * PROHIBICIÓN ESTRICTA: JAMÁS elijas `'dinero'` ni `'aprobando'` en videos o escenas de misterio, terror, crimen o tensión. `'dinero'` SOLO puede usarse si la escena habla explícitamente de finanzas, fortunas o negocios.
- host_visible: true al anunciar cada puesto (#X) y en la conclusión; pon host_visible = false cuando se deba ver el clip a pantalla completa.
- broll_query_en y broll_queries_en:
  * Genera en `broll_queries_en` ENTRE 2 y 3 consultas en inglés (3-5 palabras cada una) pensadas para bancos de video (Pexels/Pixabay) y archivo (YouTube).
  * La primera consulta debe describir el objeto/lugar literal de la escena (ej. "dark elevator interior closing", "ancient leather manuscript candle").
  * La segunda y tercera consulta deben ser planos alternativos concretos y visuales del mismo concepto (ej. "security camera hallway night", "old library dusty books").
  * Pon en `broll_query_en` la misma primera consulta principal.
- broll_mood_keywords: lista de 2 a 4 adjetivos visuales en inglés acordes al tono de la escena (ej. ["dark", "cinematic", "night", "eerie"] para misterio/tensión).
- broll_avoid_keywords: lista de 3 a 6 palabras en inglés que PROHÍBES en los resultados porque arruinan la escena o son falsos amigos (ej. si hablas de un elevador pon ["escalator", "mall", "shopping"]; si hablas de un manuscrito antiguo pon ["beach", "sunny", "vacation", "tablet", "happy"]).
- sfx: pon 'whoosh' o 'transicion' al entrar a un nuevo puesto (#X); pon 'ninguno' en el resto.

MATERIAL:
{material}
"""


def estructurar(material: str, minutos: float, tema: str = "") -> Guion:
    palabras = int(round(minutos * config.PALABRAS_POR_MIN))
    palabras_min = int(round(minutos * 135))
    palabras_max = int(round(minutos * 150))
    top_n = extraer_top_n(tema, minutos)
    lista_puestos = _formatear_lista_puestos(top_n)
    # ~16 palabras por escena (~6.7s por escena incluyendo micropausas), garantizando al menos top_n + 2 escenas
    n_escenas = max(top_n + 2, round(palabras / 16.0))
    prompt = PROMPT_ESTRUCTURA.format(
        minutos=minutos,
        palabras=palabras,
        palabras_min=palabras_min,
        palabras_max=palabras_max,
        ppm=config.PALABRAS_POR_MIN,
        n_escenas=n_escenas,
        max_pal=config.MAX_PALABRAS_ESCENA,
        top_n=top_n,
        lista_puestos=lista_puestos,
        material=material,
    )
    prompt += (
        f"\n\nATENCIÓN OBLIGATORIA DE DURACIÓN Y TOP {top_n}: El video completo debe durar {minutos} min ({int(minutos * 60)} s) "
        f"e incluir TODOS los puestos en cuenta regresiva ({lista_puestos}) con su tarjeta `texto_pantalla` (\"#N: TITULO\") "
        f"al inicio de cada puesto. Ajusta la cantidad de escenas (~{n_escenas} escenas) y la longitud de cada locución para que la SUMA TOTAL "
        f"de palabras de todas las escenas quede estrictamente entre {palabras_min} y {palabras_max} palabras (objetivo: {palabras})."
    )
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
                guion_obj = resp.parsed if resp.parsed is not None else Guion.model_validate_json(resp.text)
                for esc in guion_obj.escenas:
                    if not esc.broll_queries_en and esc.broll_query_en:
                        esc.broll_queries_en = [esc.broll_query_en]
                    elif esc.broll_queries_en and not esc.broll_query_en:
                        esc.broll_query_en = esc.broll_queries_en[0]
                    esc.pose = normalizar_pose(esc.pose, mood=esc.music_mood, tema=tema, texto_voz=esc.voz)  # type: ignore[assignment]
                asegurar_tarjetas_top(guion_obj, top_n=top_n)
                return guion_obj
            except Exception as e:
                print(f"⚠️ Reintento {intento+1}/3 con modelo {mod} tras aviso: {e}")
                time.sleep(3)

    raise RuntimeError("No se pudo estructurar el guion tras múltiples intentos.")


# ------------------------------------------------------------------ salida
def _contar_palabras_habladas(texto: str) -> int:
    limpio = re.sub(r"<[^>]+>", " ", texto or "")
    return len([w for w in limpio.split() if w.strip()])


def _montaje_txt(p: Proyecto, g: Guion) -> str:
    t = 0.0
    lineas = [
        f"PROYECTO: {p.tema}",
        f"FORMATO: {g.formato} ({'Documental TV' if g.formato == '16:9' else 'Reel Vertical'})",
        f"TÍTULO DE TRABAJO: {g.titulo_trabajo}",
        f"MOOD GENERAL: {g.mood_original} ({g.mood}) | TOP N: {g.top_n or '-'}",
        "-" * 80,
    ]
    for e in g.escenas:
        n_pal = max(1, _contar_palabras_habladas(e.voz))
        dur = min(n_pal / config.PALABRAS_POR_SEG, config.MAX_SEG_ESCENA)
        ini, fin = t, t + dur
        t = fin
        if e.capitulo:
            lineas.append(f"\n=== CAPÍTULO: {e.capitulo} ===")
        short = f"  [SHORT {e.short_id}]" if e.short_id else ""
        queries_str = " | ".join(e.broll_queries_en) if e.broll_queries_en else e.broll_query_en
        mood_kw = ", ".join(e.broll_mood_keywords) if e.broll_mood_keywords else "-"
        avoid_kw = ", ".join(e.broll_avoid_keywords) if e.broll_avoid_keywords else "-"
        lineas += [
            f"\n{int(ini//60)}:{int(ini%60):02d} - {int(fin//60)}:{int(fin%60):02d} | Escena {e.id} ({e.acto}){short}",
            f"  -> VOICEOFF: \"{e.voz}\"",
            f"  -> VISUAL: " + (f"Host '{e.pose}' a la {e.host_lado}" if e.host_visible else "B-roll a pantalla completa")
            + (f" | TEXTO: {e.texto_pantalla}" if e.texto_pantalla else ""),
            f"  -> B-ROLL: {e.broll_descripcion}  (búsquedas: {queries_str})",
            f"  -> MOOD TAGS: [{mood_kw}] | EVITAR: [{avoid_kw}]",
            f"  -> SFX: {e.sfx} | MÚSICA: {e.music_mood}",
        ]
    lineas.append(f"\nDURACIÓN ESTIMADA: {int(t//60)}:{int(t%60):02d}")
    return "\n".join(lineas)


def validar(g: Guion, minutos: Optional[float] = None) -> list[str]:
    avisos = []
    total_palabras = 0
    for e in g.escenas:
        n = _contar_palabras_habladas(e.voz)
        total_palabras += n
        if n > config.MAX_PALABRAS_ESCENA:
            avisos.append(f"Escena {e.id}: {n} palabras (máx recomendado {config.MAX_PALABRAS_ESCENA}).")
    if minutos is not None and minutos > 0:
        min_pal = int(round(minutos * 135))
        max_pal = int(round(minutos * 150))
        est_s = total_palabras / config.PALABRAS_POR_SEG
        print(
            f"📏 Guion validado: {len(g.escenas)} escenas | {total_palabras} palabras totales "
            f"(objetivo para {minutos:.2f} min: {min_pal}-{max_pal} pal, est. ~{int(est_s//60)}m {int(est_s%60):02d}s)"
        )
        if total_palabras < min_pal or total_palabras > max_pal:
            avisos.append(
                f"Conteo total de palabras ({total_palabras}) fuera del rango ideal ({min_pal}-{max_pal}) "
                f"para {minutos:.2f} min (~{int(est_s)}s estimados)."
            )
    return avisos


def validar_json_externo(
    ruta_json: Path,
    formato_esperado: Optional[str] = None,
) -> tuple[Optional[Guion], list[str], list[str]]:
    """Valida un archivo JSON de guion externo devolviendo (guion_obj, errores_por_campo, avisos)."""
    errores: list[str] = []
    avisos: list[str] = []

    if not ruta_json.exists() or not ruta_json.is_file():
        return None, [f"archivo: No existe el archivo '{ruta_json}'."], []

    try:
        texto_raw = ruta_json.read_text(encoding="utf-8")
    except Exception as e:
        return None, [f"archivo: No se pudo leer en UTF-8 ({e})."], []

    try:
        datos = json.loads(texto_raw)
    except json.JSONDecodeError as e:
        return None, [f"json (línea {e.lineno}, col {e.colno}): Sintaxis JSON inválida ({e.msg})."], []

    if not isinstance(datos, dict):
        return None, ["raiz: El JSON debe ser un objeto (diccionario) en su nivel raíz."], []

    # Validaciones explícitas de campos raíz
    titulo_raw = str(datos.get("titulo_trabajo") or datos.get("titulo") or "").strip()
    if not titulo_raw:
        errores.append("titulo: El campo 'titulo' (o 'titulo_trabajo') es obligatorio y no puede estar vacío.")

    formato_raw = str(datos.get("formato") or formato_esperado or "16:9").strip()
    if formato_raw not in ("16:9", "9:16"):
        errores.append(f"formato: Valor '{formato_raw}' inválido. Debe ser '16:9' o '9:16'.")
    elif formato_esperado and datos.get("formato") and formato_raw != formato_esperado:
        avisos.append(f"formato: El JSON declara '{formato_raw}' pero se invocó en pipeline '{formato_esperado}'.")

    mood_raiz_raw = str(datos.get("mood") or "misterio").strip().lower()
    if mood_raiz_raw not in _MAPA_MOOD_CANONICO:
        errores.append(
            f"mood: Valor '{mood_raiz_raw}' inválido. Permitidos: misterio, tension, terror, crimen, epica, curiosidad, calma."
        )

    escenas_raw = datos.get("escenas")
    if not isinstance(escenas_raw, list) or len(escenas_raw) == 0:
        errores.append("escenas: Debe ser una lista no vacía de escenas.")
    else:
        for idx, esc in enumerate(escenas_raw):
            pref = f"escenas[{idx}]"
            if not isinstance(esc, dict):
                errores.append(f"{pref}: Cada escena debe ser un objeto JSON.")
                continue
            voz_val = str(
                esc.get("voz") or esc.get("narracion") or esc.get("texto_narracion") or esc.get("texto") or ""
            ).strip()
            if not voz_val:
                errores.append(f"{pref}.voz: El texto de narración ('voz' / 'narracion') es obligatorio y no puede estar vacío.")

            queries_val = esc.get("broll_queries_en")
            query_single = str(esc.get("broll_query_en") or "").strip()
            if isinstance(queries_val, list):
                limpias = [str(q).strip() for q in queries_val if str(q).strip()]
                if not limpias and not query_single:
                    errores.append(f"{pref}.broll_queries_en: Debe contener al menos 1 consulta de búsqueda en inglés.")
            elif queries_val is not None:
                errores.append(f"{pref}.broll_queries_en: Debe ser una lista de strings en inglés (ej. ['dark hallway night', 'old archive footage']).")
            elif not query_single:
                errores.append(f"{pref}.broll_queries_en: Falta 'broll_queries_en' (lista de 2-3 consultas en inglés).")

            pose_raw = str(esc.get("pose") or esc.get("pose_host") or "explicando").strip().lower()
            pose_sin_tilde = pose_raw.translate(str.maketrans("áéíóú", "aeiou"))
            if pose_sin_tilde == "señalando":
                pose_sin_tilde = "senalando"
            pose_resuelta = config.POSE_ALIASES.get(pose_sin_tilde, pose_sin_tilde)
            if pose_resuelta not in config.POSES:
                errores.append(
                    f"{pref}.pose: Pose '{pose_raw}' desconocida. Poses válidas: {', '.join(config.POSES)}."
                )
            else:
                mood_esc_raw = str(esc.get("music_mood") or esc.get("musica") or mood_raiz_raw).strip().lower()
                if pose_resuelta == "dinero" and (
                    es_mood_oscuro_sin_dinero(mood=mood_raiz_raw, tema=titulo_raw, texto_voz=voz_val)
                    or es_mood_oscuro_sin_dinero(mood=mood_esc_raw, tema=titulo_raw, texto_voz=voz_val)
                ):
                    errores.append(
                        f"{pref}.pose: La pose 'dinero' no se acepta en guiones con mood '{mood_raiz_raw}' / '{mood_esc_raw}' "
                        f"(prohibida en misterio, terror, crimen y tensión). Usa: sorprendido, pensativo, duda, esceptico, senalando o explicando."
                    )

            mus_raw = str(esc.get("music_mood") or esc.get("musica") or mood_raiz_raw).strip().lower()
            if mus_raw not in _MAPA_MOOD_CANONICO:
                errores.append(
                    f"{pref}.music_mood: Mood musical '{mus_raw}' inválido. Permitidos: {', '.join(config.MUSIC_MOODS)}."
                )

            sfx_raw = str(esc.get("sfx") or "ninguno").strip().lower()
            if sfx_raw not in _MAPA_SFX_CANONICO:
                errores.append(
                    f"{pref}.sfx: Efecto '{sfx_raw}' inválido. Permitidos: ninguno, whoosh, impacto, riser, tension, revelacion, glitch, ambiente, digital, click, transicion."
                )

            cf_raw = esc.get("clips_fuente")
            if cf_raw is not None:
                if not isinstance(cf_raw, list):
                    errores.append(f"{pref}.clips_fuente: Debe ser una lista de objetos {{url, inicio, duracion, credito}}.")
                else:
                    for j, cf in enumerate(cf_raw):
                        pcf = f"{pref}.clips_fuente[{j}]"
                        if not isinstance(cf, dict) or not str(cf.get("url") or "").strip().lower().startswith(("http://", "https://")):
                            errores.append(f"{pcf}.url: Se requiere una URL http(s) válida.")
                            continue
                        try:
                            d_cf = float(cf.get("duracion", 4.0))
                            float(cf.get("inicio", 0.0))
                        except (TypeError, ValueError):
                            errores.append(f"{pcf}: 'inicio' y 'duracion' deben ser números (segundos).")
                            continue
                        if not 3.0 <= d_cf <= 6.0:
                            avisos.append(f"{pcf}.duracion: {d_cf}s fuera de 3-6 s; se recortará al rango permitido.")
                        if str(cf.get("estilo") or "evidencia").strip().lower() not in ("evidencia", "completo", "dividido", "congelado"):
                            errores.append(f"{pcf}.estilo: Use evidencia, completo, dividido o congelado.")
                        if not str(cf.get("credito") or "").strip():
                            avisos.append(f"{pcf}.credito: Sin crédito; se mostrará 'Fuente: redes sociales'.")

    fv_raw = datos.get("fuentes_video")
    if fv_raw is not None and not isinstance(fv_raw, list):
        errores.append("fuentes_video: Debe ser una lista de objetos {url, credito, descripcion}.")

    if errores:
        return None, errores, avisos

    try:
        guion_obj = Guion.model_validate(datos)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", ()))
            errores.append(f"{loc}: {err.get('msg')}")
        return None, errores, avisos

    # Normalizar poses y tarjetas TOP #N en 16:9
    for esc in guion_obj.escenas:
        esc.pose = normalizar_pose(
            esc.pose,
            mood=guion_obj.mood_original or esc.music_mood,
            tema=guion_obj.titulo_trabajo,
            texto_voz=esc.voz,
        )  # type: ignore[assignment]

    if (formato_esperado or guion_obj.formato) == "16:9":
        top_n_detectado = guion_obj.top_n
        if not top_n_detectado:
            puestos_en_escenas = [e.puesto for e in guion_obj.escenas if e.puesto and e.puesto > 0]
            if puestos_en_escenas:
                top_n_detectado = max(puestos_en_escenas)
            else:
                pal_tot = sum(_contar_palabras_habladas(e.voz) for e in guion_obj.escenas)
                min_est = guion_obj.minutos or round(max(0.5, pal_tot / float(config.PALABRAS_POR_MIN)), 2)
                top_n_detectado = extraer_top_n(guion_obj.titulo_trabajo, min_est)
        guion_obj.top_n = top_n_detectado
        asegurar_tarjetas_top(guion_obj, top_n=top_n_detectado)

    return guion_obj, [], avisos


def importar_guion_archivo(
    ruta_json: Path,
    formato_forzado: Optional[str] = None,
    sin_host: bool = False,
    reusar: bool = False,
) -> tuple[Proyecto, Guion, list[str]]:
    """Valida e importa un archivo JSON de guion externo, creando el proyecto y sus guías de montaje y doblaje."""
    guion_obj, errores, avisos = validar_json_externo(ruta_json, formato_esperado=formato_forzado)
    if errores or guion_obj is None:
        detalle = "\n".join(f"  ❌ [{e}]" for e in errores)
        raise ValueError(f"El archivo '{ruta_json}' contiene errores de validación:\n{detalle}")

    palabras_tot = sum(_contar_palabras_habladas(e.voz) for e in guion_obj.escenas)
    minutos_calc = guion_obj.minutos or round(max(0.5, palabras_tot / float(config.PALABRAS_POR_MIN)), 2)
    guion_obj.minutos = minutos_calc

    try:
        p = Proyecto.crear(guion_obj.titulo_trabajo, minutos=minutos_calc, lang="es", reusar=reusar)
    except TypeError:
        p = Proyecto.crear(guion_obj.titulo_trabajo, minutos=minutos_calc, lang="es")
    if sin_host:
        p.datos["sin_host"] = True
        for e in guion_obj.escenas:
            e.host_visible = False

    p.datos["formato"] = formato_forzado or guion_obj.formato
    p.datos["mood"] = guion_obj.mood
    p.datos["mood_original"] = guion_obj.mood_original
    p.datos["top_n"] = guion_obj.top_n
    p.datos["guion_origen"] = str(ruta_json.resolve())

    # Invalidar b_roll/ y renders/ si el número, orden o contenido de escenas cambió (Tarea 2)
    if hasattr(p, "invalidar_cache_si_guion_cambio"):
        p.invalidar_cache_si_guion_cambio(guion_obj.escenas)

    p.ruta("guion", "guion.json").write_text(
        json.dumps(guion_obj.model_dump(), ensure_ascii=False, indent=2), "utf-8"
    )
    p.ruta("guion", "guion_montaje.txt").write_text(_montaje_txt(p, guion_obj), "utf-8")
    p.ruta("guion", "guion_doblaje.md").write_text(_guion_doblaje_md(p, guion_obj), "utf-8")
    if not p.ruta("guion", "fuentes.md").exists():
        p.ruta("guion", "fuentes.md").write_text(
            f"# Fuentes\n\n- Guion importado desde `{ruta_json.name}` (Agente Pluma / externo)\n",
            "utf-8",
        )
    p.marcar("guion", "revisar")
    avisos_val = validar(guion_obj, minutos=minutos_calc)
    return p, guion_obj, avisos + avisos_val


def etapa_guion(p: Proyecto) -> list[str]:
    minutos = float(p.datos.get("minutos", 1.0))
    print(f"🔎 Investigando '{p.tema}' con {config.MODELO_GUION} + Google Search…")
    material, fuentes = investigar(p.tema, minutos)
    p.ruta("guion", "investigacion.md").write_text(material, "utf-8")

    print(f"🧱 Estructurando en escenas con {config.MODELO_ESTRUCTURA}…")
    g = estructurar(material, minutos, tema=p.tema)

    if p.datos.get("sin_host", False):
        for e in g.escenas:
            e.host_visible = False

    if hasattr(p, "invalidar_cache_si_guion_cambio"):
        p.invalidar_cache_si_guion_cambio(g.escenas)

    p.ruta("guion", "guion.json").write_text(json.dumps(g.model_dump(), ensure_ascii=False, indent=2), "utf-8")
    p.ruta("guion", "guion_montaje.txt").write_text(_montaje_txt(p, g), "utf-8")
    p.ruta("guion", "guion_doblaje.md").write_text(_guion_doblaje_md(p, g), "utf-8")
    p.ruta("guion", "fuentes.md").write_text(
        "# Fuentes\n\n" + "\n".join(f"- [{f['titulo']}]({f['url']})" for f in fuentes) + "\n", "utf-8"
    )
    p.marcar("guion", "revisar")
    return validar(g, minutos=minutos)


def _guion_doblaje_md(p: Proyecto, g: Guion) -> str:
    """Genera guía de locución profesional para doblaje humano / teleprompter."""
    tonos_por_pose = {
        "explicando": "Tono didáctico, narración fluida y aplomada",
        "pensativo": "Tono reflexivo, ritmo pausado, sospecha",
        "sorprendido": "Tono de asombro, tensión y revelación impactante",
        "esceptico": "Tono interrogativo, analítico o de duda razonable",
        "duda": "Tono enigmático, planteando la incógnita al espectador",
        "senalando": "Tono asertivo, dirección clara hacia el dato clave",
        "aprobando": "Tono cercano, conclusión positiva",
        "dinero": "Tono enfático sobre cifras, impacto económico o escala",
    }
    lineas = [
        f"# 🎙️ Guion de Locución y Doblaje Profesional: {p.tema}",
        f"> **Proyecto:** `{p.datos.get('slug')}` | **Formato:** `{g.formato}` | **Duración objetivo:** {p.datos.get('minutos', 1.0)} min",
        "> **Instrucción para el locutor:** Respete los tiempos de entrada y las pausas SSML (`<break time=\"...\"/>`) indicadas para mantener la sincronización con el montaje visual.",
        "\n---\n"
    ]
    t = 0.0
    for e in g.escenas:
        conteo = max(1, _contar_palabras_habladas(e.voz))
        dur_est = min(conteo / config.PALABRAS_POR_SEG, config.MAX_SEG_ESCENA)
        ini_str = f"{int(t//60):02d}:{int(t%60):02d}"
        fin_str = f"{int((t+dur_est)//60):02d}:{int((t+dur_est)%60):02d}"
        tono = tonos_por_pose.get(e.pose, "Tono documental neutro")

        texto_destacado = e.voz
        if e.texto_pantalla and e.texto_pantalla.lower() in e.voz.lower():
            idx = e.voz.lower().find(e.texto_pantalla.lower())
            if idx != -1:
                pal_orig = e.voz[idx:idx+len(e.texto_pantalla)]
                texto_destacado = e.voz[:idx] + f"**{pal_orig}**" + e.voz[idx+len(e.texto_pantalla):]

        lineas.append(f"### Escena {e.id:02d} `[{ini_str} - {fin_str}]` *(~{dur_est:.1f}s | {conteo} palabras)*")
        lineas.append(f"> **Dirección de voz:** [{tono}] (Pose: `{e.pose}`)")
        if e.puesto is not None:
            lineas.append(f"> **Puesto del Ranking:** `#{e.puesto}`" + (f" — `{e.puesto_titulo}`" if e.puesto_titulo else ""))
        if e.texto_pantalla:
            lineas.append(f"> **Tarjeta en pantalla:** `{e.texto_pantalla}`")
        lineas.append(f"\n> **LOCUCIÓN:**\n> \"{texto_destacado}\"\n")
        lineas.append("---\n")
        t += dur_est

    return "\n".join(lineas)


def cargar_guion(p: Proyecto) -> Guion:
    """Lee guion.json (incluye las ediciones manuales del usuario) y asegura poses válidas."""
    g = Guion.model_validate_json(p.ruta("guion", "guion.json").read_text("utf-8"))
    mood_ref = str(p.datos.get("mood_original") or g.mood_original or g.mood or "misterio")
    for esc in g.escenas:
        esc.pose = normalizar_pose(
            esc.pose,
            mood=mood_ref if es_mood_oscuro_sin_dinero(mood=mood_ref) else esc.music_mood,
            tema=p.tema,
            texto_voz=esc.voz,
        )  # type: ignore[assignment]
    return g
