"""Motor de animación y montaje de sprites del Host (PNGTuber style).

Genera los sprites provisionales transparentes y el filtrado para componer
el host en la capa de video con FFmpeg.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from . import config

COLORES_POSES = {
    "neutro": (70, 130, 180),
    "explicando": (60, 179, 113),
    "pensativo": (147, 112, 219),
    "alerta": (220, 20, 60),
    "eureka": (255, 165, 0),
    "senalando": (30, 144, 255),
    "esceptico": (218, 112, 214),
    "riendo": (255, 215, 0),
}


def asegurar_assets_host_base() -> None:
    """Crea avatares placeholder de 512x768 con fondo transparente si no existen."""
    config.HOST_DIR.mkdir(parents=True, exist_ok=True)
    
    for pose in config.POSES:
        color = COLORES_POSES.get(pose, (100, 100, 100))
        for boca in ("cerrada", "abierta"):
            ruta = config.HOST_DIR / f"{pose}_{boca}.png"
            if ruta.exists():
                continue
            
            # Crear imagen transparente RGBA
            img = Image.new("RGBA", (500, 750), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # Cuerpo / torso estilizado
            draw.rounded_rectangle([100, 350, 400, 740], radius=40, fill=(30, 30, 38, 255), outline=(20, 20, 25), width=5)
            # Cabeza
            draw.ellipse([150, 120, 350, 340], fill=(245, 220, 195, 255), outline=(40, 40, 40), width=5)
            # Pelo / Estilo cómic
            draw.arc([140, 100, 360, 260], start=180, end=360, fill=(40, 30, 30, 255), width=24)
            # Ojos
            draw.ellipse([200, 200, 230, 230], fill=(30, 30, 30))
            draw.ellipse([270, 200, 300, 230], fill=(30, 30, 30))
            
            # Boca (según estado)
            if boca == "abierta":
                draw.chord([220, 260, 280, 300], start=0, end=180, fill=(180, 40, 40), outline=(50, 20, 20), width=3)
            else:
                draw.line([225, 275, 275, 275], fill=(50, 20, 20), width=5)
                
            # Gafas / Accesorio de Analista
            draw.rectangle([190, 195, 240, 235], outline=(0, 0, 0), width=4)
            draw.rectangle([260, 195, 310, 235], outline=(0, 0, 0), width=4)
            draw.line([240, 215, 260, 215], fill=(0, 0, 0), width=4)
            
            # Placa / Insignia de Pose
            draw.rounded_rectangle([140, 430, 360, 490], radius=15, fill=color + (255,), outline=(255, 255, 255), width=3)
            draw.text((160, 445), f"HOST: {pose.upper()}", fill=(255, 255, 255))
            
            img.save(ruta, "PNG")


def obtener_sprite(pose: str, boca: str = "cerrada") -> Path:
    """Devuelve la ruta al sprite del Host para una pose y estado de boca."""
    asegurar_assets_host_base()
    p = pose if pose in config.POSES else "neutro"
    ruta = config.HOST_DIR / f"{p}_{boca}.png"
    if not ruta.exists():
        ruta = config.HOST_DIR / f"neutro_cerrada.png"
    return ruta
