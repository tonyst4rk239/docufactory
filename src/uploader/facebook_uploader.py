"""Módulo de subida automatizada a Facebook Reels mediante Meta Graph API oficial."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

GRAPH_VERSION = "v20.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


def subir_facebook_reel(
    video_path: Path | str,
    descripcion: str,
    page_id: Optional[str] = None,
    page_token: Optional[str] = None,
    hora_programada_unix: Optional[int] = None
) -> dict:
    """Sube y publica un Reel directamente en una Página de Facebook mediante Meta Graph API."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video no encontrado: {path}")

    pid = page_id or os.getenv("FB_PAGE_ID", "61594841415387")
    token = page_token or os.getenv("FB_PAGE_TOKEN", "")

    if not token:
        raise ValueError(
            "❌ No se encontró FB_PAGE_TOKEN en tu archivo .env ni en los parámetros.\n"
            "👉 Para obtener tu Token de Página de Facebook:\n"
            "1. Ve a https://developers.facebook.com/tools/explorer/\n"
            "2. Selecciona tu app y genera un User Token con permisos 'pages_show_list', 'pages_read_engagement', 'pages_manage_posts'.\n"
            "3. En el selector de cuentas elige tu Página 'Código Oculto TV' y copia el Page Access Token generado.\n"
            "4. Agrégalo a tu archivo .env como: FB_PAGE_TOKEN=tu_token_aqui"
        )

    file_size = path.stat().st_size

    # Fase 1: Iniciar sesión de subida de Reel
    print("🚀 [Facebook] Inicializando sesión de subida de Reel...")
    url_inicio = f"{GRAPH_URL}/{pid}/video_reels"
    resp_inicio = requests.post(url_inicio, data={
        "upload_phase": "start",
        "access_token": token
    })
    data_inicio = resp_inicio.json()
    if "video_id" not in data_inicio:
        raise RuntimeError(f"Error al iniciar subida de Reel en Facebook: {data_inicio}")

    video_id = data_inicio["video_id"]
    upload_url = data_inicio["upload_url"]

    # Fase 2: Transferir archivo binario
    print("⏳ [Facebook] Transfiriendo archivo de video a los servidores de Meta...")
    headers = {
        "Authorization": f"OAuth {token}",
        "offset": "0",
        "file_size": str(file_size)
    }
    with open(path, "rb") as f:
        resp_bin = requests.post(upload_url, headers=headers, data=f)
    
    if not resp_bin.ok:
        raise RuntimeError(f"Error al transferir video a Facebook: {resp_bin.text}")

    # Fase 3: Publicar o programar Reel
    print("📢 [Facebook] Procesando y publicando Reel en la página...")
    datos_publicacion = {
        "upload_phase": "finish",
        "access_token": token,
        "video_id": video_id,
        "video_state": "SCHEDULED" if hora_programada_unix else "PUBLISHED",
        "description": descripcion
    }
    if hora_programada_unix:
        datos_publicacion["scheduled_publish_time"] = str(hora_programada_unix)

    resp_fin = requests.post(url_inicio, data=datos_publicacion)
    data_fin = resp_fin.json()

    if not data_fin.get("success", False):
        raise RuntimeError(f"Error al finalizar publicación del Reel: {data_fin}")

    url_reel = f"https://www.facebook.com/reel/{video_id}"
    print(f"✅ ¡Reel publicado exitosamente en Facebook!\n   🔗 Enlace: {url_reel}")

    return {
        "plataforma": "Facebook Reels",
        "video_id": video_id,
        "url": url_reel,
        "respuesta": data_fin
    }
