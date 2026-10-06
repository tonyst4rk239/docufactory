"""Búsqueda y descarga inteligente de B-Roll (Pixabay Videos, Wikimedia Commons y Pixabay Fotos).

Descarga fragmentos en alta resolución para cada escena del guion,
asigna créditos y asegura que no haya videos duplicados en el montaje.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional
import requests

from . import config
from .estado import Proyecto
from .guion import cargar_guion, Guion, Escena


def _buscar_pixabay_video(query: str, min_duration: float = 3.0) -> Optional[dict]:
    """Busca video en Pixabay API."""
    if not config.PIXABAY_API_KEY:
        return None
    url = "https://pixabay.com/api/videos/"
    params = {
        "key": config.PIXABAY_API_KEY,
        "q": query,
        "per_page": 5,
        "video_type": "film",
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        if r.ok:
            hits = r.json().get("hits", [])
            for h in hits:
                vids = h.get("videos", {})
                # Priorizar medium (720p/1080p) o large
                opt = vids.get("large") or vids.get("medium") or vids.get("small")
                if opt and opt.get("url"):
                    return {
                        "tipo": "video",
                        "fuente": "Pixabay",
                        "id": h["id"],
                        "url": opt["url"],
                        "duracion": h.get("duration", 0),
                        "creditos": f"Pixabay Video ID {h['id']} ({h.get('user', 'Pixabay')})",
                    }
    except Exception as e:
        print(f"⚠️ Error buscando video Pixabay ({query}): {e}")
    return None


def _buscar_pixabay_imagen(query: str) -> Optional[dict]:
    """Busca imagen en Pixabay API como respaldo visual."""
    if not config.PIXABAY_API_KEY:
        return None
    url = "https://pixabay.com/api/"
    params = {
        "key": config.PIXABAY_API_KEY,
        "q": query,
        "per_page": 5,
        "image_type": "photo",
        "orientation": "horizontal",
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        if r.ok:
            hits = r.json().get("hits", [])
            if hits:
                h = hits[0]
                return {
                    "tipo": "imagen",
                    "fuente": "Pixabay",
                    "id": h["id"],
                    "url": h.get("largeImageURL") or h.get("webformatURL"),
                    "creditos": f"Pixabay Foto ID {h['id']} ({h.get('user', 'Pixabay')})",
                }
    except Exception as e:
        print(f"⚠️ Error buscando imagen Pixabay ({query}): {e}")
    return None


def _buscar_wikimedia(query: str) -> Optional[dict]:
    """Busca imagen/diagrama en Wikimedia Commons con metadatos de licencia."""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,  # File namespace
        "gsrlimit": 3,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "format": "json",
    }
    try:
        r = requests.get(url, params=params, headers={"User-Agent": "DocuFactoryBot/1.0"}, timeout=12)
        if r.ok:
            pages = r.json().get("query", {}).get("pages", {})
            for pid, p in pages.items():
                ii = p.get("imageinfo", [{}])[0]
                mime = ii.get("mime", "")
                if mime.startswith("image/") and not mime.endswith("svg+xml"):
                    return {
                        "tipo": "imagen",
                        "fuente": "Wikimedia",
                        "id": p.get("title"),
                        "url": ii.get("url"),
                        "creditos": f"Wikimedia Commons: {p.get('title')}",
                    }
    except Exception as e:
        print(f"⚠️ Error buscando en Wikimedia ({query}): {e}")
    return None


def descargar_archivo(url: str, destino: Path) -> bool:
    """Descarga un archivo remoto a la ruta indicada."""
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(destino, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"❌ Error al descargar {url}: {e}")
        return False


def etapa_broll(p: Proyecto) -> dict:
    """Descarga recursos visuales para cada escena del guion."""
    guion = cargar_guion(p)
    carpeta_broll = p.ruta("b_roll")
    carpeta_broll.mkdir(exist_ok=True, parents=True)
    
    creditos = []
    vistos_ids = set()
    total = len(guion.escenas)
    
    print(f"🎬 Buscando B-Roll para {total} escenas...")
    
    for i, esc in enumerate(guion.escenas, 1):
        query = esc.broll_query_en
        # 1. Intentar video Pixabay
        recurso = _buscar_pixabay_video(query)
        if recurso and recurso["id"] in vistos_ids:
            recurso = None  # evitar repetir mismo video
            
        # 2. Respaldo: Imagen Pixabay
        if not recurso:
            recurso = _buscar_pixabay_imagen(query)
            
        # 3. Respaldo: Wikimedia Commons
        if not recurso:
            recurso = _buscar_wikimedia(query)
            
        if recurso:
            vistos_ids.add(recurso.get("id"))
            ext = ".mp4" if recurso["tipo"] == "video" else ".jpg"
            destino = carpeta_broll / f"escena_{esc.id:03d}{ext}"
            
            if not destino.exists():
                print(f"   [{i}/{total}] Descargando {recurso['tipo']} ({recurso['fuente']}) para Escena {esc.id}...")
                descargar_archivo(recurso["url"], destino)
            else:
                print(f"   [{i}/{total}] Escena {esc.id}: Ya existe en caché ({destino.name})")
                
            creditos.append({
                "escena": esc.id,
                "archivo": destino.name,
                "tipo": recurso["tipo"],
                "fuente": recurso["fuente"],
                "credito": recurso["creditos"]
            })
        else:
            print(f"   ⚠️ Escena {esc.id}: No se encontró B-Roll para '{query}'. Se usará placeholder de respaldo.")

    # Guardar archivo de créditos de atribución
    p.ruta("b_roll", "creditos.json").write_text(json.dumps(creditos, ensure_ascii=False, indent=2), "utf-8")
    p.marcar("broll", "ok")
    print("✨ B-Roll listo y clasificado.")
    return creditos
