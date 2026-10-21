"""Renderizador Vertical de TikTok / Shorts (1080x1920) a 60/30fps.
Integra:
1. Fondo 9:16 con desenfoque dinámico / crop inteligente (Full Bleed).
2. Host personalizado como burbuja / overlay en la ESQUINA INFERIOR IZQUIERDA.
3. Subtítulos dinámicos de alto impacto (estilo Hormozi) centrados en Safe Zone.
4. Mezcla de audio con música acelerada y SFX de whoosh en cada corte rápido.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from src import config
from src.estado import Proyecto
from src.render import _obtener_sfx, _obtener_musica_fondo
from src_tiktok.guion_tt import GuionTikTok


def _formatear_tiempo_ass(segundos: float) -> str:
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    cs = int(round((segundos - int(segundos)) * 100))
    if cs >= 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generar_subtitulos_vertical_ass(p: Proyecto, guion: GuionTikTok, duraciones: dict[int, float]) -> Path:
    carpeta_renders = p.carpeta / "renders"
    carpeta_renders.mkdir(parents=True, exist_ok=True)
    ruta_ass = carpeta_renders / "subtitulos_vertical.ass"

    # Estilo Vertical: 1080x1920, Fuente Impact / Arial Black gigante en el tercio medio (y=1050), Outline grueso negro
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTokWord,Arial Black,96,&H0000FFFF,&H00000000,&H00000000,&HD0000000,1,0,0,0,100,100,2,0,1,14,8,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    eventos = []
    t_act = 0.0

    for esc in guion.escenas:
        dur = duraciones.get(esc.id, 3.0)
        t_ini = t_act
        t_fin = t_act + dur
        t_act = t_fin

        txt = (esc.texto_destacado or "").strip().upper()
        if not txt:
            # Si no hay texto destacado, usar primeras 3 palabras de voz
            txt = " ".join(esc.voz.split()[:3]).upper()

        ini_str = _formatear_tiempo_ass(t_ini)
        fin_str = _formatear_tiempo_ass(t_fin)

        # Alternar colores dinámicos: Amarillo Neón (&H0000FFFF) y Cian Neón (&H00FFFF00)
        color = "&H0000FFFF&" if (esc.id % 2 == 1) else "&H00FFFF00&"
        eventos.append(
            f"Dialogue: 1,{ini_str},{fin_str},TikTokWord,,0,0,0,,{{\\fad(80,80)}}{{\\c{color}}}{txt}"
        )

    ruta_ass.write_text(header + "\n" + "\n".join(eventos) + "\n", encoding="utf-8")
    return ruta_ass


def render_clip_vertical(ffmpeg: str, fondo: Path, host_sprite: Path | None, duracion: float, destino: Path):
    """Convierte cualquier video (horizontal o vertical) en 1080x1920 y añade al host en esquina inferior."""
    inputs = ["-stream_loop", "-1", "-i", str(fondo)]
    
    # 1. Fondo: Escalar a 1080x1920 con recorte centrado o desenfoque estético
    # Usamos scale crop dinámico para llenar toda la pantalla vertical 9:16
    filtros = [
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30[bg]"
    ]
    v_actual = "[bg]"

    # 2. Host en Esquina Inferior Izquierda (Opción 3: Extra Grande ~50% pantalla, anclado al marco inferior)
    if host_sprite and host_sprite.exists():
        inputs += ["-loop", "1", "-i", str(host_sprite)]
        filtros.append("[1:v]scale=1150:-1[host]")
        # Posición: x=-220, y=1920-h (anclado directamente al borde inferior de la pantalla sin flotar)
        filtros.append(f"{v_actual}[host]overlay=-220:1920-h:shortest=1[v_out]")
        v_actual = "[v_out]"

    cadena_filtros = ";".join(filtros)
    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", cadena_filtros,
        "-map", v_actual,
        "-t", f"{duracion:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(destino)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def etapa_render_tiktok(p: Proyecto, guion: GuionTikTok, duraciones: dict[int, float]) -> Path:
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    carpeta_renders = p.carpeta / "renders"
    carpeta_renders.mkdir(parents=True, exist_ok=True)
    temp_dir = carpeta_renders / "temp_vertical"
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("🎨 Generando clips verticales 1080x1920 con Avatar en esquina inferior...")
    clips_v = []
    
    # Render de cada escena vertical
    for esc in guion.escenas:
        dur = duraciones.get(esc.id, 3.0)
        broll_f = p.ruta("b_roll", f"escena_{esc.id:03d}.mp4")
        if not broll_f.exists():
            # Fallback cinematográfico abstracto oscuro (nunca el avatar como fondo)
            bg_fb = temp_dir / f"bg_fallback_{esc.id:03d}.mp4"
            cmd_fb = [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", "color=c=0x0f141c:s=1080x1920:r=30",
                "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-an", str(bg_fb)
            ]
            subprocess.run(cmd_fb, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            broll_f = bg_fb
            
        out_v = temp_dir / f"clip_v_{esc.id:03d}.mp4"
        
        # Avatar del host validado por mood/tema
        from src.host_anim import obtener_sprite
        host_png = obtener_sprite(esc.pose_host, boca="cerrada", mood="misterio", tema=p.tema, texto_voz=esc.voz)

        render_clip_vertical(ffmpeg, broll_f, host_png, dur, out_v)
        clips_v.append(out_v)

    # Concatenar todos los clips visuales
    concat_txt = temp_dir / "concat_vertical.txt"
    concat_txt.write_text("\n".join([f"file '{c.resolve().as_posix()}'" for c in clips_v]), encoding="utf-8")
    
    # Subtítulos ASS verticales
    ruta_ass = generar_subtitulos_vertical_ass(p, guion, duraciones)
    ruta_ass_esc = str(ruta_ass.resolve().as_posix()).replace(':', '\\:')

    video_mudo = temp_dir / "vertical_con_subtitulos.mp4"
    cmd_cat = [
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-vf", f"ass={ruta_ass_esc}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(video_mudo)
    ]
    subprocess.run(cmd_cat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Diseño de sonido vertical (Voz + Música acelerada + SFX en cada corte)
    print("🎧 Mezclando audio vertical dinámico con transiciones sonoras...")
    total_dur = sum(duraciones.values())
    
    # Stems de voz concatenados
    lista_voz = temp_dir / "concat_voz.txt"
    lista_voz.write_text("\n".join([f"file '{p.ruta('voz', f'escena_{esc.id:03d}.mp3').resolve().as_posix()}'" for esc in guion.escenas]), encoding="utf-8")
    voz_full = temp_dir / "voz_full.wav"
    cmd_voz = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lista_voz), "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(voz_full)]
    subprocess.run(cmd_voz, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Música de fondo documental
    musica_src = _obtener_musica_fondo("misterio") or _obtener_musica_fondo("tension")
    
    # SFX de whoosh para cada cambio de escena
    whoosh_sfx = _obtener_sfx("whoosh") or _obtener_sfx("transicion")

    # Nota: en cmd_final el input 0 es video_mudo.
    # Por lo tanto, voz_full es input 1, musica_src es input 2, y los sfx empiezan en input 3.
    audio_inputs = ["-i", str(voz_full), "-stream_loop", "-1", "-i", str(musica_src)]
    filter_parts = [
        "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.3[vocal]",
        "[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.10[bgm]"
    ]
    mix_elements = ["[vocal]", "[bgm]"]

    # Agregar whoosh en cada corte
    t_acum = 0.0
    for idx, esc in enumerate(guion.escenas[1:], 3): # Empiezan en input 3
        t_acum += duraciones.get(esc.id - 1, 3.0)
        delay_ms = int(t_acum * 1000)
        audio_inputs += ["-i", str(whoosh_sfx)]
        filter_parts.append(
            f"[{idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,adelay={delay_ms}|{delay_ms},volume=0.90[sfx{idx}]"
        )
        mix_elements.append(f"[sfx{idx}]")

    cadena_audio = f"{';'.join(filter_parts)};{''.join(mix_elements)}amix=inputs={len(mix_elements)}:normalize=0[aout]"
    
    video_final_tiktok = carpeta_renders / f"{p.datos.get('slug', 'tiktok')}_tiktok_vertical.mp4"
    cmd_final = [
        ffmpeg, "-y",
        "-i", str(video_mudo),
        *audio_inputs,
        "-filter_complex", cadena_audio,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-t", f"{total_dur:.2f}",
        "-movflags", "+faststart",
        str(video_final_tiktok)
    ]
    subprocess.run(cmd_final, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"🏆 ¡VIDEO VERTICAL DE TIKTOK COMPLETADO!: {video_final_tiktok}")
    return video_final_tiktok
