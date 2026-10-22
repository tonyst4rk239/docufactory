"""Generador programático de miniaturas cinematográficas de alto CTR (16:9) para Docu Factory.

Diseñado para uso autónomo por bots (Doyou / Megáfono) y usuarios en CLI.
Compatible con Windows y Linux.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from . import config
from .estado import Proyecto


def _buscar_fuente_bold(tamano: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Encuentra una tipografía sans-serif gruesa compatible en Windows y Linux."""
    candidatos = [
        # Windows
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/ariblk.ttf",
        "C:/Windows/Fonts/trebucbd.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
    ]
    for ruta in candidatos:
        p = Path(ruta)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), tamano)
            except Exception:
                continue

    # Búsqueda genérica por nombre en PATH o fuentes instaladas
    for nombre in ("impact.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(nombre, tamano)
        except Exception:
            continue

    return ImageFont.load_default()


def _dibujar_texto_con_borde(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    texto: str,
    font: Any,
    fill: str | tuple[int, int, int],
    borde_color: str | tuple[int, int, int] = (0, 0, 0),
    borde_w: int = 8,
    sombra_offset: tuple[int, int] = (8, 12),
    sombra_color: tuple[int, int, int, int] = (0, 0, 0, 200),
) -> None:
    """Dibuja texto con sombra profunda y borde exterior (stroke) de alto contraste."""
    x, y = xy
    # 1. Sombra de profundidad
    sx, sy = sombra_offset
    for dx in range(-borde_w, borde_w + 1, 2):
        for dy in range(-borde_w, borde_w + 1, 2):
            draw.text((x + sx + dx, y + sy + dy), texto, font=font, fill=(0, 0, 0))

    # 2. Borde perimetral circular (stroke)
    for dx in range(-borde_w, borde_w + 1):
        for dy in range(-borde_w, borde_w + 1):
            if dx * dx + dy * dy <= borde_w * borde_w:
                draw.text((x + dx, y + dy), texto, font=font, fill=borde_color)

    # 3. Relleno principal
    draw.text((x, y), texto, font=font, fill=fill)


def _crear_fondo_control_room(w: int, h: int) -> Image.Image:
    """Genera un fondo cinematográfico estilo sala de control / CCTV con viñeta y luces frías/rojas."""
    img = Image.new("RGBA", (w, h), (10, 14, 22, 255))
    draw = ImageDraw.Draw(img)

    # Gradiente vertical suave
    for y in range(h):
        factor = y / float(h)
        r = int(14 * (1.0 - factor * 0.6))
        g = int(18 * (1.0 - factor * 0.7))
        b = int(32 * (1.0 - factor * 0.5))
        draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

    # Siluetas de monitores y luces de consola en el tercio inferior
    consola_y = int(h * 0.68)
    draw.rectangle([(0, consola_y), (w, h)], fill=(6, 8, 13, 255))

    # Monitores CCTV simulados en fondo
    num_monitores = 5
    m_ancho = int(w / num_monitores) - 20
    m_alto = int(h * 0.22)
    for i in range(num_monitores):
        mx = 15 + i * (m_ancho + 20)
        my = int(h * 0.42)
        # Borde monitor
        draw.rectangle([(mx, my), (mx + m_ancho, my + m_alto)], fill=(15, 20, 30, 255), outline=(30, 42, 60), width=2)
        # Pantalla con estática / cámara
        draw.rectangle([(mx + 4, my + 4), (mx + m_ancho - 4, my + m_alto - 4)], fill=(8, 14, 22, 255))
        # Pequeño led rojo / verde
        led_col = (255, 40, 40) if i % 2 == 0 else (40, 255, 120)
        draw.ellipse([(mx + 8, my + m_alto - 10), (mx + 13, my + m_alto - 5)], fill=led_col)

    # Luz de alerta roja en esquina izquierda
    glow_rojo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_glow = ImageDraw.Draw(glow_rojo)
    draw_glow.ellipse([(-100, -100), (int(w * 0.45), int(h * 0.55))], fill=(220, 20, 20, 80))
    glow_rojo = glow_rojo.filter(ImageFilter.GaussianBlur(80))

    # Luz cyan de monitores en esquina derecha
    glow_cyan = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_cyan = ImageDraw.Draw(glow_cyan)
    draw_cyan.ellipse([(int(w * 0.55), -50), (w + 100, int(h * 0.60))], fill=(20, 180, 240, 65))
    glow_cyan = glow_cyan.filter(ImageFilter.GaussianBlur(90))

    img = Image.alpha_composite(img, glow_rojo)
    img = Image.alpha_composite(img, glow_cyan)

    # Viñeta oscura periférica
    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw_v = ImageDraw.Draw(vignette)
    for step in range(25):
        alpha = int(12 * (step / 25.0) ** 2)
        inset = step * 12
        draw_v.rectangle([(inset, inset), (w - inset, h - inset)], outline=(0, 0, 0, alpha), width=14)
    vignette = vignette.filter(ImageFilter.GaussianBlur(25))
    img = Image.alpha_composite(img, vignette)

    return img.convert("RGB")


def _cargar_fondo(fondo_path: Path | None, w: int, h: int) -> Image.Image:
    """Carga y adapta una imagen de fondo o genera una sintética cinematográfica."""
    if fondo_path and Path(fondo_path).exists() and Path(fondo_path).stat().st_size > 5000:
        try:
            with Image.open(fondo_path) as im:
                im = im.convert("RGB")
                # Escalar recortando al centro (crop 16:9)
                ratio_w = w / float(im.width)
                ratio_h = h / float(im.height)
                scale = max(ratio_w, ratio_h)
                nw, nh = int(im.width * scale), int(im.height * scale)
                im_scaled = im.resize((nw, nh), Image.Resampling.LANCZOS)
                left = (nw - w) // 2
                top = (nh - h) // 2
                bg = im_scaled.crop((left, top, left + w, top + h))

                # Ajuste cinematográfico: contraste alto, brillo controlado
                bg = ImageEnhance.Contrast(bg).enhance(1.30)
                bg = ImageEnhance.Brightness(bg).enhance(0.55)
                return bg
        except Exception as e:
            print(f"⚠️ No se pudo procesar fondo {fondo_path}: {e}")

    return _crear_fondo_control_room(w, h)


def _cargar_y_componer_host(
    canvas: Image.Image,
    host_pose: str = "alerta",
    host_path: Path | None = None,
    posicion: str = "bottom-right",
    flip: bool = False,
    color_borde: tuple[int, int, int] = (34, 211, 238),  # Cyan #22d3ee
) -> None:
    """Inserta el sprite del host con contorno brillante / resplandor en la miniatura."""
    ruta_host = None
    if host_path and Path(host_path).exists():
        ruta_host = Path(host_path)
    else:
        for sufijo in ("_cerrada.png", "_abierta.png"):
            cand = config.HOST_DIR / f"{host_pose}{sufijo}"
            if cand.exists():
                ruta_host = cand
                break
        if not ruta_host:
            cand_alerta = config.HOST_DIR / "alerta_cerrada.png"
            if cand_alerta.exists():
                ruta_host = cand_alerta

    if not ruta_host or not ruta_host.exists():
        return

    try:
        with Image.open(ruta_host) as h_im:
            h_im = h_im.convert("RGBA")
            if flip:
                h_im = h_im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

            # Escalar a ~88% de la altura del canvas
            h_h = int(canvas.height * 0.88)
            h_w = int(h_im.width * (h_h / float(h_im.height)))
            h_scaled = h_im.resize((h_w, h_h), Image.Resampling.LANCZOS)

            # Generar silueta brillante (Glow)
            glow_pad = 40
            glow_img = Image.new("RGBA", (h_w + glow_pad * 2, h_h + glow_pad * 2), (0, 0, 0, 0))
            glow_img.paste(h_scaled, (glow_pad, glow_pad), h_scaled)

            # Extraer canal alfa y aplicar desenfoque gaussiano
            alpha = glow_img.split()[3]
            glow_mask_suave = alpha.filter(ImageFilter.GaussianBlur(16))
            glow_mask_borde = alpha.filter(ImageFilter.GaussianBlur(4))

            # Capas de color de resplandor
            resplandor_color = Image.new("RGBA", glow_img.size, (*color_borde, 230))
            borde_solido = Image.new("RGBA", glow_img.size, (255, 255, 255, 240))

            # Posición en el canvas
            if posicion == "bottom-right":
                pos_x = canvas.width - h_w + int(canvas.width * 0.02)
            elif posicion == "bottom-left":
                pos_x = -int(canvas.width * 0.02)
            else:
                pos_x = int((canvas.width - h_w) / 2)
            pos_y = canvas.height - h_h + int(canvas.height * 0.02)

            # Pegar resplandor
            canvas_rgba = canvas.convert("RGBA")
            canvas_rgba.paste(resplandor_color, (pos_x - glow_pad, pos_y - glow_pad), glow_mask_suave)
            canvas_rgba.paste(borde_solido, (pos_x - glow_pad, pos_y - glow_pad), glow_mask_borde)
            canvas_rgba.paste(h_scaled, (pos_x, pos_y), h_scaled)

            canvas.paste(canvas_rgba.convert("RGB"))
    except Exception as e:
        print(f"⚠️ Error componiendo host en miniatura: {e}")


def generar_miniatura(
    p: Proyecto | None = None,
    titulo: str = "¡FUE UN FRAUDE!",
    subtitulo: str = "DOCUMENTAL DE INVESTIGACIÓN",
    host_pose: str = "alerta",
    fondo_path: Path | None = None,
    salida_path: Path | None = None,
    stamp_text: str = "CONFIDENCIAL",
    timecode: str = "00:43:18 [CAM 04]",
    color_titulo: str = "#FFE600",
    color_borde_host: str = "cyan",
    resolucion: str = "1080p",
) -> Path:
    """Genera una miniatura cinematográfica 16:9 con estética de documental de misterio y alto CTR."""
    w = 1920 if resolucion == "1080p" else 1280
    h = 1080 if resolucion == "1080p" else 720

    # 1. Cargar fondo
    img = _cargar_fondo(fondo_path, w, h)

    # 2. Host
    color_borde_rgb = {
        "cyan": (34, 211, 238),
        "yellow": (255, 230, 0),
        "white": (255, 255, 255),
        "red": (239, 68, 68),
    }.get(color_borde_host.lower(), (34, 211, 238))

    _cargar_y_componer_host(
        img,
        host_pose=host_pose,
        posicion="bottom-right",
        flip=False,
        color_borde=color_borde_rgb,
    )

    # 3. Capa de Texto y Badges
    draw = ImageDraw.Draw(img)

    # --- Badge REC (Top Left) ---
    font_badge = _buscar_fuente_bold(int(h * 0.038))
    rec_texto = f"REC  {timecode}"
    rec_box_x = int(w * 0.04)
    rec_box_y = int(h * 0.06)
    rec_pad_x = 18
    rec_pad_y = 10

    bbox_rec = font_badge.getbbox(rec_texto)
    rec_w = (bbox_rec[2] - bbox_rec[0]) + rec_pad_x * 2 + 25
    rec_h = (bbox_rec[3] - bbox_rec[1]) + rec_pad_y * 2

    # Píldora translúcida negra
    overlay_rec = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d_rec = ImageDraw.Draw(overlay_rec)
    d_rec.rounded_rectangle(
        [(rec_box_x, rec_box_y), (rec_box_x + rec_w, rec_box_y + rec_h)],
        radius=12,
        fill=(10, 12, 18, 210),
        outline=(239, 68, 68, 180),
        width=2,
    )
    # Punto rojo parpadeante
    d_rec.ellipse(
        [(rec_box_x + 16, rec_box_y + int(rec_h / 2) - 7), (rec_box_x + 30, rec_box_y + int(rec_h / 2) + 7)],
        fill=(255, 30, 30, 255),
    )
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay_rec).convert("RGB"))
    draw = ImageDraw.Draw(img)
    draw.text((rec_box_x + 38, rec_box_y + rec_pad_y - 2), rec_texto, font=font_badge, fill=(245, 245, 245))

    # --- Texto Primario Viral (Grande, Amarillo, Rotado) ---
    font_tam_titulo = int(h * 0.155)  # ~165px en 1080p
    font_titulo = _buscar_fuente_bold(font_tam_titulo)

    # Separar en máximo 2 líneas si es muy largo
    palabras = titulo.strip().split()
    lineas_titulo = []
    if len(palabras) > 3:
        mitad = len(palabras) // 2
        lineas_titulo.append(" ".join(palabras[:mitad]))
        lineas_titulo.append(" ".join(palabras[mitad:]))
    else:
        lineas_titulo.append(titulo.strip())

    start_y = int(h * 0.18)
    for idx_l, linea in enumerate(lineas_titulo):
        pos_y = start_y + idx_l * int(font_tam_titulo * 1.08)
        pos_x = int(w * 0.04)
        _dibujar_texto_con_borde(
            draw,
            (pos_x, pos_y),
            linea.upper(),
            font_titulo,
            fill=color_titulo,
            borde_color=(0, 0, 0),
            borde_w=max(8, int(h * 0.016)),
            sombra_offset=(8, 14),
        )

    # --- Sello CONFIDENCIAL / TOP SECRET ---
    if stamp_text:
        font_stamp = _buscar_fuente_bold(int(h * 0.045))
        stamp_bbox = font_stamp.getbbox(stamp_text)
        st_w = (stamp_bbox[2] - stamp_bbox[0]) + 28
        st_h = (stamp_bbox[3] - stamp_bbox[1]) + 16
        st_x = int(w * 0.04)
        st_y = start_y + len(lineas_titulo) * int(font_tam_titulo * 1.08) + 15

        # Sello rojo angulado
        stamp_img = Image.new("RGBA", (st_w + 20, st_h + 20), (0, 0, 0, 0))
        d_stamp = ImageDraw.Draw(stamp_img)
        d_stamp.rounded_rectangle([(10, 10), (10 + st_w, 10 + st_h)], radius=8, outline=(239, 68, 68, 255), width=4)
        d_stamp.text((24, 18), stamp_text.upper(), font=font_stamp, fill=(239, 68, 68, 255))
        stamp_rot = stamp_img.rotate(6, resample=Image.Resampling.BICUBIC, expand=True)

        img_rgba = img.convert("RGBA")
        img_rgba.paste(stamp_rot, (st_x, st_y), stamp_rot)
        img = img_rgba.convert("RGB")
        draw = ImageDraw.Draw(img)

    # --- Banner Subtítulo Inferior ---
    if subtitulo:
        font_sub = _buscar_fuente_bold(int(h * 0.046))
        sub_y = int(h * 0.88)
        sub_x = int(w * 0.04)
        # Barra de fondo negra con acento rojo
        sub_bbox = font_sub.getbbox(subtitulo)
        sub_w = (sub_bbox[2] - sub_bbox[0]) + 30
        sub_h = (sub_bbox[3] - sub_bbox[1]) + 16

        overlay_sub = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d_sub = ImageDraw.Draw(overlay_sub)
        d_sub.rectangle([(sub_x, sub_y), (sub_x + sub_w, sub_y + sub_h)], fill=(12, 14, 20, 230))
        d_sub.line([(sub_x, sub_y), (sub_x + sub_w, sub_y)], fill=(239, 68, 68, 255), width=3)
        img = Image.alpha_composite(img.convert("RGBA"), overlay_sub).convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.text((sub_x + 15, sub_y + 8), subtitulo.upper(), font=font_sub, fill=(255, 255, 255))

    # 4. Guardar archivo
    if salida_path is None:
        if p is not None:
            carpeta_pub = p.ruta("publicacion")
            carpeta_pub.mkdir(parents=True, exist_ok=True)
            salida_path = carpeta_pub / f"miniatura_{resolucion}.png"
        else:
            salida_path = config.RAIZ / f"miniatura_{resolucion}.png"

    salida_path = Path(salida_path)
    salida_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(salida_path), format="PNG", quality=95)
    return salida_path


def generar_miniatura_proyecto(
    p: Proyecto,
    titulo_custom: str | None = None,
    pose_custom: str | None = None,
    fondo_custom: Path | None = None,
) -> dict[str, Path]:
    """Genera las miniaturas oficiales de un proyecto en 1080p y 720p listas para YouTube."""
    from .guion import cargar_guion

    titulo = titulo_custom
    if not titulo:
        try:
            g = cargar_guion(p)
            yt_meta = getattr(g, "youtube_metadata", None)
            if yt_meta and yt_meta.titulos:
                titulo = yt_meta.titulos[0]
            elif g.titulo_trabajo:
                titulo = g.titulo_trabajo
        except Exception:
            pass
    if not titulo:
        titulo = p.tema

    # Acortar para miniatura si es muy largo
    titulo_miniatura = titulo
    if len(titulo_miniatura) > 32 and ":" in titulo_miniatura:
        titulo_miniatura = titulo_miniatura.split(":")[-1].strip()

    # Buscar mejor fondo de B-roll si no se especificó uno
    fondo = fondo_custom
    if not fondo:
        # Probar cuadros de revisión de escena 1 o fondo AI
        cand_rev = p.ruta("b_roll", "revision", "escena_001_mitad.jpg")
        if cand_rev.exists():
            fondo = cand_rev
        else:
            cand_broll = p.ruta("b_roll", "escena_001.mp4")
            if cand_broll.exists():
                fondo = cand_broll

    pose = pose_custom or "alerta"
    carpeta_pub = p.ruta("publicacion")
    carpeta_pub.mkdir(parents=True, exist_ok=True)

    ruta_1080 = generar_miniatura(
        p=p,
        titulo=titulo_miniatura,
        host_pose=pose,
        fondo_path=fondo,
        salida_path=carpeta_pub / "miniatura_1080p.png",
        resolucion="1080p",
    )

    ruta_720 = generar_miniatura(
        p=p,
        titulo=titulo_miniatura,
        host_pose=pose,
        fondo_path=fondo,
        salida_path=carpeta_pub / "miniatura_720p.png",
        resolucion="720p",
    )

    # Exportar también archivo de metadatos de miniatura para el bot
    meta = {
        "slug": p.datos.get("slug"),
        "tema": p.tema,
        "titulo_miniatura": titulo_miniatura,
        "host_pose": pose,
        "resoluciones": {
            "1080p": str(ruta_1080.relative_to(config.RAIZ).as_posix()),
            "720p": str(ruta_720.relative_to(config.RAIZ).as_posix()),
        },
    }
    p.ruta("publicacion", "miniatura.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"1080p": ruta_1080, "720p": ruta_720}
