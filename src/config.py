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
OVERLAYS_DIR = ASSETS / "overlays"
FONTS_DIR = ASSETS / "fonts"
PROYECTOS = RAIZ / "proyectos"
CONFIG_EDICION_YAML = RAIZ / "config" / "edicion.yaml"

# --- Claves ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
FREESOUND_API_KEY = os.getenv("FREESOUND_API_KEY", "")
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

# --- Modelos (solo usados si se invoca Gemini como respaldo opcional) ---
MODELO_PRO_DEFAULT = "gemini-3.1-pro-preview"
# Modelos retirados por Google (404 para usuarios nuevos): se sustituyen automáticamente.
MODELOS_RETIRADOS = {"gemini-2.5-pro", "models/gemini-2.5-pro"}


def _modelo_vigente(nombre_env: str, default: str = MODELO_PRO_DEFAULT) -> str:
    valor = (os.getenv(nombre_env) or "").strip()
    if not valor or valor in MODELOS_RETIRADOS:
        return default
    return valor


MODELO_GUION = _modelo_vigente("MODELO_GUION")
MODELO_ESTRUCTURA = _modelo_vigente("MODELO_ESTRUCTURA")
MODELO_JUEZ = os.getenv("MODELO_JUEZ", "gemini-2.5-flash")
MODELO_IMAGEN = os.getenv("MODELO_IMAGEN", "gemini-2.5-flash-image")

# --- Voz ---
TTS_IDIOMA = os.getenv("TTS_IDIOMA", "es-US")
TTS_VOZ = os.getenv("TTS_VOZ", "es-US-Chirp3-HD-Charon")

# --- Ritmo (140-150 palabras/min considerando micropausas y rate -3% de Edge-TTS) ---
PALABRAS_POR_MIN = 142
PALABRAS_POR_SEG = round(PALABRAS_POR_MIN / 60.0, 4)  # ~2.3667 pal/s
MAX_SEG_ESCENA = 9.0            # retención en Smart TV
MAX_PALABRAS_ESCENA = int(round(PALABRAS_POR_SEG * MAX_SEG_ESCENA))  # 21
MINUTOS_DEFAULT = 8.5           # >= 8:00 habilita mid-rolls
TOLERANCIA_DURACION = 0.12      # ±12% de margen al validar duración post-TTS

# --- Vocabularios cerrados (el LLM solo puede elegir de aquí) ---
POSES = ["explicando", "pensativo", "sorprendido", "esceptico", "dinero", "aprobando", "duda", "senalando"]
POSE_ALIASES = {
    "neutro": "explicando",
    "alerta": "sorprendido",
    "eureka": "sorprendido",
    "riendo": "aprobando",
}
POSES_POR_MOOD: dict[str, list[str]] = {
    "misterio": ["explicando", "pensativo", "sorprendido", "esceptico", "duda", "senalando"],
    "tension": ["sorprendido", "esceptico", "pensativo", "explicando", "duda", "senalando"],
    "epica": ["explicando", "sorprendido", "senalando", "pensativo", "aprobando"],
    "curiosidad": ["explicando", "pensativo", "sorprendido", "duda", "senalando", "esceptico", "aprobando"],
    "calma": ["explicando", "pensativo", "aprobando", "senalando"],
}
SFX_CATEGORIAS = [
    "ninguno", "whoosh", "riser", "impact", "impacto", "tension",
    "revelacion", "glitch", "ambiente", "digital", "transicion", "click", "teclado",
]
OVERLAY_TIPOS = ["film_grain", "dust_overlay", "light_leak", "glitch", "vhs"]
MUSIC_MOODS = ["misterio", "tension", "epica", "curiosidad", "calma"]
MUSIC_FALLBACKS: dict[str, list[str]] = {
    "tension": ["misterio", "curiosidad", "calma"],
    "epica": ["curiosidad", "misterio", "tension", "calma"],
    "misterio": ["tension", "curiosidad", "calma"],
    "curiosidad": ["misterio", "calma", "tension"],
    "calma": ["curiosidad", "misterio"],
}
SFX_FALLBACKS: dict[str, list[str]] = {
    "riser": ["whoosh", "tension", "transicion"],
    "impact": ["impacto", "revelacion", "whoosh"],
    "impacto": ["impact", "revelacion", "whoosh"],
    "tension": ["impacto", "impact", "revelacion", "glitch"],
    "ambiente": ["whoosh", "transicion"],
    "digital": ["glitch", "teclado", "click"],
    "whoosh": ["transicion", "impacto", "impact"],
    "transicion": ["whoosh", "click"],
    "revelacion": ["impacto", "impact", "glitch"],
    "glitch": ["revelacion", "digital", "impacto"],
    "teclado": ["click", "transicion"],
    "click": ["teclado", "transicion"],
}
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
