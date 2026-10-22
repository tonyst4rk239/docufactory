"""Módulo de subida automatizada a YouTube Shorts mediante YouTube Data API v3."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
CREDENTIALS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "credentials"
CLIENT_SECRETS_FILE = CREDENTIALS_DIR / "client_secrets.json"
TOKEN_FILE = CREDENTIALS_DIR / "token_youtube.json"


def obtener_servicio_youtube():
    """Autentica y devuelve el cliente oficial de YouTube Data API v3."""
    creds = None
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRETS_FILE.exists():
                raise FileNotFoundError(
                    f"❌ No se encontró el archivo de credenciales de Google Cloud:\n   {CLIENT_SECRETS_FILE}\n\n"
                    "👉 Pasos para obtenerlo:\n"
                    "1. Ve a https://console.cloud.google.com/\n"
                    "2. Crea un proyecto y habilita 'YouTube Data API v3'.\n"
                    "3. Ve a 'Credenciales' > Crear credenciales > 'ID de cliente de OAuth' (Aplicación de escritorio).\n"
                    "4. Descarga el JSON y guárdalo como: assets/credentials/client_secrets.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def subir_youtube_short(
    video_path: Path | str,
    titulo: str,
    descripcion: str,
    tags: Optional[list[str]] = None,
    privacidad: str = "public",
    hora_programada_iso: Optional[str] = None,
    es_short: bool = True,
    miniatura: Optional[Path | str] = None,
    categoria: str = "24",
) -> dict:
    """Sube un video a YouTube como Short y retorna el ID y enlace."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video no encontrado: {path}")

    youtube = obtener_servicio_youtube()

    # Si se programa, YouTube exige que inicialmente sea private
    estado_privacidad = "private" if hora_programada_iso else privacidad

    # Asegurar hashtag #Shorts para garantizar indexación
    if es_short and "#Shorts" not in descripcion and "#shorts" not in descripcion:
        descripcion += "\n\n#Shorts #Viral"

    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descripcion,
            "tags": tags or ["Shorts", "Viral", "CodigoOcultoTV"],
            "categoryId": categoria  # 24 = Entertainment
        },
        "status": {
            "privacyStatus": estado_privacidad,
            "selfDeclaredMadeForKids": False
        }
    }

    if hora_programada_iso:
        body["status"]["publishAt"] = hora_programada_iso

    media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True, chunksize=1024 * 1024 * 5)
    peticion = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"🚀 Subiendo a YouTube: '{titulo}'...")
    respuesta = None
    while respuesta is None:
        estado, respuesta = peticion.next_chunk()
        if estado:
            print(f"   ⏳ Progreso de subida: {int(estado.progress() * 100)}%")

    video_id = respuesta.get("id")
    enlace = f"https://youtube.com/shorts/{video_id}" if es_short else f"https://youtu.be/{video_id}"
    print(f"✅ ¡Video subido a YouTube ({estado_privacidad})!\n   🔗 Enlace: {enlace}")

    miniatura_ok = None
    if miniatura and Path(miniatura).exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id, media_body=MediaFileUpload(str(miniatura))
            ).execute()
            miniatura_ok = True
            print("🖼️  Miniatura personalizada aplicada.")
        except Exception as e:
            miniatura_ok = False
            print(f"⚠️ No se pudo aplicar la miniatura (¿canal sin verificar?): {e}")

    return {
        "plataforma": "YouTube",
        "video_id": video_id,
        "url": enlace,
        "privacidad": estado_privacidad,
        "miniatura_ok": miniatura_ok,
        "respuesta": respuesta
    }
