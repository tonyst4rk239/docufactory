"""Estado persistente de un proyecto de video (proyecto.json), para etapas reanudables."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config

ETAPAS = ["guion", "voz", "alineacion", "broll", "revision", "render", "shorts", "publicacion"]
SUBCARPETAS = ["guion", "voz", "b_roll", "render", "renders", "shorts", "publicacion"]



def _calcular_firma_escenas(escenas: list[Any]) -> dict[str, Any]:
    """Calcula una huella determinista del número, orden e identidad de las escenas."""
    ids_orden: list[int] = []
    resumen_escenas: list[dict[str, Any]] = []
    for idx, e in enumerate(escenas, 1):
        if isinstance(e, dict):
            eid = int(e.get("id", idx))
            puesto = e.get("puesto")
            voz = str(e.get("voz") or e.get("narracion") or "").strip()
            queries = list(e.get("broll_queries_en") or ([e.get("broll_query_en")] if e.get("broll_query_en") else []))
        else:
            eid = int(getattr(e, "id", idx))
            puesto = getattr(e, "puesto", None)
            voz = str(getattr(e, "voz", "")).strip()
            queries = list(
                getattr(e, "broll_queries_en", None)
                or ([getattr(e, "broll_query_en", "")] if getattr(e, "broll_query_en", "") else [])
            )
        ids_orden.append(eid)
        resumen_escenas.append(
            {
                "pos": idx,
                "id": eid,
                "puesto": puesto,
                "queries": [str(q).strip().lower() for q in queries if str(q).strip()],
                "voz_hash": hashlib.sha1(voz.encode("utf-8")).hexdigest()[:12],
            }
        )
    payload = json.dumps(resumen_escenas, sort_keys=True, ensure_ascii=False)
    return {
        "num_escenas": len(escenas),
        "orden_ids": ids_orden,
        " orden_puestos": [r["puesto"] for r in resumen_escenas],
        "hash_global": hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16],
    }


class Proyecto:
    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)
        self.archivo = self.carpeta / "proyecto.json"
        self.datos: dict = json.loads(self.archivo.read_text("utf-8")) if self.archivo.exists() else {}

    # ---------- creación / carga ----------
    @classmethod
    def _buscar_existente_por_slug_base(cls, slug_base: str) -> Path | None:
        if not config.PROYECTOS.exists():
            return None
        candidatos: list[Path] = []
        exacto = config.PROYECTOS / f"video_{slug_base}"
        if (exacto / "proyecto.json").exists():
            candidatos.append(exacto)
        for d in config.PROYECTOS.glob(f"video_{slug_base}_*"):
            if d.is_dir() and (d / "proyecto.json").exists():
                candidatos.append(d)
        if not candidatos:
            return None
        candidatos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidatos[0]

    @classmethod
    def crear(cls, tema: str, minutos: float, lang: str, reusar: bool = False) -> "Proyecto":
        slug_base = config.slugify(tema)
        carpeta_existente = cls._buscar_existente_por_slug_base(slug_base) if reusar else None

        if carpeta_existente is not None:
            p = cls(carpeta_existente)
            for sub in SUBCARPETAS:
                (p.carpeta / sub).mkdir(parents=True, exist_ok=True)
            p.datos["minutos"] = minutos
            p.datos["lang"] = lang
            p.datos["reusado_en"] = datetime.now().isoformat(timespec="seconds")
            p.guardar()
            print(f"♻️  Reutilizando proyecto existente (--reusar): {p.carpeta.name}")
            return p

        ahora = datetime.now()
        ts = ahora.strftime("%Y%m%d_%H%M")
        slug = f"{slug_base}_{ts}"
        carpeta = config.PROYECTOS / f"video_{slug}"
        if carpeta.exists():
            ts_seg = ahora.strftime("%Y%m%d_%H%M%S")
            slug = f"{slug_base}_{ts_seg}"
            carpeta = config.PROYECTOS / f"video_{slug}"

        for sub in SUBCARPETAS:
            (carpeta / sub).mkdir(parents=True, exist_ok=True)
        p = cls(carpeta)
        if not p.datos:
            p.datos = {
                "tema": tema,
                "slug": slug,
                "slug_base": slug_base,
                "minutos": minutos,
                "lang": lang,
                "creado": ahora.isoformat(timespec="seconds"),
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
            slug_limpio = slug_o_ruta[6:] if slug_o_ruta.startswith("video_") else slug_o_ruta
            reciente = cls._buscar_existente_por_slug_base(slug_limpio)
            if reciente is not None:
                print(f"ℹ️  Usando proyecto más reciente para '{slug_o_ruta}': {reciente.name}")
                return cls(reciente)
            raise FileNotFoundError(f"No existe el proyecto: {ruta}")
        return cls(ruta)

    # ---------- invalidación de caché ----------
    def limpiar_broll_y_renders(self, motivo: str = "regeneración de escenas") -> None:
        """Limpia b_roll/, render/, renders/ y voz/ cuando cambia el número o el orden de escenas."""
        print(f"🧹 Limpiando b_roll/ y renders/ ({motivo})...")
        for sub in ("b_roll", "render", "renders", "voz"):
            ruta_sub = self.carpeta / sub
            if ruta_sub.exists():
                shutil.rmtree(ruta_sub, ignore_errors=True)
            ruta_sub.mkdir(parents=True, exist_ok=True)
        for etapa_reset in ("voz", "broll", "revision", "render", "publicacion"):
            if etapa_reset in self.datos.get("etapas", {}):
                self.datos["etapas"][etapa_reset] = "pendiente"
        self.guardar()

    def invalidar_cache_si_guion_cambio(self, escenas: list[Any]) -> bool:
        """Compara la firma de escenas actual con la previa y limpia b_roll/ y renders/ si cambió."""
        nueva_firma = _calcular_firma_escenas(escenas)
        firma_previa = self.datos.get("firma_escenas")

        # Detectar si existen clips huérfanos en b_roll/ o renders/ de una corrida anterior
        carpeta_broll = self.carpeta / "b_roll"
        clips_existentes = sorted(carpeta_broll.glob("escena_*.mp4")) if carpeta_broll.exists() else []
        carpeta_renders = self.carpeta / "renders"
        renders_existentes = list(carpeta_renders.glob("*.mp4")) if carpeta_renders.exists() else []

        cambio = False
        motivo = ""
        if firma_previa is not None:
            if firma_previa.get("num_escenas") != nueva_firma["num_escenas"]:
                cambio = True
                motivo = (
                    f"cambió el número de escenas ({firma_previa.get('num_escenas')} -> {nueva_firma['num_escenas']})"
                )
            elif firma_previa.get("orden_ids") != nueva_firma["orden_ids"] or firma_previa.get(" hash_global", firma_previa.get("hash_global")) != nueva_firma["hash_global"]:
                cambio = True
                motivo = "cambió el orden o contenido de las escenas"
        elif clips_existentes or renders_existentes:
            if len(clips_existentes) != nueva_firma["num_escenas"]:
                cambio = True
                motivo = f"b_roll previo tenía {len(clips_existentes)} clips para {nueva_firma['num_escenas']} escenas"
            else:
                cambio = True
                motivo = "proyecto previo sin firma de escenas registrada"

        if cambio:
            self.limpiar_broll_y_renders(motivo=motivo)

        self.datos["firma_escenas"] = nueva_firma
        self.guardar()
        return cambio

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
