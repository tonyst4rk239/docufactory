"""Estado persistente de un proyecto de video (proyecto.json), para etapas reanudables."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import config

ETAPAS = ["guion", "voz", "alineacion", "broll", "render", "shorts", "publicacion"]
SUBCARPETAS = ["guion", "voz", "b_roll", "render", "shorts", "publicacion"]


class Proyecto:
    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)
        self.archivo = self.carpeta / "proyecto.json"
        self.datos: dict = json.loads(self.archivo.read_text("utf-8")) if self.archivo.exists() else {}

    # ---------- creación / carga ----------
    @classmethod
    def crear(cls, tema: str, minutos: float, lang: str) -> "Proyecto":
        slug = config.slugify(tema)
        carpeta = config.PROYECTOS / f"video_{slug}"
        for sub in SUBCARPETAS:
            (carpeta / sub).mkdir(parents=True, exist_ok=True)
        p = cls(carpeta)
        if not p.datos:
            p.datos = {
                "tema": tema,
                "slug": slug,
                "minutos": minutos,
                "lang": lang,
                "creado": datetime.now().isoformat(timespec="seconds"),
                "etapas": {e: "pendiente" for e in ETAPAS},
            }
            p.guardar()
        return p

    @classmethod
    def cargar(cls, slug_o_ruta: str) -> "Proyecto":
        ruta = Path(slug_o_ruta)
        if not ruta.exists():
            nombre = slug_o_ruta if slug_o_ruta.startswith("video_") else f"video_{slug_o_ruta}"
            ruta = config.PROYECTOS / nombre
        if not (ruta / "proyecto.json").exists():
            raise FileNotFoundError(f"No existe el proyecto: {ruta}")
        return cls(ruta)

    # ---------- utilidades ----------
    def guardar(self) -> None:
        self.archivo.write_text(json.dumps(self.datos, ensure_ascii=False, indent=2), "utf-8")

    def marcar(self, etapa: str, estado: str) -> None:
        self.datos["etapas"][etapa] = estado
        self.guardar()

    def estado(self, etapa: str) -> str:
        return self.datos["etapas"].get(etapa, "pendiente")

    def ruta(self, *partes: str) -> Path:
        return self.carpeta.joinpath(*partes)

    @property
    def tema(self) -> str:
        return self.datos["tema"]
