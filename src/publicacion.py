"""Generación de paquete de publicación para YouTube (títulos, descripción, capítulos y tags)."""
from __future__ import annotations

import json
from pathlib import Path
from google import genai

from . import config
from .estado import Proyecto
from .guion import cargar_guion


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
    creditos_txt = ""
    if ruta_creditos.exists():
        datos_cred = json.loads(ruta_creditos.read_text("utf-8"))
        lineas_c = [f"- {c.get('credito', c.get('fuente', 'Clip de Archivo'))} (Escena {c.get('escena')})" for c in datos_cred]
        creditos_txt = "\n".join(sorted(set(lineas_c)))

    yt_meta = getattr(guion, "youtube_metadata", None)
    texto_gen = ""
    if yt_meta and (yt_meta.titulos or yt_meta.descripcion or yt_meta.tags):
        partes_yt = []
        if yt_meta.titulos:
            partes_yt.append("🎯 TÍTULOS SUGERIDOS (GUIÓN IMPORTADO):\n" + "\n".join(f"- {t_it}" for t_it in yt_meta.titulos))
        if yt_meta.descripcion:
            partes_yt.append(f"📝 DESCRIPCIÓN:\n{yt_meta.descripcion.strip()}")
        if yt_meta.tags:
            partes_yt.append("🏷️ TAGS:\n" + ", ".join(yt_meta.tags))
        texto_gen = "\n\n".join(partes_yt)
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

    descripcion_final = f"""{texto_gen}

📌 CAPÍTULOS:
{chr(10).join(capitulos)}

📚 FUENTES Y RECURSOS:
Verificadas con el archivo de investigación del proyecto.

🎨 CRÉDITOS VISUALES Y B-ROLL (Uso Justo / Licencias Abiertas):
{creditos_txt}

---
#Documental #Misterio #Historia #Investigacion
"""
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
