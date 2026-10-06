"""Pipeline de Renderizado con Exportación Dual (IA vs Clean/Karaoke) y Stems de Audio.

Produce:
  1. Stems:
     - stems/voz_ia_master.wav: Pista continua de voz sintética masterizada.
     - stems/mde_mix.wav: Mezcla continua de SFX (transición, click, teclado) y ambiente sin voz.
  2. Renders Duales:
     - renders/{slug}_con_voz_ia.mp4: Video completo con locución IA, B-roll, Host y SFX.
     - renders/{slug}_sin_voz.mp4: Video 'Clean / Karaoke' con Host y SFX/Música para doblaje humano.
  3. Soporte para redoblaje con voz humana (re-sincronización y render final).
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
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error FFmpeg: {e.stderr[-350:]}")
        return False


def _obtener_sfx_escena(sfx_cat: str) -> Optional[Path]:
    """Obtiene archivo de sonido para la categoría solicitada."""
    if sfx_cat == "ninguno":
        return None
    carpeta = config.SFX_DIR / sfx_cat
    if carpeta.exists():
        archivos = list(carpeta.glob("*.wav")) + list(carpeta.glob("*.mp3")) + list(carpeta.glob("*.ogg"))
        if archivos:
            return archivos[0]
    return None


def crear_stems_audio(p: Proyecto, duraciones: dict[int, float], audio_voz_reemplazo: Optional[Path] = None) -> tuple[Path, Path]:
    """Crea stems/voz_ia_master.wav y stems/mde_mix.wav garantizando sincronización exacta."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    carpeta_stems = p.carpeta / "stems"
    carpeta_stems.mkdir(parents=True, exist_ok=True)
    guion = cargar_guion(p)

    # 1. Pista Continua de Voz
    voz_master = carpeta_stems / "voz_ia_master.wav"
    if audio_voz_reemplazo and audio_voz_reemplazo.exists():
        # Copiar y normalizar la voz humana proporcionada
        cmd_norm = [
            ffmpeg, "-y", "-i", str(audio_voz_reemplazo),
            "-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "24000", "-ac", "1",
            str(voz_master)
        ]
        _ejecutar_cmd(cmd_norm)
    else:
        # Concatenar los clips wav de cada escena
        clips_voz = []
        for esc in guion.escenas:
            wav_esc = p.ruta("voz", f"escena_{esc.id:03d}.wav")
            if wav_esc.exists():
                clips_voz.append(wav_esc)
        
        if clips_voz:
            lista_voz = carpeta_stems / "concat_voz.txt"
            lista_voz.write_text("\n".join([f"file '{c.resolve().as_posix()}'" for c in clips_voz]), "utf-8")
            cmd_concat_voz = [
                ffmpeg, "-y", "-f", "concat", "-safe", "0",
                "-i", str(lista_voz),
                "-c:a", "pcm_s16le", str(voz_master)
            ]
            _ejecutar_cmd(cmd_concat_voz)

    # 2. Pista de Música y Efectos de Sonido (MDE Mix)
    mde_master = carpeta_stems / "mde_mix.wav"
    duracion_total = sum(duraciones.values())
    
    # Generar silencio base con la duración exacta
    cmd_silencio = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
        "-t", f"{duracion_total:.2f}",
        "-c:a", "pcm_s16le", str(mde_master)
    ]
    _ejecutar_cmd(cmd_silencio)

    # Superponer efectos de sonido en los timestamps correspondientes
    sfx_entradas = []
    t_acum = 0.0
    for esc in guion.escenas:
        dur = duraciones.get(esc.id, 5.0)
        archivo_sfx = _obtener_sfx_escena(esc.sfx)
        if not archivo_sfx and esc.texto_pantalla:
            # Añadir sonido sutil de click/teclado al aparecer texto
            archivo_sfx = _obtener_sfx_escena("click") or _obtener_sfx_escena("teclado")
            
        if archivo_sfx:
            sfx_entradas.append((t_acum, archivo_sfx))
        t_acum += dur

    if sfx_entradas:
        # Mezclar SFX en la pista MDE
        inputs = ["-i", str(mde_master)]
        filtros_adelay = []
        mix_inputs = ["[0:a]"]
        
        for i, (timestamp_s, ruta_sfx) in enumerate(sfx_entradas, 1):
            inputs += ["-i", str(ruta_sfx)]
            delay_ms = int(timestamp_s * 1000)
            filtros_adelay.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},volume=0.6[sfx{i}]")
            mix_inputs.append(f"[sfx{i}]")
            
        filtro_mix = f"{';'.join(filtros_adelay)};{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:normalize=0[aout]"
        temp_mde = carpeta_stems / "mde_mix_temp.wav"
        cmd_sfx_mix = [
            ffmpeg, "-y",
            *inputs,
            "-filter_complex", filtro_mix,
            "-map", "[aout]",
            "-t", f"{duracion_total:.2f}",
            "-c:a", "pcm_s16le",
            str(temp_mde)
        ]
        if _ejecutar_cmd(cmd_sfx_mix):
            temp_mde.replace(mde_master)

    return voz_master, mde_master


def renderizar_clip_visual(p: Proyecto, esc: Escena, duracion: float, destino_mp4: Path) -> bool:
    """Renderiza el video visual (sin audio definitivo) escalando a 1080p con Host superpuesto."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    broll_mp4 = p.ruta("b_roll", f"escena_{esc.id:03d}.mp4")
    broll_jpg = p.ruta("b_roll", f"escena_{esc.id:03d}.jpg")

    fondo_es_video = broll_mp4.exists()
    fondo_archivo = broll_mp4 if fondo_es_video else (broll_jpg if broll_jpg.exists() else None)

    # Cargar sprite del Host según pose
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

    if host_sprite:
        inputs += ["-loop", "1", "-i", str(host_sprite)]
        pos_x = "1920-w-80" if esc.host_lado == "derecha" else "80"
        filtros.append("[1:v]scale=-1:850[host]")
        filtros.append(f"[bg][host]overlay={pos_x}:1080-h:shortest=1[v_salida]")
    else:
        filtros.append("[bg]null[v_salida]")

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
    """Genera Stems de audio y exporta de forma dual: Con Voz IA y Versión Clean / Karaoke."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    guion = cargar_guion(p)
    
    carpeta_renders = p.carpeta / "renders"
    carpeta_renders.mkdir(parents=True, exist_ok=True)
    temp_clips = carpeta_renders / "temp_visual"
    temp_clips.mkdir(parents=True, exist_ok=True)

    slug = p.datos.get("slug", "video")

    # 1. Generar Stems Independientes
    print("🎧 Generando Stems de Audio (voz_ia_master.wav y mde_mix.wav)...")
    voz_master, mde_master = crear_stems_audio(p, duraciones, audio_voz_reemplazo=voz_humana)

    # 2. Renderizar Clips Visuales
    total = len(guion.escenas)
    print(f"🎬 Renderizando visuales de {total} escenas...")
    clips_visuales = []
    for i, esc in enumerate(guion.escenas, 1):
        dur = duraciones.get(esc.id, 5.0)
        clip_path = temp_clips / f"vclip_{esc.id:03d}.mp4"
        renderizar_clip_visual(p, esc, dur, clip_path)
        clips_visuales.append(clip_path)

    # Concatenar video mudo
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

    # 3. Exportar Video Versión IA (Voz + MDE)
    video_con_voz = carpeta_renders / f"{slug}_con_voz_ia.mp4"
    print(f"🎥 Ensamblando Versión IA: {video_con_voz.name}...")
    cmd_ia = [
        ffmpeg, "-y",
        "-i", str(video_mudo),
        "-i", str(voz_master),
        "-i", str(mde_master),
        "-filter_complex", "[1:a][2:a]amix=inputs=2:weights=1.0 0.4:normalize=0[a_final]",
        "-map", "0:v",
        "-map", "[a_final]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(video_con_voz)
    ]
    _ejecutar_cmd(cmd_ia)

    # 4. Exportar Video Versión Clean / Karaoke (Sólo MDE, sin voz)
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
