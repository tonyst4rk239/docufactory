"""Motor de animación y montaje de sprites del Host (PNGTuber style).

Genera los sprites provisionales transparentes y el filtrado para componer
el host en la capa de video con FFmpeg.
"""
from __future__ import annotations

import re
from pathlib import Path
from PIL import Image, ImageDraw

from . import config

COLORES_POSES = {
    "explicando": (60, 179, 113),
    "pensativo": (147, 112, 219),
    "sorprendido": (220, 20, 60),
    "esceptico": (218, 112, 214),
    "dinero": (46, 139, 87),
    "aprobando": (255, 215, 0),
    "duda": (70, 130, 180),
    "senalando": (30, 144, 255),
}

_PALABRAS_MISTERIO_TERROR = {
    "misterio", "misterios", "terror", "horror", "paranormal", "macabro", "macabros",
    "escalofriante", "escalofriantes", "inquietante", "inquietantes", "crimen", "asesinato",
    "desaparicion", "fantasma", "maldicion", "oscuro", "oscura", "oculto", "siniestro",
}

_PALABRAS_FINANZAS = {
    "dinero", "millon", "millones", "fortuna", "riqueza", "finanzas", "negocio", "negocios",
    "economia", "banco", "estafa", "cripto", "bitcoin", "inversion", "precio", "billonario",
    "millonario", "sueldo", "dolar", "dolares", "empresa", "acciones",
}


_MOODS_SIN_DINERO = {
    "misterio", "terror", "crimen", "tension", "tensión", "horror", "paranormal", "suspenso"
}


def es_mood_oscuro_sin_dinero(mood: str = "", tema: str = "", texto_voz: str = "") -> bool:
    """Indica si el mood o tema pertenece a misterio/terror/crimen/tensión donde la pose 'dinero' está prohibida."""
    m_norm = (mood or "").strip().lower().translate(str.maketrans("áéíóú", "aeiou"))
    if m_norm in _MOODS_SIN_DINERO:
        return True
    contexto_tokens = set(re.findall(r"[a-záéíóúñ]+", f"{tema} {texto_voz}".lower()))
    contexto_limpio = {t.translate(str.maketrans("áéíóú", "aeiou")) for t in contexto_tokens}
    return bool(contexto_limpio & _PALABRAS_MISTERIO_TERROR)


def normalizar_pose(pose: str, mood: str = "misterio", tema: str = "", texto_voz: str = "") -> str:
    """Resuelve alias heredados y valida que la pose sea coherente con el mood y el tema.
    Prohíbe tajantemente 'dinero' en temas/moods de misterio, terror, crimen o tensión."""
    p = (pose or "").strip().lower()
    p = config.POSE_ALIASES.get(p, p)
    if p not in config.POSES:
        p = "explicando"

    m_norm = (mood or "misterio").strip().lower().translate(str.maketrans("áéíóú", "aeiou"))
    mood_canonico = "tension" if m_norm in ("terror", "crimen", "tension", "suspenso") else m_norm
    if mood_canonico not in config.POSES_POR_MOOD:
        mood_canonico = "misterio"

    contexto_tokens = set(re.findall(r"[a-záéíóúñ]+", f"{tema} {texto_voz}".lower()))
    contexto_limpio = {
        t.translate(str.maketrans("áéíóú", "aeiou")) for t in contexto_tokens
    }
    es_tema_misterio = es_mood_oscuro_sin_dinero(mood=mood, tema=tema, texto_voz=texto_voz)
    es_contexto_finanzas = bool(contexto_limpio & _PALABRAS_FINANZAS)

    if p == "dinero":
        if es_tema_misterio or not es_contexto_finanzas:
            return "sorprendido" if mood_canonico in ("misterio", "tension") else "senalando"

    permitidas = config.POSES_POR_MOOD.get(mood_canonico, config.POSES)
    if p not in permitidas and not (p == "dinero" and es_contexto_finanzas and not es_tema_misterio):
        reemplazos = {
            "aprobando": "explicando",
            "dinero": "sorprendido",
        }
        p = reemplazos.get(p, permitidas[0] if permitidas else "explicando")
    return p


def asegurar_assets_host_base() -> None:
    """Crea avatares placeholder de 512x768 con fondo transparente si no existen."""
    config.HOST_DIR.mkdir(parents=True, exist_ok=True)
    
    for pose in config.POSES:
        color = COLORES_POSES.get(pose, (100, 100, 100))
        for boca in ("cerrada", "abierta"):
            ruta = config.HOST_DIR / f"{pose}_{boca}.png"
            if ruta.exists():
                continue
            
            img = Image.new("RGBA", (500, 750), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([100, 350, 400, 740], radius=40, fill=(30, 30, 38, 255), outline=(20, 20, 25), width=5)
            draw.ellipse([150, 120, 350, 340], fill=(245, 220, 195, 255), outline=(40, 40, 40), width=5)
            draw.arc([140, 100, 360, 260], start=180, end=360, fill=(40, 30, 30, 255), width=24)
            draw.ellipse([200, 200, 230, 230], fill=(30, 30, 30))
            draw.ellipse([270, 200, 300, 230], fill=(30, 30, 30))
            if boca == "abierta":
                draw.chord([220, 260, 280, 300], start=0, end=180, fill=(180, 40, 40), outline=(50, 20, 20), width=3)
            else:
                draw.line([225, 275, 275, 275], fill=(50, 20, 20), width=5)
            draw.rectangle([190, 195, 240, 235], outline=(0, 0, 0), width=4)
            draw.rectangle([260, 195, 310, 235], outline=(0, 0, 0), width=4)
            draw.line([240, 215, 260, 215], fill=(0, 0, 0), width=4)
            draw.rounded_rectangle([140, 430, 360, 490], radius=15, fill=color + (255,), outline=(255, 255, 255), width=3)
            draw.text((160, 445), f"HOST: {pose.upper()}", fill=(255, 255, 255))
            img.save(ruta, "PNG")


def obtener_sprite(
    pose: str,
    boca: str = "cerrada",
    mood: str = "misterio",
    tema: str = "",
    texto_voz: str = "",
) -> Path:
    """Devuelve la ruta al sprite del Host validando pose contra mood y tema."""
    asegurar_assets_host_base()
    p = normalizar_pose(pose, mood=mood, tema=tema, texto_voz=texto_voz)
    ruta = config.HOST_DIR / f"{p}_{boca}.png"
    if not ruta.exists():
        ruta = config.HOST_DIR / "explicando_cerrada.png"
    return ruta
