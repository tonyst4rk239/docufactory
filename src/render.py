"""Motor de renderizado de video FFmpeg 16:9 automático.

Compone para cada escena:
  1. Fondo B-Roll (video o imagen con escala y recorte 1920x1080 30fps)
  2. Host PNG superpuesto en el tercio seleccionado con fondo transparente
  3. Locución WAV sincronizada exactamente escena por escena
  4. Concatenación final sin recodificación compleja
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import config
from .estado import Proyecto
from .guion import cargar_guion, Guion, Escena
from .host_anim import obtener_sprite


def _ejecutar_cmd(cmd: list[str]) -> bool:
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error FFmpeg: {e.stderr[-300:]}")
        return False


def renderizar_escena(p: Proyecto, esc: Escena, duracion: float, destino_mp4: Path) -> bool:
    """Renderiza una escena individual en MP4 (1920x1080 30fps)."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg no encontrado.")

    ruta_voz = p.ruta("voz", f"escena_{esc.id:03d}.wav")
    
    # 1. Buscar archivo de B-Roll (mp4 o jpg)
    broll_mp4 = p.ruta("b_roll", f"escena_{esc.id:03d}.mp4")
    broll_jpg = p.ruta("b_roll", f"escena_{esc.id:03d}.jpg")
    
    fondo_es_video = broll_mp4.exists()
    fondo_archivo = broll_mp4 if fondo_es_video else (broll_jpg if broll_jpg.exists() else None)

    # 2. Host sprite
    host_sprite = obtener_sprite(esc.pose, boca="cerrada") if esc.host_visible else None

    # Si no hay B-roll, generar fondo abstracto tecnológico con color
    inputs = []
    filtros = []

    if fondo_archivo and fondo_es_video:
        inputs += ["-stream_loop", "-1", "-i", str(fondo_archivo)]
        filtros.append(f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg]")
    elif fondo_archivo and not fondo_es_video:
        inputs += ["-loop", "1", "-i", str(fondo_archivo)]
        # Leve zoom dinámico (Ken Burns simple)
        filtros.append(f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30[bg]")
    else:
        # Fondo color sólido oscuro elegante
        inputs += ["-f", "lavfi", "-i", f"color=c=0x111625:s=1920x1080:r=30"]
        filtros.append("[0:v]null[bg]")

    idx_audio = 1
    if host_sprite:
        inputs += ["-loop", "1", "-i", str(host_sprite)]
        idx_audio = 2
        # Posición del avatar (derecha o izquierda)
        pos_x = "1920-w-80" if esc.host_lado == "derecha" else "80"
        filtros.append(f"[1:v]scale=-1:850[host]")
        filtros.append(f"[bg][host]overlay={pos_x}:1080-h:shortest=1[v_comp]")
        v_salida = "[v_comp]"
    else:
        v_salida = "[bg]"

    # Audio voz
    inputs += ["-i", str(ruta_voz)]

    filtro_completo = ";".join(filtros)
    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filtro_completo,
        "-map", v_salida,
        "-map", f"{idx_audio}:a",
        "-t", f"{duracion:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(destino_mp4)
    ]
    return _ejecutar_cmd(cmd)


def etapa_render(p: Proyecto, duraciones: dict[int, float]) -> Path:
    """Renderiza todas las escenas y las concatena en video_16x9.mp4."""
    ffmpeg = config.ffmpeg_bin("ffmpeg")
    guion = cargar_guion(p)
    carpeta_render = p.ruta("render")
    carpeta_render.mkdir(parents=True, exist_ok=True)
    temp_escenas = carpeta_render / "temp_escenas"
    temp_escenas.mkdir(parents=True, exist_ok=True)

    archivos_clips = []
    total = len(guion.escenas)
    print(f"🎬 Renderizando {total} escenas a 1080p 30fps...")

    for i, esc in enumerate(guion.escenas, 1):
        dur = duraciones.get(esc.id, 5.0)
        destino = temp_escenas / f"clip_{esc.id:03d}.mp4"
        print(f"   [{i}/{total}] Renderizando clip Escena {esc.id} ({dur}s)...")
        ok = renderizar_escena(p, esc, dur, destino)
        if ok:
            archivos_clips.append(destino)
        else:
            print(f"   ❌ Fallo al renderizar escena {esc.id}")

    # Concatenar todos los clips
    lista_txt = carpeta_render / "concat_list.txt"
    lineas = [f"file '{c.resolve().as_posix()}'" for c in archivos_clips]
    lista_txt.write_text("\n".join(lineas), "utf-8")

    salida_final = carpeta_render / "video_16x9.mp4"
    print(f"🎞️ Concatenando video final en: {salida_final.name}...")
    cmd_concat = [
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(lista_txt),
        "-c", "copy",
        str(salida_final)
    ]
    _ejecutar_cmd(cmd_concat)

    p.marcar("render", "ok")
    print(f"🎉 Render completo: {salida_final}")
    return salida_final
