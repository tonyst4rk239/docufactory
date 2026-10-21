"""Configuración central: rutas, claves y constantes del pipeline."""
from __future__ import annotations

import os
import re
import shutil
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

ASSETS = RAIZ / "assets"
HOST_DIR = ASSETS / "host"
SFX_DIR = ASSETS / "sfx"
MUSIC_DIR = ASSETS / "music"
FONTS_DIR = ASSETS / "fonts"
PROYECTOS = RAIZ / "proyectos"

# --- Claves ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")


def _resolver_cookies() -> Path | None:
    valor = os.getenv("YTDLP_COOKIES", "").strip().strip('"').strip("'")
    if not valor:
        return None
    ruta = Path(valor).expanduser()
    if not ruta.is_absolute():
        ruta = RAIZ / ruta
    return ruta


# Ruta a cookies.txt para yt-dlp (None si no se configuró)
YTDLP_COOKIES: Path | None = _resolver_cookies()

# --- Modelos ---
MODELO_GUION = os.getenv("MODELO_GUION", "gemini-2.5-pro")
MODELO_ESTRUCTURA = os.getenv("MODELO_ESTRUCTURA", "gemini-2.5-pro")
MODELO_JUEZ = os.getenv("MODELO_JUEZ", "gemini-2.5-flash")
MODELO_IMAGEN = os.getenv("MODELO_IMAGEN", "gemini-2.5-flash-image")

# --- Voz ---
TTS_IDIOMA = os.getenv("TTS_IDIOMA", "es-US")
TTS_VOZ = os.getenv("TTS_VOZ", "es-US-Chirp3-HD-Charon")

# --- Ritmo ---
PALABRAS_POR_SEG = 2.5          # ~150 ppm, ritmo documental ágil
MAX_SEG_ESCENA = 10.0           # retención en Smart TV
MAX_PALABRAS_ESCENA = int(PALABRAS_POR_SEG * MAX_SEG_ESCENA)  # 25
MINUTOS_DEFAULT = 8.5           # >= 8:00 habilita mid-rolls

# --- Vocabularios cerrados (el LLM solo puede elegir de aquí) ---
POSES = ["neutro", "explicando", "pensativo", "alerta", "eureka", "senalando", "esceptico", "riendo"]
SFX_CATEGORIAS = ["ninguno", "whoosh", "impacto", "tension", "revelacion", "glitch", "ambiente", "digital", "transicion"]
MUSIC_MOODS = ["misterio", "tension", "epica", "curiosidad", "calma"]
ACTOS = ["gancho", "contexto", "conflicto", "profundizacion", "giro", "resolucion", "cta"]


def slugify(texto: str, max_len: int = 60) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "_", t).strip("_").lower()
    return t[:max_len].rstrip("_") or "video"


def ffmpeg_bin(nombre: str = "ffmpeg") -> str | None:
    """Encuentra ffmpeg/ffprobe en PATH o en la instalación de winget."""
    encontrado = shutil.which(nombre)
    if encontrado:
        return encontrado
    base = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for exe in base.glob(f"Gyan.FFmpeg*/**/bin/{nombre}.exe"):
        return str(exe)
    return None
