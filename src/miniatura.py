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
        str(config.ASSETS / "fonts" / "bold.ttf"),
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
            # Poses alias/fallback (p. ej. "alerta" no existe como sprite)
            for pose_alt in ("sorprendido", "senalando", "explicando", "pensativo"):
                cand_alt = config.HOST_DIR / f"{pose_alt}_cerrada.png"
                if cand_alt.exists():
                    ruta_host = cand_alt
                    break

    if not ruta_host or not ruta_host.exists():
        return

    try:
        with Image.open(ruta_host) as h_im:
            h_im = h_im.convert("RGBA")
            bbox_alpha = h_im.split()[3].getbbox()
            if bbox_alpha:
                h_im = h_im.crop(bbox_alpha)  # quitar margen transparente
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

    # Ajustar a 2 líneas máx. y al ancho libre (lado izquierdo, sin tapar al host)
    ancho_max = int(w * 0.50)
    palabras = titulo.strip().upper().split()

    def _ancho(txt: str, f: Any) -> int:
        b = f.getbbox(txt)
        return b[2] - b[0]

    if len(palabras) > 1 and _ancho(" ".join(palabras), font_titulo) > ancho_max:
        mejor = None
        for corte in range(1, len(palabras)):
            l1, l2 = " ".join(palabras[:corte]), " ".join(palabras[corte:])
            m = max(_ancho(l1, font_titulo), _ancho(l2, font_titulo))
            if mejor is None or m < mejor[0]:
                mejor = (m, [l1, l2])
        lineas_titulo = mejor[1]
    else:
        lineas_titulo = [" ".join(palabras)]
    while font_tam_titulo > 40 and max(_ancho(l, font_titulo) for l in lineas_titulo) > ancho_max:
        font_tam_titulo = int(font_tam_titulo * 0.92)
        font_titulo = _buscar_fuente_bold(font_tam_titulo)

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


# =====================================================================================
# Motor de miniaturas VARIADAS (layouts, paletas, fuentes, sellos y poses por tono)
# =====================================================================================
import hashlib
import random

LAYOUTS = ("avatar_derecha", "avatar_izquierda", "avatar_centro", "sin_avatar")

FAMILIAS_FUENTE: dict[str, list[str]] = {
    "impacto": [str(config.ASSETS / "fonts" / "bold.ttf"), "C:/Windows/Fonts/impact.ttf",
                "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "condensada": ["C:/Windows/Fonts/ARIALNB.TTF", "C:/Windows/Fonts/bahnschrift.ttf",
                   "/usr/share/fonts/opentype/urw-base35/NimbusSansNarrow-Bold.otf",
                   "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
    "serif": ["C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/timesbd.ttf",
              "/usr/share/fonts/opentype/urw-base35/C059-Bold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"],
    "geometrica": ["C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                   "/usr/share/fonts/opentype/urw-base35/URWGothic-Demi.otf",
                   "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
}

# Paletas: titulo, acento (2ª palabra/linea), borde, glow host, tinte de fondo (rgb, fuerza), saturación fondo
PALETAS: dict[str, dict[str, Any]] = {
    "amarillo_noche": {"titulo": (255, 222, 0), "acento": (255, 255, 255), "borde": (0, 0, 0), "glow": (34, 211, 238), "tinte": ((10, 40, 30), 0.35), "sat": 0.7},
    "blanco_rojo": {"titulo": (255, 255, 255), "acento": (255, 45, 45), "borde": (0, 0, 0), "glow": (255, 60, 60), "tinte": ((60, 0, 0), 0.30), "sat": 1.1},
    "rojo_fuego": {"titulo": (255, 70, 40), "acento": (255, 230, 0), "borde": (0, 0, 0), "glow": (255, 140, 0), "tinte": ((70, 20, 0), 0.25), "sat": 1.25},
    "cian_frio": {"titulo": (120, 240, 255), "acento": (255, 255, 255), "borde": (0, 10, 25), "glow": (80, 200, 255), "tinte": ((0, 25, 55), 0.35), "sat": 0.9},
    "verde_cctv": {"titulo": (120, 255, 120), "acento": (255, 255, 255), "borde": (0, 0, 0), "glow": (60, 255, 120), "tinte": ((0, 45, 10), 0.45), "sat": 0.5},
    "rosa_pop": {"titulo": (255, 90, 200), "acento": (255, 240, 0), "borde": (40, 0, 60), "glow": (255, 120, 220), "tinte": ((70, 0, 60), 0.18), "sat": 1.35},
    "dorado_epico": {"titulo": (255, 200, 60), "acento": (255, 255, 255), "borde": (20, 10, 0), "glow": (255, 170, 40), "tinte": ((0, 40, 60), 0.25), "sat": 1.15},
    "sangre": {"titulo": (230, 20, 20), "acento": (255, 255, 255), "borde": (0, 0, 0), "glow": (200, 0, 0), "tinte": ((30, 0, 0), 0.45), "sat": 0.55},
    "blanco_azul": {"titulo": (255, 255, 255), "acento": (90, 190, 255), "borde": (0, 0, 0), "glow": (90, 190, 255), "tinte": ((0, 20, 50), 0.25), "sat": 1.0},
}

ESTILO_POR_TONO: dict[str, dict[str, list[str]]] = {
    "misterio": {"paletas": ["amarillo_noche", "verde_cctv", "cian_frio"], "sellos": ["REC", "CONFIDENCIAL", ""],
                 "poses": ["sorprendido", "pensativo", "senalando", "duda"], "fuentes": ["impacto", "condensada"]},
    "terror": {"paletas": ["sangre", "verde_cctv", "blanco_rojo"], "sellos": ["REC", "CONFIDENCIAL", ""],
               "poses": ["sorprendido", "duda", "senalando"], "fuentes": ["impacto", "serif", "condensada"]},
    "polemica": {"paletas": ["blanco_rojo", "rojo_fuego", "amarillo_noche"], "sellos": ["POLÉMICA", "EXCLUSIVA", ""],
                 "poses": ["esceptico", "senalando", "sorprendido", "duda"], "fuentes": ["impacto", "geometrica", "condensada"]},
    "investigacion": {"paletas": ["blanco_azul", "cian_frio", "amarillo_noche"], "sellos": ["CONFIDENCIAL", "EXCLUSIVA", ""],
                      "poses": ["explicando", "pensativo", "senalando"], "fuentes": ["condensada", "geometrica", "serif"]},
    "humor": {"paletas": ["rosa_pop", "rojo_fuego", "amarillo_noche"], "sellos": ["", "EXCLUSIVA"],
              "poses": ["aprobando", "sorprendido", "esceptico", "dinero"], "fuentes": ["geometrica", "impacto"]},
    "epico": {"paletas": ["dorado_epico", "blanco_azul", "rojo_fuego"], "sellos": ["", "EXCLUSIVA"],
              "poses": ["senalando", "aprobando", "explicando"], "fuentes": ["serif", "impacto", "geometrica"]},
    "drama": {"paletas": ["blanco_rojo", "dorado_epico", "cian_frio"], "sellos": ["", "EXCLUSIVA", "POLÉMICA"],
              "poses": ["duda", "pensativo", "esceptico"], "fuentes": ["serif", "condensada"]},
    "curiosidad": {"paletas": ["amarillo_noche", "blanco_azul", "rosa_pop"], "sellos": ["", "EXCLUSIVA"],
                   "poses": ["pensativo", "sorprendido", "explicando", "duda"], "fuentes": ["geometrica", "impacto", "condensada"]},
}

SELLOS_ALIAS = {"ninguno": "", "none": "", "no": "", "polemica": "POLÉMICA"}
HISTORIAL_MINIATURAS = config.RAIZ / "proyectos" / "_miniaturas_historial.json"


def _fuente_familia(familia: str, tamano: int) -> Any:
    for ruta in FAMILIAS_FUENTE.get(familia, []):
        if Path(ruta).exists():
            try:
                return ImageFont.truetype(ruta, tamano)
            except Exception:
                continue
    return _buscar_fuente_bold(tamano)


def poses_disponibles() -> list[str]:
    return sorted({f.name.rsplit("_", 1)[0] for f in config.HOST_DIR.glob("*_cerrada.png")})


def _leer_historial() -> list[dict]:
    try:
        datos = json.loads(HISTORIAL_MINIATURAS.read_text(encoding="utf-8"))
        return datos if isinstance(datos, list) else []
    except Exception:
        return []


def _guardar_historial(entrada: dict) -> None:
    hist = [h for h in _leer_historial() if h.get("slug") != entrada.get("slug")]
    hist.append(entrada)
    try:
        HISTORIAL_MINIATURAS.parent.mkdir(parents=True, exist_ok=True)
        HISTORIAL_MINIATURAS.write_text(json.dumps(hist[-30:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ No se pudo guardar historial de miniaturas: {e}")


def elegir_estilo_miniatura(
    semilla: str,
    tono: str = "misterio",
    usar_avatar: bool = True,
    overrides: Optional[dict] = None,
    evitar: Optional[dict] = None,
) -> dict[str, Any]:
    """Elige layout/paleta/fuente/sello/pose de forma determinista a partir de la semilla (slug) y el tono,
    evitando repetir el layout+posición de título de `evitar` (la miniatura anterior)."""
    ov = {k: v for k, v in (overrides or {}).items() if v not in (None, "")}
    tono = tono if tono in ESTILO_POR_TONO else "misterio"
    est = ESTILO_POR_TONO[tono]
    rng = random.Random(int(hashlib.md5(f"{semilla}|{tono}".encode("utf-8")).hexdigest()[:12], 16))

    layouts = list(LAYOUTS) if usar_avatar else ["sin_avatar"]
    if not usar_avatar:
        ov.pop("layout", None)
    combos = []
    for lay in layouts:
        pos_opts = {"avatar_derecha": ["arriba", "abajo", "centro"], "avatar_izquierda": ["arriba", "abajo", "centro"],
                    "avatar_centro": ["arriba"],
                    "sin_avatar": ["abajo"] if usar_avatar else ["arriba", "abajo", "centro"]}[lay]
        for pos in pos_opts:
            combos.append((lay, pos))
    rng.shuffle(combos)
    if ov.get("layout"):
        combos = [c for c in combos if c[0] == ov["layout"]] or combos
    ev = evitar or {}
    elegido = next((c for c in combos if not (c[0] == ev.get("layout") and c[1] == ev.get("posicion_titulo"))), combos[0])
    if len(combos) > 1 and elegido[0] == ev.get("layout"):
        otro = next((c for c in combos if c[0] != ev.get("layout")), None)
        if otro and not ov.get("layout"):
            elegido = otro

    def _pick(lista: list, previo: Any) -> Any:
        cand = [x for x in lista if x != previo] or lista
        return rng.choice(cand)

    poses_ok = [p for p in est["poses"] if p in poses_disponibles()] or poses_disponibles() or ["sorprendido"]
    sello = ov.get("sello")
    if sello is None:
        sello = _pick(est["sellos"], ev.get("sello"))
    sello = SELLOS_ALIAS.get(str(sello).strip().lower(), str(sello).upper())
    return {
        "tono": tono,
        "layout": elegido[0],
        "posicion_titulo": elegido[1],
        "lineas": rng.choice({"avatar_centro": [1, 2], "sin_avatar": [1, 2, 2, 3]}.get(elegido[0], [2, 3, 3])),
        "paleta": _pick(est["paletas"], ev.get("paleta")),
        "fuente": _pick(est["fuentes"], ev.get("fuente")),
        "sello": sello,
        "pose": ov.get("pose") or _pick(poses_ok, ev.get("pose")),
        "flip": rng.random() < 0.5,
        "inclinacion": rng.choice([0, 0, -3, 3]),
    }


def _partir_lineas(texto: str, n: int) -> list[str]:
    palabras = texto.split()
    n = max(1, min(n, len(palabras), 3))
    if n == 1:
        return [texto]
    total = sum(len(w) + 1 for w in palabras)
    lineas, actual, acum = [], [], 0
    for idx, w in enumerate(palabras):
        restantes = len(palabras) - idx
        if actual and len(lineas) < n - 1 and (acum + len(w) / 2 > total * (len(lineas) + 1) / n or restantes < n - len(lineas)):
            lineas.append(" ".join(actual)); actual = []
        actual.append(w); acum += len(w) + 1
    if actual:
        lineas.append(" ".join(actual))
    return lineas


def _ruta_sprite(pose: str) -> Optional[Path]:
    for pz in (pose, "sorprendido", "senalando", "explicando"):
        for suf in ("_abierta.png", "_cerrada.png"):
            c = config.HOST_DIR / f"{pz}{suf}"
            if c.exists():
                return c
    return None


def generar_miniatura_variada(
    titulo: str,
    estilo: dict[str, Any],
    subtitulo: str = "",
    fondo_path: Optional[Path] = None,
    salida_path: Optional[Path] = None,
    resolucion: str = "1080p",
) -> Path:
    """Compone una miniatura según `estilo` (ver elegir_estilo_miniatura). El texto nunca pisa la caja del avatar."""
    w, h = (1920, 1080) if resolucion == "1080p" else (1280, 720)
    pal = PALETAS.get(estilo.get("paleta"), PALETAS["amarillo_noche"])

    # --- Fondo con tratamiento por paleta ---
    fondo = None
    if fondo_path and Path(fondo_path).exists() and Path(fondo_path).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        try:
            with Image.open(fondo_path) as im:
                im = im.convert("RGB")
                sc = max(w / im.width, h / im.height)
                im = im.resize((int(im.width * sc) + 1, int(im.height * sc) + 1), Image.Resampling.LANCZOS)
                l, t = (im.width - w) // 2, (im.height - h) // 2
                fondo = im.crop((l, t, l + w, t + h))
        except Exception as e:
            print(f"⚠️ Fondo no usable ({e})")
    if fondo is None:
        fondo = _crear_fondo_control_room(w, h)
    fondo = ImageEnhance.Color(fondo).enhance(pal["sat"])
    fondo = ImageEnhance.Contrast(fondo).enhance(1.25)
    fondo = ImageEnhance.Brightness(fondo).enhance(0.62)
    tinte_rgb, fuerza = pal["tinte"]
    fondo = Image.blend(fondo, Image.new("RGB", (w, h), tinte_rgb), fuerza)
    img = fondo.convert("RGBA")

    layout = estilo.get("layout", "avatar_derecha")
    margen = int(w * 0.035)

    # --- Avatar: caja reservada ---
    caja_host = None
    if layout != "sin_avatar":
        ruta = _ruta_sprite(estilo.get("pose", "sorprendido"))
        if ruta:
            with Image.open(ruta) as hi:
                hi = hi.convert("RGBA")
                bb = hi.split()[3].getbbox()
                if bb:
                    hi = hi.crop(bb)
                if estilo.get("flip"):
                    hi = hi.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                alto = int(h * (0.54 if layout == "avatar_centro" else 0.90))
                ancho = int(hi.width * alto / hi.height)
                ancho_max = int(w * (0.42 if layout == "avatar_centro" else 0.44))
                if ancho > ancho_max:
                    alto = int(alto * ancho_max / ancho); ancho = ancho_max
                hi = hi.resize((ancho, alto), Image.Resampling.LANCZOS)
                x = {"avatar_derecha": w - ancho - margen // 2, "avatar_izquierda": margen // 2}.get(layout, (w - ancho) // 2)
                y = h - alto
                pad = 36
                capa = Image.new("RGBA", (ancho + pad * 2, alto + pad * 2), (0, 0, 0, 0))
                capa.paste(hi, (pad, pad), hi)
                a = capa.split()[3]
                img.paste(Image.new("RGBA", capa.size, (*pal["glow"], 220)), (x - pad, y - pad), a.filter(ImageFilter.GaussianBlur(18)))
                img.paste(Image.new("RGBA", capa.size, (255, 255, 255, 235)), (x - pad, y - pad), a.filter(ImageFilter.GaussianBlur(3)))
                img.alpha_composite(capa, (x - pad, y - pad))
                caja_host = (x - pad // 2, y - pad // 2, x + ancho + pad // 2, h)

    # --- Zona de texto: complemento de la caja del avatar ---
    if layout == "avatar_derecha" and caja_host:
        zona = (margen, margen, caja_host[0] - margen // 2, h - margen)
    elif layout == "avatar_izquierda" and caja_host:
        zona = (caja_host[2] + margen // 2, margen, w - margen, h - margen)
    elif layout == "avatar_centro" and caja_host:
        zona = (margen, margen, w - margen, caja_host[1] - margen // 3)
    else:
        zona = (margen * 2, margen, w - margen * 2, h - margen)
    zx0, zy0, zx1, zy1 = zona
    zw, zh = zx1 - zx0, zy1 - zy0

    # --- Título: ajuste de tamaño a la zona ---
    texto = titulo.upper().strip()
    n_lin = int(estilo.get("lineas", 2))
    if len(texto) > 20:
        n_lin = max(n_lin, 2)
    if len(texto) > 24 and layout in ("avatar_derecha", "avatar_izquierda"):
        n_lin = 3
    lineas = _partir_lineas(texto, n_lin)
    familia = estilo.get("fuente", "impacto")
    alto_sub = int(h * 0.075) if subtitulo else 0
    alto_sello = int(h * (0.07 if layout == "avatar_centro" else 0.09)) if estilo.get("sello") else 0
    zh_titulo = zh - alto_sub - alto_sello
    tam = int(h * 0.26)
    while tam > 30:
        f = _fuente_familia(familia, tam)
        anchos = [f.getbbox(l)[2] - f.getbbox(l)[0] for l in lineas]
        alto_total = int(tam * 1.05) * len(lineas)
        if max(anchos) <= zw - 20 and alto_total <= zh_titulo:
            break
        tam -= 4
    f = _fuente_familia(familia, tam)
    salto = int(tam * 1.05)
    bloque_h = salto * len(lineas) + alto_sello + alto_sub
    pos_v = estilo.get("posicion_titulo", "arriba")
    by = zy0 if pos_v == "arriba" else (zy1 - bloque_h if pos_v == "abajo" else zy0 + (zh - bloque_h) // 2)
    centrar = layout in ("avatar_centro", "sin_avatar")
    if layout == "avatar_izquierda":
        alinear = "der"
    else:
        alinear = "centro" if centrar else "izq"

    capa_txt = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa_txt)
    # franja oscura detrás del bloque para legibilidad
    franja = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(franja).rectangle([zx0 - 10, by - 10, zx1 + 10, by + bloque_h + 10], fill=(0, 0, 0, 110))
    img.alpha_composite(franja.filter(ImageFilter.GaussianBlur(30)))

    y = by
    if estilo.get("sello"):
        fs = _fuente_familia("geometrica", int(alto_sello * 0.6))
        st = estilo["sello"]
        bb = fs.getbbox(st)
        sw, sh = bb[2] - bb[0] + 40, int(alto_sello * 0.85)
        sx = {"izq": zx0, "der": zx1 - sw, "centro": zx0 + (zw - sw) // 2}[alinear]
        col = (239, 40, 40) if st in ("REC", "CONFIDENCIAL", "POLÉMICA") else (255, 200, 0)
        d.rounded_rectangle([sx, y, sx + sw, y + sh], radius=10, fill=(*col, 235))
        if st == "REC":
            d.ellipse([sx + 10, y + sh // 2 - 9, sx + 28, y + sh // 2 + 9], fill=(255, 255, 255))
            d.text((sx + 34, y + (sh - (bb[3] - bb[1])) // 2 - bb[1]), st, font=fs, fill=(255, 255, 255))
        else:
            d.text((sx + 20, y + (sh - (bb[3] - bb[1])) // 2 - bb[1]), st, font=fs, fill=(0, 0, 0) if col[1] > 150 else (255, 255, 255))
        y += alto_sello
    for i, l in enumerate(lineas):
        bb = f.getbbox(l)
        lw = bb[2] - bb[0]
        lx = {"izq": zx0, "der": zx1 - lw, "centro": zx0 + (zw - lw) // 2}[alinear] - bb[0]
        col = pal["acento"] if (len(lineas) > 1 and i == len(lineas) - 1) else pal["titulo"]
        d.text((lx + 8, y + 10), l, font=f, fill=(0, 0, 0, 200), stroke_width=max(4, tam // 12), stroke_fill=(0, 0, 0, 200))
        d.text((lx, y), l, font=f, fill=col, stroke_width=max(4, tam // 14), stroke_fill=pal["borde"])
        y += salto
    if subtitulo:
        fsub = _fuente_familia("condensada", int(alto_sub * 0.55))
        sub = subtitulo.upper()
        bb = fsub.getbbox(sub)
        sw = min(bb[2] - bb[0] + 30, zw)
        sx = {"izq": zx0, "der": zx1 - sw, "centro": zx0 + (zw - sw) // 2}[alinear]
        sy = y + int(alto_sub * 0.15)
        d.rectangle([sx, sy, sx + sw, sy + int(alto_sub * 0.75)], fill=(10, 12, 18, 225))
        d.rectangle([sx, sy, sx + 6, sy + int(alto_sub * 0.75)], fill=(*pal["glow"], 255))
        d.text((sx + 16, sy + 6 - bb[1] // 2), sub, font=fsub, fill=(255, 255, 255))

    inc = int(estilo.get("inclinacion", 0))
    if inc:
        # rotar alrededor del centro de la zona; recortar a la zona para no invadir el avatar
        cx, cy = zx0 + zw // 2, by + bloque_h // 2
        capa_txt = capa_txt.rotate(inc, resample=Image.Resampling.BICUBIC, center=(cx, cy))
    if caja_host:
        ImageDraw.Draw(capa_txt).rectangle(caja_host, fill=(0, 0, 0, 0))  # garantía: texto nunca sobre el avatar
    img.alpha_composite(capa_txt)

    salida_path = Path(salida_path or (config.RAIZ / f"miniatura_{resolucion}.png"))
    salida_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(str(salida_path), format="PNG")
    return salida_path


_PALABRAS_DEBILES = {"de", "del", "la", "las", "el", "los", "y", "que", "a", "en", "un", "una", "donde", "con", "por", "para", "este", "esta", "su", "sus", "al"}


def acortar_titulo(t: str, max_chars: int = 40) -> str:
    """Acorta a <= max_chars por palabras, sin terminar en preposición/artículo."""
    t = t.replace("…", " ").strip()
    if len(t) <= max_chars:
        return t
    if ":" in t and len(t.split(":")[-1].strip()) >= 8:
        cola = t.split(":")[-1].strip()
        if len(cola) <= max_chars:
            return cola
    palabras, out = t.split(), []
    for w_ in palabras:
        if len(" ".join(out + [w_])) > max_chars:
            break
        out.append(w_)
    while len(out) > 2 and out[-1].lower().strip(",.;:¿?¡!") in _PALABRAS_DEBILES:
        out.pop()
    return " ".join(out).rstrip(",.;:")


def _frame_de_clip(clip: Path, destino: Path) -> Optional[Path]:
    import subprocess
    try:
        subprocess.run([config.ffmpeg_bin("ffmpeg"), "-y", "-ss", "1.5", "-i", str(clip), "-frames:v", "1", "-q:v", "2", str(destino)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        return destino if destino.exists() and destino.stat().st_size > 15000 else None
    except Exception:
        return None


def _elegir_fondo_proyecto(p: Proyecto, semilla: str) -> Optional[Path]:
    rng0 = random.Random(int(hashlib.md5(("f" + semilla).encode("utf-8")).hexdigest()[:8], 16))
    reales = sorted(p.ruta("b_roll").glob("escena_*_real_*.mp4")) if p.ruta("b_roll").exists() else []
    rng0.shuffle(reales)
    for clip in reales[:4]:
        fr = _frame_de_clip(clip, p.ruta("publicacion", "_fondo_miniatura.jpg"))
        if fr:
            return fr
    rev = p.ruta("b_roll", "revision")
    cands = sorted(rev.glob("escena_*_toma_*.jpg")) or sorted(rev.glob("escena_*_mitad.jpg")) if rev.exists() else []
    cands = [c for c in cands if c.stat().st_size > 15000]
    if not cands:
        return None
    rng = random.Random(int(hashlib.md5(semilla.encode("utf-8")).hexdigest()[:8], 16))
    return rng.choice(cands[: max(1, len(cands) // 2)])  # primera mitad del video: suele ser el gancho


def generar_miniatura_proyecto(
    p: Proyecto,
    titulo_custom: str | None = None,
    pose_custom: str | None = None,
    fondo_custom: Path | None = None,
    subtitulo_custom: str | None = None,
    sello_custom: str | None = None,
    layout_custom: str | None = None,
    tono_custom: str | None = None,
    salida_dir: Path | None = None,
    registrar_historial: bool = True,
) -> dict[str, Path]:
    """Genera las miniaturas 1080p/720p de un proyecto con layout variado según tono, semilla (slug) y la anterior."""
    from .guion import cargar_guion

    g = None
    try:
        g = cargar_guion(p)
    except Exception:
        pass
    mini = (g.miniatura.model_dump() if g is not None and getattr(g, "miniatura", None) else {}) or {}
    tono = tono_custom or (getattr(g, "tono", None) if g else None) or "misterio"
    usar_avatar = bool(getattr(g, "usar_avatar", True)) if g else True
    if p.datos.get("sin_host"):
        usar_avatar = False

    titulo = titulo_custom or mini.get("titulo")
    if not titulo and g is not None:
        yt_meta = getattr(g, "youtube_metadata", None)
        titulo = (yt_meta.titulos[0] if yt_meta and yt_meta.titulos else None) or g.titulo_trabajo
    titulo = titulo or p.tema
    titulo_miniatura = titulo
    if not (titulo_custom or mini.get("titulo")):
        titulo_miniatura = acortar_titulo(titulo_miniatura)

    subtitulo = subtitulo_custom if subtitulo_custom is not None else (mini.get("subtitulo") or "")
    slug = str(p.datos.get("slug") or p.carpeta.name)
    hist = [h for h in _leer_historial() if h.get("slug") != slug]
    previo = hist[-1] if hist else None
    estilo = elegir_estilo_miniatura(
        slug, tono=tono, usar_avatar=usar_avatar,
        overrides={"pose": pose_custom or mini.get("pose"), "sello": sello_custom if sello_custom is not None else mini.get("sello"),
                   "layout": layout_custom or mini.get("layout")},
        evitar=previo,
    )
    fondo = fondo_custom or _elegir_fondo_proyecto(p, slug)

    carpeta_pub = Path(salida_dir) if salida_dir else p.ruta("publicacion")
    carpeta_pub.mkdir(parents=True, exist_ok=True)
    rutas = {}
    for res in ("1080p", "720p"):
        rutas[res] = generar_miniatura_variada(titulo_miniatura, estilo, subtitulo=subtitulo, fondo_path=fondo,
                                               salida_path=carpeta_pub / f"miniatura_{res}.png", resolucion=res)
    meta = {"slug": slug, "tema": p.tema, "titulo_miniatura": titulo_miniatura, "estilo": estilo,
            "fondo": str(fondo) if fondo else None,
            "resoluciones": {k: v.as_posix() for k, v in rutas.items()}}
    (carpeta_pub / "miniatura.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if registrar_historial:
        _guardar_historial({"slug": slug, **{k: estilo[k] for k in ("layout", "posicion_titulo", "paleta", "fuente", "sello", "pose")}})
    return rutas
