"""Generador de pistas de subtítulos (.srt) y tarjetas de puesto estilizadas (.ass)."""
from __future__ import annotations

import re
from pathlib import Path
from . import config
from .estado import Proyecto
from .guion import cargar_guion, extraer_top_n, asegurar_tarjetas_top


def _formatear_tiempo_srt(segundos: float) -> str:
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    ms = int((segundos - int(segundos)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _formatear_tiempo_ass(segundos: float) -> str:
    """Formatea segundos en formato H:MM:SS.cs para subtítulos ASS."""
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    cs = int(round((segundos - int(segundos)) * 100))
    if cs >= 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generar_srt(p: Proyecto, duraciones: dict[int, float]) -> Path:
    """Genera archivo de subtítulos .srt en la carpeta de render."""
    guion = cargar_guion(p)
    carpeta_render = p.ruta("render")
    carpeta_render.mkdir(parents=True, exist_ok=True)
    ruta_srt = carpeta_render / "subtitulos.srt"
    
    lineas = []
    tiempo_actual = 0.0
    
    for i, esc in enumerate(guion.escenas, 1):
        dur = duraciones.get(esc.id, 5.0)
        t_inicio = tiempo_actual
        t_fin = tiempo_actual + dur
        tiempo_actual = t_fin
        
        lineas.append(str(i))
        lineas.append(f"{_formatear_tiempo_srt(t_inicio)} --> {_formatear_tiempo_srt(t_fin)}")
        lineas.append(esc.voz)
        lineas.append("")
        
    ruta_srt.write_text("\n".join(lineas), "utf-8")
    return ruta_srt


def generar_tarjetas_ass(p: Proyecto, duraciones: dict[int, float]) -> Path:
    """Genera archivo de subtítulos estilizados .ass garantizando una tarjeta TOP #N al inicio de cada puesto."""
    guion = cargar_guion(p)
    minutos = float(p.datos.get("minutos", 1.0))
    top_n = extraer_top_n(p.tema, minutos)
    asegurar_tarjetas_top(guion, top_n=top_n)

    carpeta_renders = p.carpeta / "renders"
    carpeta_renders.mkdir(parents=True, exist_ok=True)
    ruta_ass = carpeta_renders / "tarjetas_puestos.ass"

    # Estilo ASS: Tamaño grande 92pt, Centrado al centro de la pantalla (Alignment=5), con fondo oscuro opaco y borde cian/amarillo
    contenido_base = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TopCentered,Arial Black,92,&H00FFFFFF,&H00000000,&H00000000,&HD0000000,1,0,0,0,100,100,2.5,0,3,18,12,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    eventos = []
    tiempo_actual = 0.0
    primer_top_visto = False
    puestos_emitidos: set[int] = set()

    for esc in guion.escenas:
        dur = duraciones.get(esc.id, 5.0)
        t_inicio = tiempo_actual
        t_fin = tiempo_actual + dur
        tiempo_actual = t_fin

        txt = (esc.texto_pantalla or "").strip()
        numero: int | None = None
        titulo: str = ""

        if esc.puesto and esc.puesto not in puestos_emitidos and esc.puesto_titulo:
            numero = esc.puesto
            titulo = esc.puesto_titulo.strip()
        elif txt:
            m = re.search(r"(?:TOP\s*)?(?:PUESTO\s*)?#?\s*(\d{1,2})\s*[:\-\.\–—]*\s*(.*)", txt, re.IGNORECASE)
            if m and (txt.startswith("#") or "top" in txt.lower() or "puesto" in txt.lower() or esc.puesto):
                cand_num = int(m.group(1))
                if cand_num not in puestos_emitidos:
                    numero = cand_num
                    titulo = m.group(2).strip()

        if numero is None and not txt:
            continue

        # Duración de la tarjeta: hasta 3.5 segundos (o la duración de la escena si es menor)
        t_evento_fin = min(t_fin, t_inicio + 3.5)
        ini_str = _formatear_tiempo_ass(t_inicio)
        fin_str = _formatear_tiempo_ass(t_evento_fin)

        if numero is not None:
            puestos_emitidos.add(numero)
            # Escapar caracteres especiales ASS en el título
            titulo_ass = titulo.replace("{", "(").replace("}", ")")
            if not primer_top_visto:
                primer_top_visto = True
                if titulo_ass:
                    texto_formateado = f"{{\\fs115}}{{\\c&H0000E6FF&}}TOP #{numero}\\N{{\\c&H00FFFFFF&}}{{\\fs76}}{titulo_ass}"
                else:
                    texto_formateado = f"{{\\fs120}}{{\\c&H0000E6FF&}}TOP #{numero}"
            else:
                if titulo_ass:
                    texto_formateado = f"{{\\fs90}}{{\\c&H0000E6FF&}}TOP #{numero}\\N{{\\c&H00FFFFFF&}}{{\\fs62}}{titulo_ass}"
                else:
                    texto_formateado = f"{{\\fs95}}{{\\c&H0000E6FF&}}TOP #{numero}"
        else:
            txt_ass = txt.replace("{", "(").replace("}", ")")
            if not primer_top_visto:
                texto_formateado = f"{{\\fs105}}{{\\c&H0000E6FF&}}{txt_ass}"
            else:
                texto_formateado = f"{{\\fs90}}{{\\c&H0000E6FF&}}{txt_ass}"

        eventos.append(
            f"Dialogue: 1,{ini_str},{fin_str},TopCentered,,0,0,0,,{{\\fad(250,250)}}{texto_formateado}"
        )

    contenido_final = contenido_base + "\n" + "\n".join(eventos) + "\n"
    ruta_ass.write_text(contenido_final, encoding="utf-8")
    return ruta_ass
