"""Docu Factory — CLI Unificado de Subida Multi-Plataforma.
Sube automáticamente cualquier video a YouTube Shorts, Facebook Reels y TikTok.

Uso:
  python subir_video.py <video.mp4> [--plataformas yt fb tt] [--titulo "Mi Titulo"] [--texto "Descripcion #shorts"]
  python subir_video.py status
  python subir_video.py login-tiktok
  python subir_video.py auth-youtube
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

from src.uploader.youtube_uploader import subir_youtube_short, CLIENT_SECRETS_FILE, TOKEN_FILE, obtener_servicio_youtube
from src.uploader.facebook_uploader import subir_facebook_reel
from src.uploader.tiktok_uploader import subir_tiktok, iniciar_sesion_tiktok, TIKTOK_USER_DATA_DIR


def cmd_status(args) -> int:
    print("\n" + "=" * 65)
    print("📊 ESTADO DE CONEXIÓN MULTI-PLATAFORMA")
    print("=" * 65)

    # 1. YouTube
    yt_secrets = CLIENT_SECRETS_FILE.exists()
    yt_token = TOKEN_FILE.exists()
    if yt_token:
        print("✅ YouTube Data API: CONECTADO Y AUTORIZADO (token_youtube.json)")
    elif yt_secrets:
        print("⚠️ YouTube Data API: client_secrets.json detectado. Falta autorizar ('python subir_video.py auth-youtube')")
    else:
        print("❌ YouTube Data API: No configurado. Falta 'assets/credentials/client_secrets.json'")

    # 2. Facebook Reels
    fb_token = bool(os.getenv("FB_PAGE_TOKEN"))
    fb_page = os.getenv("FB_PAGE_ID", "61594841415387")
    if fb_token:
        print(f"✅ Facebook Reels API: CONECTADO (Página ID: {fb_page})")
    else:
        print(f"❌ Facebook Reels API: No configurado. Agrega FB_PAGE_TOKEN en tu archivo .env")

    # 3. TikTok
    tt_session = TIKTOK_USER_DATA_DIR.exists() and any(TIKTOK_USER_DATA_DIR.iterdir())
    if tt_session:
        print("✅ TikTok Playwright: SESIÓN GUARDADA (tiktok_browser_profile)")
    else:
        print("❌ TikTok Playwright: Sin sesión iniciada. Ejecuta 'python subir_video.py login-tiktok'")

    print("=" * 65 + "\n")
    return 0


def cmd_auth_youtube(args) -> int:
    try:
        print("🔐 Iniciando autorización de YouTube...")
        obtener_servicio_youtube()
        print("✅ ¡YouTube autorizado con éxito!")
        return 0
    except Exception as e:
        print(f"❌ Error en autorización de YouTube: {e}")
        return 1


def cmd_login_tiktok(args) -> int:
    iniciar_sesion_tiktok()
    return 0


def cmd_subir(args) -> int:
    video_path = Path(args.video).resolve()
    if not video_path.exists():
        # Buscar en renders de proyectos si pasaron un nombre relativo
        print(f"❌ No se encontró el archivo: {video_path}")
        return 1

    titulo = args.titulo or video_path.stem.replace("_", " ").title()
    texto = args.texto or (titulo + " #fyp #parati #viral #codigoocultotv #Shorts")
    plataformas = [p.lower() for p in args.plataformas]

    print("\n" + "=" * 65)
    print(f"🚀 PUBLICANDO VIDEO MULTI-PLATAFORMA")
    print(f"📁 Archivo: {video_path.name}")
    print(f"📝 Título: {titulo}")
    print(f"🌐 Plataformas: {', '.join(plataformas).upper()}")
    print("=" * 65 + "\n")

    errores = []

    # 1. YouTube Shorts
    if "yt" in plataformas or "youtube" in plataformas:
        try:
            subir_youtube_short(video_path, titulo=titulo, descripcion=texto, privacidad=args.privacidad)
        except Exception as e:
            print(f"❌ Error subiendo a YouTube: {e}")
            errores.append("YouTube")

    # 2. Facebook Reels
    if "fb" in plataformas or "facebook" in plataformas:
        try:
            subir_facebook_reel(video_path, descripcion=texto)
        except Exception as e:
            print(f"❌ Error subiendo a Facebook Reels: {e}")
            errores.append("Facebook")

    # 3. TikTok
    if "tt" in plataformas or "tiktok" in plataformas:
        try:
            subir_tiktok(video_path, caption=texto, headless=args.headless)
        except Exception as e:
            print(f"❌ Error subiendo a TikTok: {e}")
            errores.append("TikTok")

    if errores:
        print(f"\n⚠️ Falló la subida en: {', '.join(errores)}")
        return 1

    print("\n🏆 ¡TODAS LAS SUBIDAS COMPLETADAS EXITOSAMENTE!")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Publicador automático a YouTube Shorts, Facebook Reels y TikTok.")
    subs = parser.add_subparsers(dest="comando")

    # Subcomando status
    p_stat = subs.add_parser("status", help="Muestra el estado de credenciales")
    p_stat.set_defaults(func=cmd_status)

    # Subcomando auth-youtube
    p_ay = subs.add_parser("auth-youtube", help="Autoriza cuenta de YouTube")
    p_ay.set_defaults(func=cmd_auth_youtube)

    # Subcomando login-tiktok
    p_lt = subs.add_parser("login-tiktok", help="Inicia sesión en TikTok y guarda sesión")
    p_lt.set_defaults(func=cmd_login_tiktok)

    # Subcomando subir
    p_sub = subs.add_parser("subir", help="Sube un video a las plataformas seleccionadas")
    p_sub.add_argument("video", help="Ruta al archivo MP4")
    p_sub.add_argument("--plataformas", nargs="+", default=["yt", "fb", "tt"], help="Plataformas destino: yt, fb, tt")
    p_sub.add_argument("--titulo", default=None, help="Título del video")
    p_sub.add_argument("--texto", default=None, help="Texto/Copy y hashtags")
    p_sub.add_argument("--privacidad", default="public", choices=["public", "private", "unlisted"], help="Privacidad (YouTube)")
    p_sub.add_argument("--headless", action="store_true", help="Ejecutar TikTok en segundo plano sin ventana visual")
    p_sub.set_defaults(func=cmd_subir)

    args = parser.parse_args()

    # Si se pasa como: python subir_video.py ruta.mp4 ...
    if not args.comando and len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        sys.argv.insert(1, "subir")
        args = parser.parse_args()

    if not args.comando:
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
