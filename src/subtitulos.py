"""Generador de pistas de subtítulos (.srt) a partir del guion y duraciones de voz."""
from __future__ import annotations

from pathlib import Path
from .estado import Proyecto
from .guion import cargar_guion


def _formatear_tiempo_srt(segundos: float) -> str:
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    ms = int((segundos - int(segundos)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


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
