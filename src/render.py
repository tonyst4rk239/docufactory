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

    candidatos_fb = config.SFX_FALLBACKS.get(cat, ["impacto", "whoosh", "transicion"])
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
    """Crea stems/voz_ia_master.wav y stems/mde_mix.wav con diseño sonoro completo (música + SFX)."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    carpeta_stems = p.carpeta / "stems"
    carpeta_stems.mkdir(parents=True, exist_ok=True)
    guion = cargar_guion(p)
    asegurar_tarjetas_top(guion, top_n=extraer_top_n(p.tema, float(p.datos.get("minutos", 1.0))))
    duracion_total = sum(duraciones.values())

    # 1. PISTA DE VOZ (IA o Reemplazo Humano)
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

    # A) Pista de Música en Loop ajustada a la duración total con ducking suave
    pista_musica = _obtener_musica_fondo(guion.escenas[0].music_mood if guion.escenas else "misterio")
    temp_musica = carpeta_stems / "temp_music_bed.wav"
    if pista_musica:
        # Loop de música con volumen base sutil (-20 dB aprox, volume=0.22)
        cmd_musica = [
            ffmpeg, "-y",
            "-stream_loop", "-1", "-i", str(pista_musica),
            "-t", f"{duracion_total:.2f}",
            "-af", "volume=0.22,afade=t=in:ss=0:d=1.5,afade=t=out:st=" + f"{max(0, duracion_total - 2.5):.2f}" + ":d=2.5",
            "-ar", "24000", "-ac", "1",
            "-c:a", "pcm_s16le", str(temp_musica)
        ]
        _ejecutar_cmd(cmd_musica)
    else:
        # Silencio si no hay pista
        cmd_silencio = [
            ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", f"{duracion_total:.2f}",
            "-c:a", "pcm_s16le", str(temp_musica)
        ]
        _ejecutar_cmd(cmd_silencio)

    # B) Planificar eventos de SFX a lo largo de la línea de tiempo:
    #    - Transición/Whoosh + Impacto al cambiar de puesto del Top (#N al #1)
    #    - Sonido de Typing/Click únicamente cuando aparece un título/subtítulo, con duración corta (~1.2s)
    #    - SFX específicos del guion (glitch, revelación, impacto)
    eventos_sfx = []
    t_acum = 0.0
    puestos_sfx_vistos: set[int] = set()

    for i, esc in enumerate(guion.escenas, 1):
        dur = duraciones.get(esc.id, 5.0)
        txt = (esc.texto_pantalla or "").strip()
        es_inicio_puesto = bool(esc.puesto and esc.puesto_titulo and esc.puesto not in puestos_sfx_vistos)
        if es_inicio_puesto and esc.puesto:
            puestos_sfx_vistos.add(esc.puesto)
        es_top = es_inicio_puesto or bool(re.search(r"(?:#|top\s*#?|puesto\s*#?)\s*\d+", txt, re.IGNORECASE))
        es_titulo = es_inicio_puesto or bool(txt)

        # 1. Transición sonora al cambiar de puesto del Top (#N..#1)
        if es_top:
            sfx_trans = _obtener_sfx("whoosh") or _obtener_sfx("transicion") or _obtener_sfx("impacto")
            if sfx_trans:
                eventos_sfx.append((t_acum, sfx_trans, 0.60))

        # 2. Sonido de Typing/Click: SOLO cuando se pone título/subtítulo en pantalla y que se corte rápido
        if es_titulo:
            sfx_teclado = _obtener_sfx("teclado") or _obtener_sfx("click")
            if sfx_teclado:
                # Entra 150ms después de la transición para sincro perfecta con la tarjeta
                eventos_sfx.append((t_acum + 0.15, sfx_teclado, 0.85))

        # 3. SFX explícito del guion (impacto, revelación, glitch...)
        if esc.sfx and esc.sfx not in ("ninguno", "whoosh", "transicion"):
            sfx_especifico = _obtener_sfx(esc.sfx)
            if sfx_especifico:
                eventos_sfx.append((t_acum + 0.3, sfx_especifico, 0.50))

        t_acum += dur

    # C) Mezclar música de fondo + todos los SFX programados
    if eventos_sfx:
        inputs = ["-i", str(temp_musica)]
        filtros_delay = []
        mix_labels = ["[0:a]"]

        # Mezclar todos los eventos de la línea de tiempo (hasta 40 eventos)
        # Normalizamos la frecuencia de muestreo de cada SFX a 44.1kHz estéreo para evitar chasquidos, aliasing o silencios
        filtros_delay.append("[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[bgm_clean]")
        mix_labels = ["[bgm_clean]"]

        for idx, (timestamp_s, ruta_sfx, vol) in enumerate(eventos_sfx[:40], 1):
            inputs += ["-i", str(ruta_sfx)]
            delay_ms = max(0, int(timestamp_s * 1000))
            # Ajuste de volumen para que el swoosh y transiciones se escuchen con fuerza y claridad
            vol_ajustado = min(2.0, vol * 1.6)
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


def renderizar_clip_visual(p: Proyecto, esc: Escena, duracion: float, destino_mp4: Path, es_cierre: bool = False) -> bool:
    """Renderiza el corte visual en 1080p con Host personalizado.
    Si el clip dura menos que el audio, encadena un segundo clip distinto en lugar de repetir uno en loop."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    broll_mp4 = p.ruta("b_roll", f"escena_{esc.id:03d}.mp4")
    broll_jpg = p.ruta("b_roll", f"escena_{esc.id:03d}.jpg")

    fondo_es_video = broll_mp4.exists() and es_video_valido(broll_mp4)
    fondo_archivo = broll_mp4 if fondo_es_video else (broll_jpg if broll_jpg.exists() else None)

    # Host personalizado según la pose validada contra el mood y tema (salvo si se desactiva explícitamente)
    sin_host = p.datos.get("sin_host", False)
    host_sprite = (
        obtener_sprite(esc.pose, boca="cerrada", mood=esc.music_mood, tema=p.tema, texto_voz=esc.voz)
        if (esc.host_visible and not sin_host)
        else None
    )

    inputs = []
    filtros = []
    num_inputs = 0

    if fondo_archivo and fondo_es_video:
        dur_clip = obtener_duracion_video(fondo_archivo)
        segundo_clip = _buscar_clip_complementario(p, fondo_archivo) if (dur_clip + 0.25 < duracion) else None
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
            filtros.append("[bg0][bg1]concat=n=2:v=1:a=0[bg]")
        else:
            inputs += ["-stream_loop", "-1", "-i", str(fondo_archivo)]
            num_inputs = 1
            filtros.append(
                "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(1920-iw)/2:(1080-ih)/2:color=black,setsar=1,fps=30[bg]"
            )
    elif fondo_archivo and not fondo_es_video:
        inputs += ["-loop", "1", "-i", str(fondo_archivo)]
        num_inputs = 1
        filtros.append("[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(1920-iw)/2:(1080-ih)/2:color=black,setsar=1,fps=30[bg]")
    else:
        inputs += ["-f", "lavfi", "-i", "color=c=0x111625:s=1920x1080:r=30"]
        num_inputs = 1
        filtros.append("[0:v]null[bg]")

    v_previo = "[bg]"
    if host_sprite and host_sprite.exists():
        tight_sprite = config.ASSETS / "host_tight" / host_sprite.name
        sprite_a_usar = tight_sprite if tight_sprite.exists() else host_sprite
        host_idx = num_inputs
        inputs += ["-loop", "1", "-i", str(sprite_a_usar)]
        pos_x = "1920-w-80" if esc.host_lado == "derecha" else "80"
        filtros.append(f"[{host_idx}:v]scale=-1:750[host]")
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


def etapa_render(p: Proyecto, duraciones: dict[int, float], voz_humana: Optional[Path] = None) -> dict[str, Path]:
    """Genera Stems de audio enriquecidos con música/SFX y exporta versión IA y versión Karaoke."""
    from .subtitulos import generar_tarjetas_ass

    ffmpeg = config.ffmpeg_bin("ffmpeg")
    guion = cargar_guion(p)

    carpeta_renders = p.carpeta / "renders"
    carpeta_renders.mkdir(parents=True, exist_ok=True)
    temp_clips = carpeta_renders / "temp_visual"
    temp_clips.mkdir(parents=True, exist_ok=True)

    slug = p.datos.get("slug", "video")

    # 1. Stems con Diseño de Sonido Dinámico (Música de fondo + SFX)
    print("🎧 Generando Stems con Diseño de Sonido (Música documental + SFX clicks/teclado/whoosh)...")
    voz_master, mde_master = crear_stems_audio(p, duraciones, audio_voz_reemplazo=voz_humana)

    # 2. Clips Visuales (B-roll limpio + Host)
    total = len(guion.escenas)
    print(f"🎬 Renderizando visuales de {total} escenas...")
    clips_visuales = []
    for i, esc in enumerate(guion.escenas, 1):
        dur = duraciones.get(esc.id, 5.0)
        clip_path = temp_clips / f"vclip_{esc.id:03d}.mp4"
        es_cierre = (i == total)
        if not clip_path.exists() or clip_path.stat().st_size < 1000:
            renderizar_clip_visual(p, esc, dur, clip_path, es_cierre=es_cierre)
        clips_visuales.append(clip_path)

    # 3. Generar y Quemar Tarjetas de Puesto del Top (.ass)
    print("🎨 Generando tarjetas de puesto estilizadas (.ass)...")
    ruta_ass = generar_tarjetas_ass(p, duraciones)
    ruta_ass_escapada = str(ruta_ass.resolve().as_posix()).replace(':', '\\:')

    lista_v = temp_clips / "concat_v.txt"
    lista_v.write_text("\n".join([f"file '{c.resolve().as_posix()}'" for c in clips_visuales if c.exists()]), "utf-8")
    video_mudo = temp_clips / "visual_completo.mp4"
    cmd_concat_v = [
        ffmpeg, "-y", "-f", "concat", "-safe", "0",
        "-i", str(lista_v),
        "-vf", f"ass='{ruta_ass_escapada}'",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-an",
        str(video_mudo)
    ]
    _ejecutar_cmd(cmd_concat_v)

    duracion_total = sum(duraciones.values())
    fade_audio_st = max(0.0, duracion_total - 0.5)

    # 4. Exportar Versión IA (Voz principal + MDE de fondo)
    video_con_voz = carpeta_renders / f"{slug}_con_voz_ia.mp4"
    print(f"🎥 Ensamblando Versión IA Dinámica: {video_con_voz.name}...")
    cmd_ia = [
        ffmpeg, "-y",
        "-i", str(video_mudo),
        "-i", str(voz_master),
        "-i", str(mde_master),
        "-filter_complex",
        f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.0[v_aud];"
        f"[2:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.85[mde_aud];"
        f"[v_aud][mde_aud]amix=inputs=2:normalize=0,afade=t=out:st={fade_audio_st:.2f}:d=0.5[a_final]",
        "-map", "0:v",
        "-map", "[a_final]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-shortest",
        str(video_con_voz)
    ]
    _ejecutar_cmd(cmd_ia)

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
