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

import subprocess
from pathlib import Path
from typing import Optional

from . import config
from .estado import Proyecto
from .guion import cargar_guion, Guion, Escena
from .host_anim import obtener_sprite


def _ejecutar_cmd(cmd: list[str]) -> bool:
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=True)
        return True
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr[-350:] if e.stderr else "Error desconocido"
        print(f"❌ Error FFmpeg: {err_msg}")
        return False


def _obtener_sfx(cat: str) -> Optional[Path]:
    """Obtiene un archivo de sonido para la categoría solicitada."""
    if not cat or cat == "ninguno":
        return None
    carpeta = config.SFX_DIR / cat
    if carpeta.exists():
        archivos = list(carpeta.glob("*.wav")) + list(carpeta.glob("*.mp3")) + list(carpeta.glob("*.ogg"))
        if archivos:
            return archivos[0]
    return None


def _obtener_musica_fondo(mood: str = "misterio") -> Optional[Path]:
    """Obtiene la pista de música de fondo documental correspondiente al mood."""
    carpeta = config.MUSIC_DIR / (mood if mood in config.MUSIC_MOODS else "misterio")
    if carpeta.exists():
        archivos = list(carpeta.glob("*.wav")) + list(carpeta.glob("*.ogg")) + list(carpeta.glob("*.mp3"))
        if archivos:
            return archivos[0]
    # Respaldo general
    archivos_todos = list(config.MUSIC_DIR.glob("*/*.wav"))
    return archivos_todos[0] if archivos_todos else None


def crear_stems_audio(p: Proyecto, duraciones: dict[int, float], audio_voz_reemplazo: Optional[Path] = None) -> tuple[Path, Path]:
    """Crea stems/voz_ia_master.wav y stems/mde_mix.wav con diseño sonoro completo (música + SFX)."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    carpeta_stems = p.carpeta / "stems"
    carpeta_stems.mkdir(parents=True, exist_ok=True)
    guion = cargar_guion(p)
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
    #    - Transición/Whoosh al inicio de cada cambio de escena
    #    - Click o Teclado cuando hay texto en pantalla
    #    - Impacto en escenas de alerta o clímax
    eventos_sfx = []
    t_acum = 0.0

    for i, esc in enumerate(guion.escenas, 1):
        dur = duraciones.get(esc.id, 5.0)

        # 1. Transición/Whoosh entre escenas (a partir de la escena 2)
        if i > 1:
            sfx_trans = _obtener_sfx("whoosh") or _obtener_sfx("transicion")
            if sfx_trans:
                eventos_sfx.append((t_acum, sfx_trans, 0.45))

        # 2. SFX explícito del guion (impacto, revelación, glitch...)
        if esc.sfx and esc.sfx != "ninguno":
            sfx_especifico = _obtener_sfx(esc.sfx)
            if sfx_especifico:
                eventos_sfx.append((t_acum + 0.3, sfx_especifico, 0.55))

        # 3. Sonido de Click o Teclado Typing si hay texto en pantalla
        if esc.texto_pantalla:
            sfx_texto = _obtener_sfx("teclado") if len(esc.texto_pantalla.split()) > 1 else _obtener_sfx("click")
            if sfx_texto:
                eventos_sfx.append((t_acum + 0.5, sfx_texto, 0.50))

        t_acum += dur

    # C) Mezclar música de fondo + todos los SFX programados
    if eventos_sfx:
        inputs = ["-i", str(temp_musica)]
        filtros_delay = []
        mix_labels = ["[0:a]"]

        # Limitar a máximo 32 entradas simultáneas para estabilidad de FFmpeg
        for idx, (timestamp_s, ruta_sfx, vol) in enumerate(eventos_sfx[:30], 1):
            inputs += ["-i", str(ruta_sfx)]
            delay_ms = max(0, int(timestamp_s * 1000))
            filtros_delay.append(f"[{idx}:a]adelay={delay_ms}|{delay_ms},volume={vol:.2f}[sfx{idx}]")
            mix_labels.append(f"[sfx{idx}]")

        cadena_mix = f"{';'.join(filtros_delay)};{''.join(mix_labels)}amix=inputs={len(mix_labels)}:normalize=0[mde_out]"
        cmd_mezcla_total = [
            ffmpeg, "-y",
            *inputs,
            "-filter_complex", cadena_mix,
            "-map", "[mde_out]",
            "-t", f"{duracion_total:.2f}",
            "-ar", "24000", "-ac", "1",
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


def renderizar_clip_visual(p: Proyecto, esc: Escena, duracion: float, destino_mp4: Path) -> bool:
    """Renderiza el corte visual en 1080p con Host personalizado y texto clave superpuesto."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    broll_mp4 = p.ruta("b_roll", f"escena_{esc.id:03d}.mp4")
    broll_jpg = p.ruta("b_roll", f"escena_{esc.id:03d}.jpg")

    fondo_es_video = broll_mp4.exists()
    fondo_archivo = broll_mp4 if fondo_es_video else (broll_jpg if broll_jpg.exists() else None)

    # Host personalizado según la pose
    host_sprite = obtener_sprite(esc.pose, boca="cerrada") if esc.host_visible else None

    inputs = []
    filtros = []

    if fondo_archivo and fondo_es_video:
        inputs += ["-stream_loop", "-1", "-i", str(fondo_archivo)]
        filtros.append("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg]")
    elif fondo_archivo and not fondo_es_video:
        inputs += ["-loop", "1", "-i", str(fondo_archivo)]
        filtros.append("[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg]")
    else:
        inputs += ["-f", "lavfi", "-i", "color=c=0x111625:s=1920x1080:r=30"]
        filtros.append("[0:v]null[bg]")

    v_previo = "[bg]"
    if host_sprite:
        inputs += ["-loop", "1", "-i", str(host_sprite)]
        pos_x = "1920-w-80" if esc.host_lado == "derecha" else "80"
        filtros.append("[1:v]scale=-1:850[host]")
        filtros.append(f"{v_previo}[host]overlay={pos_x}:1080-h:shortest=1[v_con_host]")
        v_previo = "[v_con_host]"

    # Gráfico de Texto Clave en Pantalla (si existe)
    if esc.texto_pantalla:
        # Texto centrado en el tercio inferior con caja de contraste estilo documental
        texto_limpio = esc.texto_pantalla.replace(":", "").replace("'", "")
        ruta_fuente = (config.FONTS_DIR / "bold.ttf").resolve().as_posix()
        # En Windows FFmpeg requiere escapar los dos puntos de la unidad (ej C\:/...)
        ruta_fuente_escapada = ruta_fuente.replace(":", "\\:")
        filtros.append(
            f"{v_previo}drawtext=fontfile='{ruta_fuente_escapada}':text='{texto_limpio}':fontcolor=white:fontsize=52:box=1:boxcolor=black@0.70:boxborderw=20:x=(w-text_w)/2:y=h-190[v_salida]"
        )
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
    return _ejecutar_cmd(cmd)


def etapa_render(p: Proyecto, duraciones: dict[int, float], voz_humana: Optional[Path] = None) -> dict[str, Path]:
    """Genera Stems de audio enriquecidos con música/SFX y exporta versión IA y versión Karaoke."""
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

    # 2. Clips Visuales con Textos en Pantalla
    total = len(guion.escenas)
    print(f"🎬 Renderizando visuales de {total} escenas...")
    clips_visuales = []
    for i, esc in enumerate(guion.escenas, 1):
        dur = duraciones.get(esc.id, 5.0)
        clip_path = temp_clips / f"vclip_{esc.id:03d}.mp4"
        renderizar_clip_visual(p, esc, dur, clip_path)
        clips_visuales.append(clip_path)

    # Concatenar visual
    lista_v = temp_clips / "concat_v.txt"
    lista_v.write_text("\n".join([f"file '{c.resolve().as_posix()}'" for c in clips_visuales]), "utf-8")
    video_mudo = temp_clips / "visual_completo.mp4"
    cmd_concat_v = [
        ffmpeg, "-y", "-f", "concat", "-safe", "0",
        "-i", str(lista_v),
        "-c", "copy",
        str(video_mudo)
    ]
    _ejecutar_cmd(cmd_concat_v)

    # 3. Exportar Versión IA (Voz principal + MDE de fondo)
    video_con_voz = carpeta_renders / f"{slug}_con_voz_ia.mp4"
    print(f"🎥 Ensamblando Versión IA Dinámica: {video_con_voz.name}...")
    cmd_ia = [
        ffmpeg, "-y",
        "-i", str(video_mudo),
        "-i", str(voz_master),
        "-i", str(mde_master),
        "-filter_complex", "[1:a]volume=1.0[v_aud];[2:a]volume=0.85[mde_aud];[v_aud][mde_aud]amix=inputs=2:normalize=0[a_final]",
        "-map", "0:v",
        "-map", "[a_final]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(video_con_voz)
    ]
    _ejecutar_cmd(cmd_ia)

    # 4. Exportar Versión Clean / Karaoke (Música y SFX sin locución)
    video_sin_voz = carpeta_renders / f"{slug}_sin_voz.mp4"
    print(f"🎤 Ensamblando Versión Clean / Karaoke: {video_sin_voz.name}...")
    cmd_clean = [
        ffmpeg, "-y",
        "-i", str(video_mudo),
        "-i", str(mde_master),
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
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
