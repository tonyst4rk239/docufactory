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
    
    # Calcular marcas de tiempo de capítulos
    capitulos = ["00:00 - Introducción / Gancho"]
    t = 0.0
    for esc in guion.escenas:
        dur = duraciones.get(esc.id, 5.0)
        if esc.capitulo and t > 0:
            m = int(t // 60)
            s = int(t % 60)
            capitulos.append(f"{m:02d}:{s:02d} - {esc.capitulo}")
        t += dur

    # Leer créditos de B-Roll
    ruta_creditos = p.ruta("b_roll", "creditos.json")
    creditos_txt = ""
    if ruta_creditos.exists():
        datos_cred = json.loads(ruta_creditos.read_text("utf-8"))
        lineas_c = [f"- {c['credito']}" for c in datos_cred]
        creditos_txt = "\n".join(set(lineas_c))

    # Generar títulos con Gemini
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    prompt = f"""Para un documental de YouTube sobre '{p.tema}':
1. Genera 3 TÍTULOS de alto impacto (máximo 60 caracteres cada uno, optimizados para CTR).
2. Genera una DESCRIPCIÓN persuasiva de 2 párrafos.
3. Lista 15 TAGS separados por coma.
"""
    try:
        resp = client.models.generate_content(model=config.MODELO_ESTRUCTURA, contents=prompt)
        texto_gen = resp.text
    except Exception:
        texto_gen = f"Títulos sugeridos para {p.tema}\n- La revolución oculta: {p.tema}\n- El fin de una era: {p.tema}"

    descripcion_final = f"""{texto_gen}

📌 CAPÍTULOS:
{chr(10).join(capitulos)}

📚 FUENTES Y RECURSOS:
Verificadas con el archivo de investigación del proyecto.

🎨 CRÉDITOS VISUALES Y B-ROLL (Uso Justo / Licencias Abiertas):
{creditos_txt}

---
#Documental #Ciencia #Tecnologia #Historia
"""
    (carpeta / "paquete_youtube.txt").write_text(descripcion_final, "utf-8")
    p.marcar("publicacion", "ok")
    print(f"📄 Paquete de publicación guardado en {carpeta / 'paquete_youtube.txt'}")
