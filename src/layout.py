"""Geometría de pantalla 16:9: caja del host 2D y zona segura para textos (.ass, créditos, paneles).

Regla: ningún texto ni panel debe solapar al host. Se calcula la caja del host (sprite escalado a
HOST_ALTO px, pegado abajo a HOST_MARGEN_X px del borde de su lado) y los textos se colocan en el
lado opuesto, en la franja superior, con margen de seguridad.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from . import config

ANCHO, ALTO = 1920, 1080
HOST_ALTO = 750
HOST_MARGEN_X = 80
MARGEN_SEGURO = 60
MARGEN_BORDE = 60
# Avance medio (em) de Arial Black en mayúsculas (la fuente más ancha usada); en Linux la fuente de
# respaldo es más estrecha, así que la estimación es conservadora en ambos sistemas.
FACTOR_ANCHO_CHAR = 0.72
FACTOR_ANCHO_ESPACIO = 0.33


@dataclass(frozen=True)
class Caja:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    def solapa(self, otra: "Caja") -> bool:
        return not (self.x2 <= otra.x or otra.x2 <= self.x or self.y2 <= otra.y or otra.y2 <= self.y)


@lru_cache(maxsize=64)
def _ancho_sprite(pose: str) -> int:
    """Ancho escalado (a HOST_ALTO) del sprite de la pose; usa el más ancho disponible si no existe."""
    try:
        from PIL import Image
    except Exception:  # pragma: no cover
        return 700
    carpetas = [config.ASSETS / "host_tight", config.HOST_DIR]
    for carpeta in carpetas:
        for nombre in (f"{pose}_cerrada.png", f"{pose}_abierta.png"):
            f = carpeta / nombre
            if f.exists():
                with Image.open(f) as im:
                    w, h = im.size
                return int(round(HOST_ALTO * w / max(1, h)))
    anchos = []
    for carpeta in carpetas:
        for f in carpeta.glob("*.png") if carpeta.exists() else []:
            with Image.open(f) as im:
                w, h = im.size
            anchos.append(int(round(HOST_ALTO * w / max(1, h))))
    return max(anchos) if anchos else 700


def caja_host(pose: str, host_lado: str = "izquierda", visible: bool = True) -> Optional[Caja]:
    if not visible:
        return None
    w = _ancho_sprite(pose or "explicando")
    x = ANCHO - w - HOST_MARGEN_X if host_lado == "derecha" else HOST_MARGEN_X
    return Caja(x, ALTO - HOST_ALTO, w, HOST_ALTO)


def zona_texto(host: Optional[Caja]) -> Caja:
    """Zona horizontal libre (lado opuesto al host) para textos y paneles."""
    if host is None:
        return Caja(MARGEN_BORDE, MARGEN_BORDE, ANCHO - 2 * MARGEN_BORDE, ALTO - 2 * MARGEN_BORDE)
    if host.x + host.w / 2 < ANCHO / 2:  # host a la izquierda -> texto a la derecha
        x0 = host.x2 + MARGEN_SEGURO
        return Caja(x0, MARGEN_BORDE, ANCHO - MARGEN_BORDE - x0, ALTO - 2 * MARGEN_BORDE)
    x1 = host.x - MARGEN_SEGURO
    return Caja(MARGEN_BORDE, MARGEN_BORDE, x1 - MARGEN_BORDE, ALTO - 2 * MARGEN_BORDE)


def _ems(texto: str) -> float:
    return sum(FACTOR_ANCHO_ESPACIO if c == " " else FACTOR_ANCHO_CHAR for c in texto)


def ancho_texto(texto: str, fs: int, padding: int = 26) -> int:
    return int(_ems(texto) * fs) + 2 * padding


def ajustar_fuente(lineas: list[str], fs_max: int, ancho_disp: int, fs_min: int = 40, padding: int = 26) -> int:
    larga = max((_ems(l) for l in lineas), default=1.0) or 1.0
    fs = int((ancho_disp - 2 * padding) / larga)
    return max(fs_min, min(fs_max, fs))


def partir_en_lineas(texto: str, fs_max: int, ancho_disp: int, fs_legible: int = 70) -> list[str]:
    """Devuelve 1 o 2 líneas; parte en el espacio más cercano al centro si a 1 línea queda ilegible."""
    texto = texto.strip()
    if ajustar_fuente([texto], fs_max, ancho_disp) >= fs_legible or " " not in texto:
        return [texto]
    mitad = len(texto) / 2
    espacios = [i for i, c in enumerate(texto) if c == " "]
    corte = min(espacios, key=lambda i: abs(i - mitad))
    return [texto[:corte].strip(), texto[corte + 1:].strip()]


def caja_bloque(lineas_fs: list[tuple[str, int]], centro_x: int, y_top: int, padding: int = 26) -> Caja:
    w = max(ancho_texto(t, fs, padding) for t, fs in lineas_fs)
    h = sum(int(fs * 1.25) + padding for _, fs in lineas_fs)
    return Caja(int(centro_x - w / 2), y_top, w, h)
