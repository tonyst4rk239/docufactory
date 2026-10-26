"""Generación de paquete de publicación para YouTube (títulos, descripción, capítulos y tags)."""
from __future__ import annotations

import json
from pathlib import Path
from google import genai

from . import config
from .estado import Proyecto
from .guion import cargar_guion


# YouTube rechaza descripciones de más de 5000 caracteres.
LIMITE_DESCRIPCION_YT = 5000
ENCABEZADO_CREDITOS = "🎨 CRÉDITOS VISUALES Y B-ROLL (stock y licencias abiertas):"
_MARCAS_CREDITOS = ("creative commons", "cc by", "créditos", "creditos")


def _ya_trae_creditos(texto: str) -> bool:
    t = (texto or "").lower()
    return any(m in t for m in _MARCAS_CREDITOS)


def armar_descripcion_youtube(
    cuerpo: str,
    capitulos: list[str],
    lineas_creditos: list[str],
    limite: int = LIMITE_DESCRIPCION_YT,
) -> tuple[str, list[str]]:
    """Arma la descripción final sin pasar de `limite` caracteres.

    Si el cuerpo ya trae sus créditos, no se agrega el bloque automático.
    Si el bloque no cabe, se recorta y se deja una nota que remite a la lista
    completa. Devuelve el texto y las líneas de crédito que quedaron fuera.
    """
    cuerpo = (cuerpo or "").strip()
    cabeza = f"{cuerpo}\n\n📌 CAPÍTULOS:\n" + "\n".join(capitulos)
    if "fuentes" not in cuerpo.lower():
        cabeza += "\n\n📚 FUENTES Y RECURSOS:\nVerificadas con el archivo de investigación del proyecto."
    cola = "\n\n---\n#Documental #Misterio #Historia #Investigacion"

    lineas = [] if _ya_trae_creditos(cuerpo) else list(lineas_creditos)
    omitidas: list[str] = []

    def _bloque(ls: list[str], faltan: int) -> str:
        if not ls and not faltan:
            return ""
        nota = [f"…y {faltan} créditos más (lista completa en creditos_completos.txt del paquete)."] if faltan else []
        return f"\n\n{ENCABEZADO_CREDITOS}\n" + "\n".join(ls + nota)

    texto = cabeza + _bloque(lineas, 0) + cola
    while len(texto) > limite and lineas:
        omitidas.insert(0, lineas.pop())
        texto = cabeza + _bloque(lineas, len(omitidas)) + cola
    if len(texto) > limite:
        texto = texto[: limite - 1].rstrip() + "…"
    return texto, omitidas


def etapa_publicacion(p: Proyecto, duraciones: dict[int, float]) -> None:
    guion = cargar_guion(p)
    carpeta = p.ruta("publicacion")
    carpeta.mkdir(parents=True, exist_ok=True)

    # Mapear capítulos por escena desde guion.capitulos si existen
    caps_por_escena: dict[int, str] = {}
    for cap in getattr(guion, "capitulos", []) or []:
        if isinstance(cap, dict):
            eid = cap.get("escena_id")
            tit = cap.get("titulo") or cap.get("nombre")
            if eid is not None and tit:
                caps_por_escena[int(eid)] = str(tit)
        elif hasattr(cap, "escena_id") and getattr(cap, "escena_id", None) is not None:
            caps_por_escena[int(cap.escena_id)] = str(getattr(cap, "titulo", ""))

    # Calcular marcas de tiempo de capítulos reales según duraciones TTS
    capitulos = ["00:00 - Introducción / Gancho"]
    t = 0.0
    puestos_cap_vistos: set[int] = set()
    for esc in guion.escenas:
        dur = duraciones.get(esc.id, 5.0)
        nombre_cap = esc.capitulo or caps_por_escena.get(esc.id)
        if not nombre_cap and esc.puesto and esc.puesto not in puestos_cap_vistos and esc.puesto_titulo:
            nombre_cap = f"Puesto #{esc.puesto}: {esc.puesto_titulo}"
            puestos_cap_vistos.add(esc.puesto)
        if nombre_cap and t > 0:
            m = int(t // 60)
            s = int(t % 60)
            linea_cap = f"{m:02d}:{s:02d} - {nombre_cap}"
            if linea_cap not in capitulos:
                capitulos.append(linea_cap)
        t += dur

    # Leer créditos de B-Roll
    ruta_creditos = p.ruta("b_roll", "creditos.json")
    lineas_creditos: list[str] = []
    if ruta_creditos.exists():
        datos_cred = json.loads(ruta_creditos.read_text("utf-8"))
        lineas_c = [f"- {c.get('credito', c.get('fuente', 'Clip de Archivo'))} (Escena {c.get('escena')})" for c in datos_cred]
        lineas_creditos = sorted(set(lineas_c))

    yt_meta = getattr(guion, "youtube_metadata", None)
    texto_gen = ""
    cuerpo_desc = ""
    if yt_meta and (yt_meta.titulos or yt_meta.descripcion or yt_meta.tags):
        partes_yt = []
        if yt_meta.titulos:
            partes_yt.append("🎯 TÍTULOS SUGERIDOS (GUIÓN IMPORTADO):\n" + "\n".join(f"- {t_it}" for t_it in yt_meta.titulos))
        if yt_meta.tags:
            partes_yt.append("🏷️ TAGS:\n" + ", ".join(yt_meta.tags))
        texto_gen = "\n\n".join(partes_yt)
        cuerpo_desc = (yt_meta.descripcion or guion.resumen or f"Documental sobre {p.tema}.").strip()
    elif config.GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            prompt = f"""Para un documental de YouTube sobre '{p.tema}':
1. Genera 3 TÍTULOS de alto impacto (máximo 60 caracteres cada uno, optimizados para CTR).
2. Genera una DESCRIPCIÓN persuasiva de 2 párrafos.
3. Lista 15 TAGS separados por coma.
"""
            resp = client.models.generate_content(model=config.MODELO_ESTRUCTURA, contents=prompt)
            texto_gen = resp.text or ""
        except Exception:
            texto_gen = ""

    if not texto_gen:
        resumen_txt = (guion.resumen or f"Documental sobre {p.tema}.").strip()
        texto_gen = (
            f"🎯 TÍTULOS SUGERIDOS:\n"
            f"- {guion.titulo_trabajo}\n"
            f"- Lo que nadie te contó sobre {p.tema}\n"
            f"- El misterio detrás de {p.tema}\n\n"
            f"📝 DESCRIPCIÓN:\n{resumen_txt}\n\n"
            f"🏷️ TAGS:\ndocumental, misterio, historia, investigacion, top"
        )

    descripcion_yt, omitidas = armar_descripcion_youtube(cuerpo_desc or texto_gen, capitulos, lineas_creditos)
    if omitidas:
        (carpeta / "creditos_completos.txt").write_text("\n".join(lineas_creditos) + "\n", "utf-8")
        print(f"⚠️ {len(omitidas)} créditos no cupieron en la descripción; lista completa en creditos_completos.txt")
    (carpeta / "descripcion_youtube.txt").write_text(descripcion_yt, "utf-8")
    print(f"📝 Descripción de YouTube: {len(descripcion_yt)}/{LIMITE_DESCRIPCION_YT} caracteres")

    if cuerpo_desc:
        descripcion_final = f"{texto_gen}\n\n📝 DESCRIPCIÓN (lista para YouTube):\n{descripcion_yt}\n"
    else:
        descripcion_final = f"{descripcion_yt}\n"
    (carpeta / "paquete_youtube.txt").write_text(descripcion_final, "utf-8")
    
    # Auto-generar miniaturas oficiales 1080p y 720p en carpeta publicacion/
    try:
        from .miniatura import generar_miniatura_proyecto
        res_mini = generar_miniatura_proyecto(p)
        print(f"🖼️  Miniaturas de alto CTR generadas: {res_mini['1080p'].name} y {res_mini['720p'].name}")
    except Exception as e:
        print(f"⚠️ Aviso: No se pudo auto-generar miniatura: {e}")

    p.marcar("publicacion", "ok")
    print(f"📄 Paquete de publicación guardado en {carpeta / 'paquete_youtube.txt'}")
