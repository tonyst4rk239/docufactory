"""Generador de pistas de subtítulos (.srt) y tarjetas de puesto estilizadas (.ass)."""
from __future__ import annotations

import re
from pathlib import Path
from . import config
from .estado import Proyecto
from .guion import cargar_guion, asegurar_tarjetas_top, top_n_explicito
from .voz import limpiar_tags_ssml


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
        lineas.append(limpiar_tags_ssml(esc.voz))
        lineas.append("")
        
    ruta_srt.write_text("\n".join(lineas), "utf-8")
    return ruta_srt


from .layout import ajustar_fuente, caja_host, partir_en_lineas, zona_texto


def generar_tarjetas_ass(p: Proyecto, duraciones: dict[int, float]) -> Path:
    """Genera archivo de subtítulos estilizados .ass garantizando una tarjeta TOP #N (~2x más grande,
    con fondo semitransparente y delay de 0.35s post-glitch) al inicio de cada puesto."""
    from .edicion import cargar_config_edicion

    guion = cargar_guion(p)
    top_n = top_n_explicito(guion, p.tema)
    asegurar_tarjetas_top(guion, top_n=top_n)

    cfg = cargar_config_edicion()
    top_fx = cfg.get("top_rank_fx", {})
    delay_post_glitch = float(top_fx.get("card_delay_post_glitch_s", 0.35))
    dur_tarjeta = float(top_fx.get("card_duracion_s", 3.5))
    fs_top = int(top_fx.get("card_font_size_top", 184))
    fs_titulo = int(top_fx.get("card_font_size_titulo", 116))
    back_colour = str(top_fx.get("card_back_colour", "&H58000000")).strip()

    carpeta_renders = p.carpeta / "renders"
    carpeta_renders.mkdir(parents=True, exist_ok=True)
    ruta_ass = carpeta_renders / "tarjetas_puestos.ass"

    # Estilo ASS: ~2x más grande (184pt/116pt), centrado (Alignment=5), BorderStyle=3 con caja semitransparente (&H58000000)
    contenido_base = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TopCentered,Arial Black,{fs_top},&H00FFFFFF,&H00000000,{back_colour},{back_colour},1,0,0,0,100,100,3.0,0,3,26,0,5,90,90,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    sin_host = bool(p.datos.get("sin_host", False))
    eventos = []
    tiempo_actual = 0.0
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

        # Aparecer 0.35 s después del glitch/pixelize para no quedar encima de la distorsión
        t_evento_ini = min(max(t_inicio, t_fin - 0.6), t_inicio + delay_post_glitch)
        t_evento_fin = min(t_fin, t_evento_ini + dur_tarjeta)
        ini_str = _formatear_tiempo_ass(t_evento_ini)
        fin_str = _formatear_tiempo_ass(t_evento_fin)

        # Zona segura: lado opuesto al host, franja superior, con margen (nunca encima del avatar)
        host_box = caja_host(esc.pose, esc.host_lado, bool(esc.host_visible) and not sin_host)
        zona = zona_texto(host_box)
        centro_x = int(zona.x + zona.w / 2)
        y_top = 70

        if numero is not None:
            puestos_emitidos.add(numero)
            titulo_ass = titulo.replace("{", "(").replace("}", ")")
            fs_t = ajustar_fuente([f"  TOP #{numero}  "], fs_top, zona.w)
            partes = [
                f"{{\\fs{fs_t}\\3c{back_colour}\\4c{back_colour}\\c&H0000E6FF&}}  TOP #{numero}  "
            ]
            if titulo_ass:
                lineas = partir_en_lineas(titulo_ass, fs_titulo, zona.w)
                fs_l = ajustar_fuente([f"  {l}  " for l in lineas], fs_titulo, zona.w)
                partes += [f"{{\\fs{fs_l}\\c&H00FFFFFF&}}  {l}  " for l in lineas]
            texto_formateado = "\\N".join(partes)
        else:
            txt_ass = txt.replace("{", "(").replace("}", ")")
            lineas = partir_en_lineas(txt_ass, fs_titulo, zona.w)
            fs_l = ajustar_fuente([f"  {l}  " for l in lineas], fs_titulo, zona.w)
            texto_formateado = "\\N".join(
                f"{{\\fs{fs_l}\\3c{back_colour}\\4c{back_colour}\\c&H0000E6FF&}}  {l}  " for l in lineas
            )

        eventos.append(
            f"Dialogue: 1,{ini_str},{fin_str},TopCentered,,0,0,0,,{{\\an8\\pos({centro_x},{y_top})\\fad(200,220)}}{texto_formateado}"
        )

    contenido_final = contenido_base + "\n" + "\n".join(eventos) + "\n"
    ruta_ass.write_text(contenido_final, encoding="utf-8")
    return ruta_ass
