"""Pipeline de Renderizado Cinematográfico con Diseño de Sonido Dinámico (Estilo JonnDezz / Documental Tech).

Capas de Producción de Audio y Video:
  1. Música de Fondo Continua con Ducking Inteligente (baja suavemente durante la locución y sube en pausas/transiciones).
  2. Capa de SFX Dinámicos:
     - whoosh/transición al cambiar de escena.
     - click de ratón y teclado typing al aparecer textos/subtítulos clave en pantalla.
     - impacto de bajo y glitch en escenas de conflicto, alerta o revelación.
  3. Exportación Dual y Stems:
     - stems/voz_ia_master.wav
     - stems/mde_mix.wav (Música ecualizada + Efectos sin voz)
     - renders/{slug}_con_voz_ia.mp4
     - renders/{slug}_sin_voz.mp4 (versión clean lista para doblaje)
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from . import config
from .edicion import (
    cargar_config_edicion,
    construir_filtro_color_textura,
    construir_filtro_ken_burns,
    resolver_overlay_por_mood,
)
from .estado import Proyecto
from .guion import cargar_guion, Guion, Escena, extraer_top_n, asegurar_tarjetas_top
from .host_anim import obtener_sprite


def _ejecutar_cmd(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=True)
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr[-350:] if e.stderr else "Error desconocido"
        print(f"❌ Error FFmpeg: {err_msg}")
        return False


_AVISOS_ASSETS_EMITIDOS: set[str] = set()


def listar_archivos_audio(carpeta: Path) -> list[Path]:
    """Lista archivos de audio (.wav, .mp3, .ogg) válidos en una carpeta."""
    if not carpeta.exists() or not carpeta.is_dir():
        return []
    archivos: list[Path] = []
    for ext in ("*.wav", "*.mp3", "*.ogg"):
        archivos.extend(sorted(carpeta.glob(ext)))
    return [a for a in archivos if a.is_file() and a.stat().st_size > 0]


def resolver_sfx_categoria(cat: str, silencioso: bool = False) -> tuple[Optional[Path], str, bool]:
    """Resuelve la categoría de SFX o su fallback más cercano si está vacía.
    Retorna (ruta_archivo, categoria_efectiva, uso_fallback)."""
    if not cat or cat == "ninguno":
        return None, "ninguno", False

    def _elegir_de_carpeta(c: str) -> Optional[Path]:
        carpeta = config.SFX_DIR / c
        if not carpeta.exists():
            return None
        if c == "teclado":
            for pref in ("typing_corto_boosted.wav", "typing_corto.wav"):
                p_pref = carpeta / pref
                if p_pref.exists() and p_pref.stat().st_size > 0:
                    return p_pref
        archivos = listar_archivos_audio(carpeta)
        return archivos[0] if archivos else None

    directo = _elegir_de_carpeta(cat)
    if directo is not None:
        return directo, cat, False

    candidatos_fb = config.SFX_FALLBACKS.get(cat, ["impacto", "impact", "whoosh", "transicion"])
    for fb in candidatos_fb:
        elegido = _elegir_de_carpeta(fb)
        if elegido is not None:
            clave_aviso = f"sfx:{cat}->{fb}"
            if not silencioso and clave_aviso not in _AVISOS_ASSETS_EMITIDOS:
                _AVISOS_ASSETS_EMITIDOS.add(clave_aviso)
                print(f"   ⚠️ SFX '{cat}' sin archivos en assets/sfx/{cat} -> usando fallback '{fb}' ({elegido.name})")
            return elegido, fb, True

    return None, cat, True


def resolver_musica_mood(mood: str = "misterio", silencioso: bool = False) -> tuple[Optional[Path], str, bool]:
    """Resuelve la pista de música de fondo para el mood o su fallback más cercano (ej. tension->misterio, epica->curiosidad).
    Retorna (ruta_archivo, mood_efectivo, uso_fallback)."""
    mood_limpio = mood if mood in config.MUSIC_MOODS else "misterio"
    archivos_directos = listar_archivos_audio(config.MUSIC_DIR / mood_limpio)
    if archivos_directos:
        return archivos_directos[0], mood_limpio, False

    candidatos_fb = config.MUSIC_FALLBACKS.get(mood_limpio, []) + [m for m in config.MUSIC_MOODS if m != mood_limpio]
    vistos: set[str] = set()
    for fb in candidatos_fb:
        if fb in vistos:
            continue
        vistos.add(fb)
        archivos_fb = listar_archivos_audio(config.MUSIC_DIR / fb)
        if archivos_fb:
            clave_aviso = f"music:{mood_limpio}->{fb}"
            if not silencioso and clave_aviso not in _AVISOS_ASSETS_EMITIDOS:
                _AVISOS_ASSETS_EMITIDOS.add(clave_aviso)
                print(
                    f"   ⚠️ Música mood '{mood_limpio}' sin archivos en assets/music/{mood_limpio} "
                    f"-> usando fallback '{fb}' ({archivos_fb[0].name})"
                )
            return archivos_fb[0], fb, True

    archivos_todos = list(config.MUSIC_DIR.glob("*/*.wav")) + list(config.MUSIC_DIR.glob("*/*.mp3")) + list(config.MUSIC_DIR.glob("*/*.ogg"))
    if archivos_todos:
        return archivos_todos[0], archivos_todos[0].parent.name, True
    return None, mood_limpio, True


def _obtener_sfx(cat: str) -> Optional[Path]:
    """Obtiene un archivo de sonido para la categoría solicitada (con fallback automático si falta)."""
    ruta, _, _ = resolver_sfx_categoria(cat, silencioso=False)
    return ruta


def _obtener_musica_fondo(mood: str = "misterio") -> Optional[Path]:
    """Obtiene la pista de música de fondo documental correspondiente al mood (con fallback automático si falta)."""
    ruta, _, _ = resolver_musica_mood(mood, silencioso=False)
    return ruta


def crear_stems_audio(p: Proyecto, duraciones: dict[int, float], audio_voz_reemplazo: Optional[Path] = None) -> tuple[Path, Path]:
    """Crea stems/voz_ia_master.wav y stems/mde_mix.wav con diseño sonoro completo (música + riser + impact + whoosh)."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    cfg = cargar_config_edicion()
    carpeta_stems = p.carpeta / "stems"
    carpeta_stems.mkdir(parents=True, exist_ok=True)
    guion = cargar_guion(p)
    asegurar_tarjetas_top(guion, top_n=extraer_top_n(p.tema, float(p.datos.get("minutos", 1.0))))
    duracion_total = sum(duraciones.values())

    # 1. PISTA DE VOZ (IA o Reemplazo Humano) — conserva intacta la masterización -16 LUFS y highpass 80 Hz
    voz_master = carpeta_stems / "voz_ia_master.wav"
    if audio_voz_reemplazo and audio_voz_reemplazo.exists():
        cmd_norm = [
            ffmpeg, "-y", "-i", str(audio_voz_reemplazo),
            "-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "24000", "-ac", "1",
            str(voz_master)
        ]
        _ejecutar_cmd(cmd_norm)
    else:
        clips_voz = [p.ruta("voz", f"escena_{e.id:03d}.wav") for e in guion.escenas if p.ruta("voz", f"escena_{e.id:03d}.wav").exists()]
        if clips_voz:
            lista_voz = carpeta_stems / "concat_voz.txt"
            lista_voz.write_text("\n".join([f"file '{c.resolve().as_posix()}'" for c in clips_voz]), "utf-8")
            cmd_concat_voz = [
                ffmpeg, "-y", "-f", "concat", "-safe", "0",
                "-i", str(lista_voz),
                "-c:a", "pcm_s16le", str(voz_master)
            ]
            _ejecutar_cmd(cmd_concat_voz)

    # 2. PISTA DE MÚSICA Y EFECTOS DE SONIDO (MDE MIX)
    mde_master = carpeta_stems / "mde_mix.wav"
    vol_musica = float(cfg.get("audio", {}).get("ducking_sidechain", {}).get("musica_volumen_base", 0.28))

    # A) Pista de Música en Loop ajustada a la duración total
    pista_musica = _obtener_musica_fondo(guion.escenas[0].music_mood if guion.escenas else "misterio")
    temp_musica = carpeta_stems / "temp_music_bed.wav"
    if pista_musica:
        cmd_musica = [
            ffmpeg, "-y",
            "-stream_loop", "-1", "-i", str(pista_musica),
            "-t", f"{duracion_total:.2f}",
            "-af", f"volume={vol_musica:.2f},afade=t=in:ss=0:d=1.5,afade=t=out:st={max(0, duracion_total - 2.5):.2f}:d=2.5",
            "-ar", "24000", "-ac", "1",
            "-c:a", "pcm_s16le", str(temp_musica)
        ]
        _ejecutar_cmd(cmd_musica)
    else:
        cmd_silencio = [
            ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", f"{duracion_total:.2f}",
            "-c:a", "pcm_s16le", str(temp_musica)
        ]
        _ejecutar_cmd(cmd_silencio)

    # B) Planificar eventos de SFX a lo largo de la línea de tiempo:
    #    - En cada TOP #N: riser 1-2s antes + impact al aparecer la tarjeta .ass + whoosh + teclado
    #    - En cada transición xfade entre escenas: whoosh sutil sincronizado
    #    - SFX específicos del guion (glitch, revelación, tensión, ambiente, digital)
    eventos_sfx: list[tuple[float, Path, float]] = []
    t_acum = 0.0
    puestos_sfx_vistos: set[int] = set()

    top_fx = cfg.get("top_rank_fx", {})
    top_fx_on = bool(cfg.get("formatos", {}).get("horizontal_16_9", {}).get("top_rank_fx", True) and top_fx.get("enabled", True))
    riser_lead_s = float(top_fx.get("riser_lead_s", 1.5))
    riser_vol = float(top_fx.get("riser_volume", 0.65))
    impact_vol = float(top_fx.get("impact_volume", 0.85))
    tr_cfg = cfg.get("transiciones", {})
    whoosh_en_cortes = bool(tr_cfg.get("enabled", True) and tr_cfg.get("sfx_whoosh", True))

    for i, esc in enumerate(guion.escenas, 1):
        dur = duraciones.get(esc.id, 5.0)
        txt = (esc.texto_pantalla or "").strip()
        es_inicio_puesto = bool(esc.puesto and esc.puesto_titulo and esc.puesto not in puestos_sfx_vistos)
        if es_inicio_puesto and esc.puesto:
            puestos_sfx_vistos.add(esc.puesto)
        es_top = es_inicio_puesto or bool(re.search(r"(?:#|top\s*#?|puesto\s*#?)\s*\d+", txt, re.IGNORECASE))
        es_titulo = es_inicio_puesto or bool(txt)

        if es_top:
            # 1a. Riser de 1-2 s ANTES de aparecer la tarjeta TOP #N
            if top_fx_on and top_fx.get("riser_enabled", True) and t_acum >= 0.4:
                sfx_riser = _obtener_sfx("riser")
                if sfx_riser:
                    eventos_sfx.append((max(0.0, t_acum - riser_lead_s), sfx_riser, riser_vol))

            # 1b. Impacto profundo exactamente al aparecer la tarjeta TOP #N
            if top_fx_on and top_fx.get("impact_enabled", True):
                sfx_imp = _obtener_sfx("impact") or _obtener_sfx("impacto")
                if sfx_imp:
                    eventos_sfx.append((t_acum, sfx_imp, impact_vol))

            # 1c. Whoosh de transición
            sfx_trans = _obtener_sfx("whoosh") or _obtener_sfx("transicion")
            if sfx_trans:
                eventos_sfx.append((t_acum, sfx_trans, 0.60))
        elif i > 1 and whoosh_en_cortes:
            # Whoosh sutil sincronizado con la transición xfade entre escenas normales
            sfx_whoosh = _obtener_sfx("whoosh") or _obtener_sfx("transicion")
            if sfx_whoosh:
                eventos_sfx.append((max(0.0, t_acum - 0.12), sfx_whoosh, 0.35))

        # 2. Sonido de Typing/Click al aparecer la tarjeta en pantalla
        if es_titulo:
            sfx_teclado = _obtener_sfx("teclado") or _obtener_sfx("click")
            if sfx_teclado:
                eventos_sfx.append((t_acum + 0.15, sfx_teclado, 0.80))

        # 3. SFX explícito del guion (impacto, revelación, glitch, tension, ambiente, digital...)
        if esc.sfx and esc.sfx not in ("ninguno", "whoosh", "transicion"):
            sfx_especifico = _obtener_sfx(esc.sfx)
            if sfx_especifico:
                eventos_sfx.append((t_acum + 0.3, sfx_especifico, 0.50))

        t_acum += dur

    # C) Mezclar música de fondo + todos los SFX programados
    if eventos_sfx:
        inputs = ["-i", str(temp_musica)]
        filtros_delay = ["[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[bgm_clean]"]
        mix_labels = ["[bgm_clean]"]

        for idx, (timestamp_s, ruta_sfx, vol) in enumerate(eventos_sfx[:55], 1):
            inputs += ["-i", str(ruta_sfx)]
            delay_ms = max(0, int(timestamp_s * 1000))
            vol_ajustado = min(2.0, vol * 1.5)
            filtros_delay.append(
                f"[{idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
                f"adelay={delay_ms}|{delay_ms},volume={vol_ajustado:.2f}[sfx{idx}]"
            )
            mix_labels.append(f"[sfx{idx}]")

        cadena_mix = f"{';'.join(filtros_delay)};{''.join(mix_labels)}amix=inputs={len(mix_labels)}:normalize=0[mde_out]"
        cmd_mezcla_total = [
            ffmpeg, "-y",
            *inputs,
            "-filter_complex", cadena_mix,
            "-map", "[mde_out]",
            "-t", f"{duracion_total:.2f}",
            "-ar", "44100", "-ac", "2",
            "-c:a", "pcm_s16le",
            str(mde_master)
        ]
        if _ejecutar_cmd(cmd_mezcla_total):
            if temp_musica.exists():
                temp_musica.unlink()
        else:
            temp_musica.replace(mde_master)
    else:
        temp_musica.replace(mde_master)

    return voz_master, mde_master


from .broll import obtener_duracion_video, es_video_valido


def _buscar_clip_complementario(p: Proyecto, actual: Path) -> Optional[Path]:
    """Busca un segundo clip distinto dentro de b_roll/ para encadenar si el clip principal es corto."""
    carpeta = p.ruta("b_roll")
    if not carpeta.exists():
        return None
    candidatos = sorted(
        [c for c in carpeta.glob("escena_*.mp4") if c.resolve() != actual.resolve() and es_video_valido(c)],
        key=lambda c: obtener_duracion_video(c),
        reverse=True,
    )
    return candidatos[0] if candidatos else None


def renderizar_clip_visual(
    p: Proyecto,
    esc: Escena,
    duracion: float,
    destino_mp4: Path,
    es_cierre: bool = False,
    es_inicio_top: bool = False,
    cfg: Optional[dict] = None,
) -> bool:
    """Renderiza el corte visual en 1080p con:
    - Grado de color por mood (curves/eq/colorbalance)
    - Viñeta (vignette=PI/5) + grano ligero FFmpeg (noise=alls=8:allf=t)
    - Overlay de polvo/grano/glitch en blend=screen (15-25%)
    - Movimiento Ken Burns (zoompan lento 1.00 a 1.08) en clips estáticos o cortos
    - Flash + glitch (rgbashift) al iniciar un puesto TOP #N
    - Host personalizado en capa frontal."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    cfg = cfg or cargar_config_edicion()
    fmt_cfg = cfg.get("formatos", {}).get("horizontal_16_9", {})
    kb_cfg = cfg.get("ken_burns", {})
    usar_kb = bool(fmt_cfg.get("ken_burns", True) and kb_cfg.get("enabled", True))

    broll_mp4 = p.ruta("b_roll", f"escena_{esc.id:03d}.mp4")
    broll_jpg = p.ruta("b_roll", f"escena_{esc.id:03d}.jpg")

    fondo_es_video = broll_mp4.exists() and es_video_valido(broll_mp4)
    fondo_archivo = broll_mp4 if fondo_es_video else (broll_jpg if broll_jpg.exists() else None)

    sin_host = p.datos.get("sin_host", False)
    host_sprite = (
        obtener_sprite(esc.pose, boca="cerrada", mood=esc.music_mood, tema=p.tema, texto_voz=esc.voz)
        if (esc.host_visible and not sin_host)
        else None
    )

    inputs: list[str] = []
    filtros: list[str] = []
    num_inputs = 0

    if fondo_archivo and fondo_es_video:
        dur_clip = obtener_duracion_video(fondo_archivo)
        es_corto = (dur_clip + 0.25 < duracion)
        segundo_clip = _buscar_clip_complementario(p, fondo_archivo) if es_corto else None
        if segundo_clip:
            inputs += ["-i", str(fondo_archivo), "-stream_loop", "-1", "-i", str(segundo_clip)]
            num_inputs = 2
            filtros.append(
                "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(1920-iw)/2:(1080-ih)/2:color=black,setsar=1,fps=30,format=yuv420p[bg0]"
            )
            filtros.append(
                "[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(1920-iw)/2:(1080-ih)/2:color=black,setsar=1,fps=30,format=yuv420p[bg1]"
            )
            filtros.append("[bg0][bg1]concat=n=2:v=1:a=0[bg_raw]")
        else:
            inputs += ["-stream_loop", "-1", "-i", str(fondo_archivo)]
            num_inputs = 1
            if usar_kb and kb_cfg.get("aplicar_en_clips_cortos", True) and dur_clip < max(6.0, duracion):
                kb_expr = construir_filtro_ken_burns(duracion, 1920, 1080, 30, cfg=cfg)
                filtros.append(f"[0:v]{kb_expr}[bg_raw]")
            else:
                filtros.append(
                    "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                    "pad=1920:1080:(1920-iw)/2:(1080-ih)/2:color=black,setsar=1,fps=30[bg_raw]"
                )
    elif fondo_archivo and not fondo_es_video:
        inputs += ["-loop", "1", "-i", str(fondo_archivo)]
        num_inputs = 1
        if usar_kb and kb_cfg.get("aplicar_en_estaticos", True):
            kb_expr = construir_filtro_ken_burns(duracion, 1920, 1080, 30, cfg=cfg)
            filtros.append(f"[0:v]{kb_expr}[bg_raw]")
        else:
            filtros.append(
                "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(1920-iw)/2:(1080-ih)/2:color=black,setsar=1,fps=30[bg_raw]"
            )
    else:
        inputs += ["-f", "lavfi", "-i", "color=c=0x111625:s=1920x1080:r=30"]
        num_inputs = 1
        filtros.append("[0:v]null[bg_raw]")

    # Grado de color por mood + viñeta + grano ligero FFmpeg + flash/glitch en apertura de puesto TOP #N
    filtro_look = construir_filtro_color_textura(
        mood=esc.music_mood,
        formato="horizontal_16_9",
        es_inicio_top=es_inicio_top,
        cfg=cfg,
    )
    filtros.append(f"[bg_raw]{filtro_look}[bg_graded]")
    v_previo = "[bg_graded]"

    # Overlay de polvo/grano/light_leak/glitch en blend=screen al 15-25% (si está activo y existe asset)
    ov_cfg = cfg.get("textura_visual", {}).get("video_overlay", {})
    if fmt_cfg.get("video_overlay", True) and ov_cfg.get("enabled", True):
        ruta_ov, _ = resolver_overlay_por_mood(
            mood=esc.music_mood,
            idx_escena=esc.id,
            es_inicio_top=es_inicio_top,
            cfg=cfg,
            silencioso=False,
        )
        if ruta_ov and ruta_ov.exists():
            ov_idx = num_inputs
            num_inputs += 1
            inputs += ["-stream_loop", "-1", "-i", str(ruta_ov)]
            blend_mode = ov_cfg.get("blend_mode", "screen")
            opacity = float(ov_cfg.get("opacity", 0.18))
            filtros.append(
                f"[{ov_idx}:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                f"crop=1920:1080,setsar=1,fps=30,format=yuv420p[ov]"
            )
            filtros.append(
                f"{v_previo}[ov]blend=all_mode={blend_mode}:all_opacity={opacity:.2f}:shortest=1,format=yuv420p[bg_ov]"
            )
            v_previo = "[bg_ov]"

    # Host personalizado en capa frontal
    if host_sprite and host_sprite.exists():
        tight_sprite = config.ASSETS / "host_tight" / host_sprite.name
        sprite_a_usar = tight_sprite if tight_sprite.exists() else host_sprite
        host_idx = num_inputs
        num_inputs += 1
        inputs += ["-loop", "1", "-i", str(sprite_a_usar)]
        from .layout import HOST_ALTO, HOST_MARGEN_X
        pos_x = f"1920-w-{HOST_MARGEN_X}" if esc.host_lado == "derecha" else f"{HOST_MARGEN_X}"
        filtros.append(f"[{host_idx}:v]scale=-1:{HOST_ALTO}[host]")
        filtros.append(f"{v_previo}[host]overlay={pos_x}:1080-h:shortest=1[v_con_host]")
        v_previo = "[v_con_host]"

    # Fundido a negro en el clip de cierre (fade out 0.5s)
    if es_cierre:
        fade_st = max(0.0, duracion - 0.5)
        filtros.append(f"{v_previo}fade=t=out:st={fade_st:.2f}:d=0.5[v_salida]")
    else:
        filtros.append(f"{v_previo}null[v_salida]")

    filtro_completo = ";".join(filtros)
    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filtro_completo,
        "-map", "[v_salida]",
        "-t", f"{duracion:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(destino_mp4)
    ]
    ok = _ejecutar_cmd(cmd)
    if not ok or not destino_mp4.exists() or destino_mp4.stat().st_size < 1000:
        print(f"   ⚠️ Reintentando renderizado fallback sólido para escena {esc.id}...")
        cmd_fallback = [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", "color=c=0x111625:s=1920x1080:r=30",
            "-t", f"{duracion:.2f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-an",
            str(destino_mp4)
        ]
        return _ejecutar_cmd(cmd_fallback)
    return True


def _ensamblar_visual_xfade_o_concat(
    ffmpeg: str,
    clips_visuales: list[Path],
    duraciones_base: list[float],
    es_top_flags: list[bool],
    dur_transicion: float,
    usar_xfade: bool,
    ruta_ass_escapada: str,
    temp_clips: Path,
    video_mudo: Path,
    cfg: dict,
) -> bool:
    """Une los clips visuales aplicando transiciones xfade (fade, fadeblack, smoothleft y glitch en cambios de Top)
    y quema las tarjetas .ass. Si xfade está desactivado o falla, degrada limpiamente a concat."""
    clips_existentes = [c for c in clips_visuales if c.exists()]
    ifusar = usar_xfade and len(clips_existentes) == len(clips_visuales) and 1 < len(clips_existentes) <= 35 and dur_transicion > 0.05

    if ifusar:
        tr_cfg = cfg.get("transiciones", {})
        tipos_norm = tr_cfg.get("tipos_normales") or ["fade", "fadeblack", "smoothleft"]
        inputs: list[str] = []
        filtros: list[str] = []
        for idx, c in enumerate(clips_existentes):
            inputs += ["-i", str(c)]
            filtros.append(f"[{idx}:v]fps=30,format=yuv420p,settb=AVTB[v{idx}]")

        prev_label = "[v0]"
        offset_acum = 0.0
        for idx in range(1, len(clips_existentes)):
            offset_acum += duraciones_base[idx - 1]
            # Si la escena que entra inicia un puesto TOP #N, usamos transición glitch/pixelize o fadeblack
            if es_top_flags[idx]:
                trans_name = "pixelize" if (idx % 2 == 1) else "fadeblack"
            else:
                trans_name = tipos_norm[(idx - 1) % len(tipos_norm)]
            out_label = f"[vx{idx}]"
            filtros.append(
                f"{prev_label}[v{idx}]xfade=transition={trans_name}:duration={dur_transicion:.2f}:offset={offset_acum:.2f}{out_label}"
            )
            prev_label = out_label

        filtros.append(f"{prev_label}ass='{ruta_ass_escapada}',format=yuv420p[v_final]")
        cmd_xfade = [
            ffmpeg, "-y",
            *inputs,
            "-filter_complex", ";".join(filtros),
            "-map", "[v_final]",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-an",
            str(video_mudo),
        ]
        if _ejecutar_cmd(cmd_xfade) and video_mudo.exists() and video_mudo.stat().st_size > 1000:
            return True
        print("   ⚠️ Aviso: xfade falló o excedió límites -> degradando con elegancia a concat estándar.")

    # Fallback: concat directo
    lista_v = temp_clips / "concat_v.txt"
    lista_v.write_text("\n".join([f"file '{c.resolve().as_posix()}'" for c in clips_existentes]), "utf-8")
    cmd_concat_v = [
        ffmpeg, "-y", "-f", "concat", "-safe", "0",
        "-i", str(lista_v),
        "-vf", f"ass='{ruta_ass_escapada}'",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(video_mudo),
    ]
    return _ejecutar_cmd(cmd_concat_v)


def etapa_render(p: Proyecto, duraciones: dict[int, float], voz_humana: Optional[Path] = None) -> dict[str, Path]:
    """Genera Stems de audio enriquecidos con música/SFX y exporta versión IA (con sidechain ducking) y versión Karaoke."""
    from .subtitulos import generar_tarjetas_ass

    ffmpeg = config.ffmpeg_bin("ffmpeg")
    cfg = cargar_config_edicion()
    fmt_cfg = cfg.get("formatos", {}).get("horizontal_16_9", {})
    guion = cargar_guion(p)
    asegurar_tarjetas_top(guion, top_n=extraer_top_n(p.tema, float(p.datos.get("minutos", 1.0))))

    carpeta_renders = p.carpeta / "renders"
    carpeta_renders.mkdir(parents=True, exist_ok=True)
    temp_clips = carpeta_renders / "temp_visual"
    temp_clips.mkdir(parents=True, exist_ok=True)

    slug = p.datos.get("slug", "video")

    # 1. Stems con Diseño de Sonido Dinámico (Música de fondo + Riser + Impact + Whoosh + SFX)
    print("🎧 Generando Stems con Diseño de Sonido (Música documental + Riser/Impact en TOP #N + SFX)...")
    voz_master, mde_master = crear_stems_audio(p, duraciones, audio_voz_reemplazo=voz_humana)

    # 2. Clips Visuales (B-roll con Color Grading + Viñeta + Grano + Overlay Screen + Ken Burns + Host)
    total = len(guion.escenas)
    usar_xfade = bool(
        fmt_cfg.get("transiciones_xfade", True)
        and cfg.get("transiciones", {}).get("enabled", True)
        and 1 < total <= 35
    )
    dur_transicion = float(cfg.get("transiciones", {}).get("duracion_s", 0.35)) if usar_xfade else 0.0

    print(f"🎬 Renderizando visuales de {total} escenas (Color grade por mood, viñeta, grano, overlays y Ken Burns)...")
    clips_visuales: list[Path] = []
    duraciones_base: list[float] = []
    es_top_flags: list[bool] = []
    puestos_vistos_render: set[int] = set()

    for i, esc in enumerate(guion.escenas, 1):
        dur_base = duraciones.get(esc.id, 5.0)
        duraciones_base.append(dur_base)
        es_cierre = (i == total)
        # Añadimos cola de solapamiento (+dur_transicion) para que xfade no acorte el video ni desincronice el audio
        dur_clip_render = dur_base if es_cierre else (dur_base + dur_transicion)

        txt = (esc.texto_pantalla or "").strip()
        es_inicio_puesto = bool(esc.puesto and esc.puesto_titulo and esc.puesto not in puestos_vistos_render)
        if es_inicio_puesto and esc.puesto:
            puestos_vistos_render.add(esc.puesto)
        es_top = es_inicio_puesto or bool(re.search(r"(?:#|top\s*#?|puesto\s*#?)\s*\d+", txt, re.IGNORECASE))
        es_top_flags.append(es_top)

        clip_path = temp_clips / f"vclip_{esc.id:03d}.mp4"
        if not clip_path.exists() or clip_path.stat().st_size < 1000:
            renderizar_clip_visual(
                p,
                esc,
                dur_clip_render,
                clip_path,
                es_cierre=es_cierre,
                es_inicio_top=es_top,
                cfg=cfg,
            )
        clips_visuales.append(clip_path)

    # 3. Generar Tarjetas .ass y Ensamblar con Transiciones xfade (fade, fadeblack, smoothleft y glitch en TOP #N)
    print("🎨 Aplicando transiciones xfade y quemando tarjetas estilizadas TOP #N (.ass)...")
    ruta_ass = generar_tarjetas_ass(p, duraciones)
    ruta_ass_escapada = str(ruta_ass.resolve().as_posix()).replace(':', '\\:')

    video_mudo = temp_clips / "visual_completo.mp4"
    _ensamblar_visual_xfade_o_concat(
        ffmpeg=ffmpeg,
        clips_visuales=clips_visuales,
        duraciones_base=duraciones_base,
        es_top_flags=es_top_flags,
        dur_transicion=dur_transicion,
        usar_xfade=usar_xfade,
        ruta_ass_escapada=ruta_ass_escapada,
        temp_clips=temp_clips,
        video_mudo=video_mudo,
        cfg=cfg,
    )

    duracion_total = sum(duraciones.values())
    fade_audio_st = max(0.0, duracion_total - 0.5)

    # 4. Exportar Versión IA (Voz principal a -16 LUFS + MDE con sidechaincompress ducking)
    video_con_voz = carpeta_renders / f"{slug}_con_voz_ia.mp4"
    print(f"🎥 Ensamblando Versión IA Dinámica con Sidechain Ducking: {video_con_voz.name}...")
    duck_cfg = cfg.get("audio", {}).get("ducking_sidechain", {})
    usar_ducking = bool(fmt_cfg.get("audio_ducking_sidechain", True) and duck_cfg.get("enabled", True))

    if usar_ducking:
        thr = float(duck_cfg.get("threshold", 0.035))
        rat = float(duck_cfg.get("ratio", 5.0))
        atk = int(duck_cfg.get("attack_ms", 35))
        rel = int(duck_cfg.get("release_ms", 450))
        mkp = float(duck_cfg.get("makeup", 1.0))
        filtro_audio_ia = (
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0,asplit=2[v_aud][v_sc];"
            f"[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.95[mde_in];"
            f"[mde_in][v_sc]sidechaincompress=threshold={thr:.3f}:ratio={rat:.1f}:attack={atk}:release={rel}:makeup={mkp:.1f}[mde_duck];"
            f"[v_aud][mde_duck]amix=inputs=2:normalize=0,afade=t=out:st={fade_audio_st:.2f}:d=0.5[a_final]"
        )
    else:
        filtro_audio_ia = (
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[v_aud];"
            f"[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.85[mde_aud];"
            f"[v_aud][mde_aud]amix=inputs=2:normalize=0,afade=t=out:st={fade_audio_st:.2f}:d=0.5[a_final]"
        )

    cmd_ia = [
        ffmpeg, "-y",
        "-i", str(video_mudo),
        "-i", str(voz_master),
        "-i", str(mde_master),
        "-filter_complex", filtro_audio_ia,
        "-map", "0:v",
        "-map", "[a_final]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-shortest",
        str(video_con_voz)
    ]
    if not _ejecutar_cmd(cmd_ia):
        # Fallback sin sidechaincompress si algo fallara
        cmd_ia_fb = [
            ffmpeg, "-y",
            "-i", str(video_mudo),
            "-i", str(voz_master),
            "-i", str(mde_master),
            "-filter_complex",
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[v_aud];"
            f"[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.85[mde_aud];"
            f"[v_aud][mde_aud]amix=inputs=2:normalize=0,afade=t=out:st={fade_audio_st:.2f}:d=0.5[a_final]",
            "-map", "0:v", "-map", "[a_final]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(video_con_voz)
        ]
        _ejecutar_cmd(cmd_ia_fb)

    # 5. Exportar Versión Clean / Karaoke (Música y SFX sin locución)
    video_sin_voz = carpeta_renders / f"{slug}_sin_voz.mp4"
    print(f"🎤 Ensamblando Versión Clean / Karaoke: {video_sin_voz.name}...")
    cmd_clean = [
        ffmpeg, "-y",
        "-i", str(video_mudo),
        "-i", str(mde_master),
        "-filter_complex",
        f"[1:a]afade=t=out:st={fade_audio_st:.2f}:d=0.5[a_clean]",
        "-map", "0:v",
        "-map", "[a_clean]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(video_sin_voz)
    ]
    _ejecutar_cmd(cmd_clean)

    p.marcar("render", "ok")
    return {
        "voz_master": voz_master,
        "mde_master": mde_master,
        "video_con_voz": video_con_voz,
        "video_sin_voz": video_sin_voz,
    }
