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
from src.edicion import (
    cargar_config_edicion,
    construir_filtro_color_textura,
    construir_filtro_zoom_punch_vertical,
    resolver_overlay_por_mood,
)
from src.estado import Proyecto
from src.render import _obtener_sfx, _obtener_musica_fondo
from src.voz import limpiar_tags_ssml
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


def _limpiar_token(w: str) -> str:
    return re.sub(r"[^a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]", "", w).upper()


def generar_subtitulos_vertical_ass(p: Proyecto, guion: GuionTikTok, duraciones: dict[int, float]) -> Path:
    """Genera subtítulos ASS verticales tipo Karaoke palabra por palabra más grandes (112pt) con resalte de keywords."""
    cfg = cargar_config_edicion()
    k_cfg = cfg.get("reels_9_16", {}).get("karaoke", {})
    font_size = int(k_cfg.get("font_size", 112))
    palabras_por_linea = max(1, int(k_cfg.get("palabras_por_linea", 3)))
    color_activo = k_cfg.get("color_activo", "&H0000FFFF&")
    color_inactivo = k_cfg.get("color_inactivo", "&H00FFFFFF&")
    color_keyword = k_cfg.get("color_keyword", "&H00FFFF00&")

    carpeta_renders = p.carpeta / "renders"
    carpeta_renders.mkdir(parents=True, exist_ok=True)
    ruta_ass = carpeta_renders / "subtitulos_vertical.ass"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTokKaraoke,Arial Black,{font_size},{color_inactivo},{color_activo},&H00000000,&HD0000000,1,0,0,0,100,100,2,0,1,16,9,5,55,55,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    eventos: list[str] = []
    t_act = 0.0

    for esc in guion.escenas:
        dur = duraciones.get(esc.id, 2.5)
        t_ini_esc = t_act
        t_fin_esc = t_act + dur
        t_act = t_fin_esc

        voz_limpia = limpiar_tags_ssml(esc.voz or "")
        palabras = [w.strip() for w in voz_limpia.split() if w.strip()]
        if not palabras:
            continue

        keywords_set = {_limpiar_token(k) for k in (esc.texto_destacado or "").split() if _limpiar_token(k)}
        pesos = [max(2, len(_limpiar_token(w))) for w in palabras]
        peso_total = sum(pesos) or len(palabras)

        # Tiempos exactos por palabra dentro de la escena
        tiempos_palabra: list[tuple[float, float]] = []
        cursor = t_ini_esc
        for idx_w, peso in enumerate(pesos):
            frac = peso / float(peso_total)
            t_w_fin = t_fin_esc if idx_w == len(palabras) - 1 else (cursor + dur * frac)
            tiempos_palabra.append((cursor, t_w_fin))
            cursor = t_w_fin

        # Agrupar de a `palabras_por_linea` (ej. bloques de 2-3 palabras) y resaltar palabra por palabra
        for ini_bloque in range(0, len(palabras), palabras_por_linea):
            bloque_pal = palabras[ini_bloque : ini_bloque + palabras_por_linea]
            bloque_tiempos = tiempos_palabra[ini_bloque : ini_bloque + palabras_por_linea]

            for idx_activo in range(len(bloque_pal)):
                w_ini, w_fin = bloque_tiempos[idx_activo]
                ini_str = _formatear_tiempo_ass(w_ini)
                fin_str = _formatear_tiempo_ass(w_fin)

                tokens_formateados: list[str] = []
                for j, pal_raw in enumerate(bloque_pal):
                    pal_up = pal_raw.upper().replace("{", "(").replace("}", ")")
                    token_limpio = _limpiar_token(pal_up)
                    es_kw = token_limpio in keywords_set
                    if j == idx_activo:
                        col = color_keyword if es_kw else color_activo
                        tokens_formateados.append(
                            f"{{\\c{col}\\fscx114\\fscy114}}{pal_up}{{\\fscx100\\fscy100\\c{color_inactivo}}}"
                        )
                    else:
                        tokens_formateados.append(f"{{\\c{color_inactivo}}}{pal_up}")

                linea_ass = " ".join(tokens_formateados)
                eventos.append(f"Dialogue: 1,{ini_str},{fin_str},TikTokKaraoke,,0,0,0,,{linea_ass}")

    ruta_ass.write_text(header + "\n" + "\n".join(eventos) + "\n", encoding="utf-8")
    return ruta_ass


def render_clip_vertical(
    ffmpeg: str,
    fondo: Path,
    host_sprite: Path | None,
    duracion: float,
    destino: Path,
    idx_escena: int = 1,
    cfg: dict | None = None,
):
    """Convierte cualquier video en 1080x1920 con zoom punch en palabras clave, grado de color oscuro,
    viñeta, grano ligero FFmpeg, overlay screen y host en esquina inferior."""
    cfg = cfg or cargar_config_edicion()
    fmt_cfg = cfg.get("formatos", {}).get("vertical_9_16", {})
    inputs = ["-stream_loop", "-1", "-i", str(fondo)]
    num_inputs = 1

    # 1. Fondo 9:16 con Zoom Punch + Grado de Color + Viñeta + Grano
    zp_expr = construir_filtro_zoom_punch_vertical(duracion, 1080, 1920, 30, cfg=cfg)
    look_expr = construir_filtro_color_textura(mood="misterio", formato="vertical_9_16", es_inicio_top=(idx_escena == 1), cfg=cfg)
    filtros = [f"[0:v]{zp_expr},{look_expr}[bg_graded]"]
    v_actual = "[bg_graded]"

    # 2. Overlay de polvo/grano en blend=screen (15-25%)
    ov_cfg = cfg.get("textura_visual", {}).get("video_overlay", {})
    if fmt_cfg.get("video_overlay", True) and ov_cfg.get("enabled", True):
        ruta_ov, _ = resolver_overlay_por_mood(mood="misterio", idx_escena=idx_escena, cfg=cfg, silencioso=True)
        if ruta_ov and ruta_ov.exists():
            ov_idx = num_inputs
            num_inputs += 1
            inputs += ["-stream_loop", "-1", "-i", str(ruta_ov)]
            blend_mode = ov_cfg.get("blend_mode", "screen")
            opacity = float(ov_cfg.get("opacity", 0.18))
            filtros.append(
                f"[{ov_idx}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,setsar=1,fps=30,format=yuv420p[ov]"
            )
            filtros.append(
                f"{v_actual}[ov]blend=c0_mode={blend_mode}:c0_opacity={opacity:.2f}:c1_mode=normal:c1_opacity=0:c2_mode=normal:c2_opacity=0:shortest=1,format=yuv420p[bg_ov]"
            )
            v_actual = "[bg_ov]"

    # 3. Host en Esquina Inferior Izquierda
    if host_sprite and host_sprite.exists():
        host_idx = num_inputs
        num_inputs += 1
        inputs += ["-loop", "1", "-i", str(host_sprite)]
        filtros.append(f"[{host_idx}:v]scale=1150:-1[host]")
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
    cfg = cargar_config_edicion()
    carpeta_renders = p.carpeta / "renders"
    carpeta_renders.mkdir(parents=True, exist_ok=True)
    temp_dir = carpeta_renders / "temp_vertical"
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("🎨 Generando clips verticales 1080x1920 (cortes rápidos 2-3s, zoom punch, color grade y Karaoke)...")
    clips_v = []

    for esc in guion.escenas:
        dur = duraciones.get(esc.id, 2.5)
        broll_f = p.ruta("b_roll", f"escena_{esc.id:03d}.mp4")
        if not broll_f.exists():
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
        from src.host_anim import obtener_sprite
        host_png = obtener_sprite(esc.pose_host, boca="cerrada", mood="misterio", tema=p.tema, texto_voz=esc.voz)

        render_clip_vertical(ffmpeg, broll_f, host_png, dur, out_v, idx_escena=esc.id, cfg=cfg)
        clips_v.append(out_v)

    concat_txt = temp_dir / "concat_vertical.txt"
    concat_txt.write_text("\n".join([f"file '{c.resolve().as_posix()}'" for c in clips_v]), encoding="utf-8")

    # Subtítulos ASS verticales tipo Karaoke palabra por palabra
    ruta_ass = generar_subtitulos_vertical_ass(p, guion, duraciones)
    ruta_ass_esc = str(ruta_ass.resolve().as_posix()).replace(':', '\\:')

    video_mudo = temp_dir / "vertical_con_subtitulos.mp4"
    cmd_cat = [
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-vf", f"ass='{ruta_ass_esc}'",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(video_mudo)
    ]
    subprocess.run(cmd_cat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Diseño de sonido vertical (Stems + Voz con sidechaincompress ducking + Versión Sin Voz)
    print("🎧 Mezclando audio vertical dinámico con sidechain ducking y exportando salida dual (_con_voz_ia / _sin_voz)...")
    total_dur = sum(duraciones.values())
    slug = p.datos.get("slug", "tiktok")

    lista_voz = temp_dir / "concat_voz.txt"
    lista_voz.write_text(
        "\n".join([f"file '{p.ruta('voz', f'escena_{esc.id:03d}.mp3').resolve().as_posix()}'" for esc in guion.escenas]),
        encoding="utf-8",
    )
    voz_master = carpeta_renders / "voz_ia_master.wav"
    cmd_voz = [
        ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lista_voz),
        "-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(voz_master)
    ]
    subprocess.run(cmd_voz, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    mood_general = getattr(guion, "mood", "misterio") or "misterio"
    musica_src = _obtener_musica_fondo(mood_general) or _obtener_musica_fondo("misterio") or _obtener_musica_fondo("tension")
    whoosh_sfx = _obtener_sfx("whoosh") or _obtener_sfx("transicion")

    # Construir stem MDE (Música + SFX sin voz) para poder exportar tanto _con_voz_ia.mp4 como _sin_voz.mp4
    mde_master = carpeta_renders / "mde_mix.wav"
    mde_inputs = ["-stream_loop", "-1", "-i", str(musica_src)]
    mde_filters = [
        f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,atrim=0:{total_dur:.2f},volume=0.26[bgm]"
    ]
    mde_mix_tags = ["[bgm]"]

    t_acum = 0.0
    for idx_m, esc in enumerate(guion.escenas[1:], 1):
        t_acum += duraciones.get(esc.id - 1, 2.5)
        delay_ms = int(t_acum * 1000)
        sfx_esc = _obtener_sfx(getattr(esc, "sfx", "whoosh") or "whoosh") or whoosh_sfx
        mde_inputs += ["-i", str(sfx_esc)]
        mde_filters.append(
            f"[{idx_m}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,adelay={delay_ms}|{delay_ms},volume=0.80[sfx{idx_m}]"
        )
        mde_mix_tags.append(f"[sfx{idx_m}]")

    cadena_mde = f"{';'.join(mde_filters)};{''.join(mde_mix_tags)}amix=inputs={len(mde_mix_tags)}:duration=first:normalize=0[mde_out]"
    cmd_mde = [
        ffmpeg, "-y",
        *mde_inputs,
        "-filter_complex", cadena_mde,
        "-map", "[mde_out]",
        "-t", f"{total_dur:.2f}",
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        str(mde_master),
    ]
    subprocess.run(cmd_mde, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    duck_cfg = cfg.get("audio", {}).get("ducking_sidechain", {})
    thr = float(duck_cfg.get("threshold", 0.035))
    rat = float(duck_cfg.get("ratio", 5.0))
    atk = int(duck_cfg.get("attack_ms", 35))
    rel = int(duck_cfg.get("release_ms", 450))
    fade_st = max(0.0, total_dur - 0.4)

    cadena_audio_ia = (
        f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0,asplit=2[vocal][v_sc];"
        f"[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.95[mde_in];"
        f"[mde_in][v_sc]sidechaincompress=threshold={thr:.3f}:ratio={rat:.1f}:attack={atk}:release={rel}:makeup=1.0[mde_duck];"
        f"[vocal][mde_duck]amix=inputs=2:normalize=0,afade=t=out:st={fade_st:.2f}:d=0.4[aout]"
    )

    video_con_voz = carpeta_renders / f"{slug}_con_voz_ia.mp4"
    cmd_con_voz = [
        ffmpeg, "-y",
        "-i", str(video_mudo),
        "-i", str(voz_master),
        "-i", str(mde_master),
        "-filter_complex", cadena_audio_ia,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-t", f"{total_dur:.2f}",
        "-movflags", "+faststart",
        str(video_con_voz)
    ]
    subprocess.run(cmd_con_voz, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    video_sin_voz = carpeta_renders / f"{slug}_sin_voz.mp4"
    cmd_sin_voz = [
        ffmpeg, "-y",
        "-i", str(video_mudo),
        "-i", str(mde_master),
        "-filter_complex", f"[1:a]afade=t=out:st={fade_st:.2f}:d=0.4[a_clean]",
        "-map", "0:v",
        "-map", "[a_clean]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-t", f"{total_dur:.2f}",
        "-movflags", "+faststart",
        str(video_sin_voz)
    ]
    subprocess.run(cmd_sin_voz, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    p.marcar("render", "ok")
    return {
        "voz_master": voz_master,
        "mde_master": mde_master,
        "video_con_voz": video_con_voz,
        "video_sin_voz": video_sin_voz,
    }
