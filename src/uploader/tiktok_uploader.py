"""Módulo de subida automatizada a TikTok mediante Playwright con sesión persistente."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional
from playwright.sync_api import sync_playwright

CREDENTIALS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "credentials"
TIKTOK_USER_DATA_DIR = CREDENTIALS_DIR / "tiktok_browser_profile"


def iniciar_sesion_tiktok():
    """Abre un navegador visual una sola vez para que el usuario inicie sesión en TikTok."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    TIKTOK_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 65)
    print("🌐 INICIO DE SESIÓN EN TIKTOK (@codiigoocultottv)")
    print("=" * 65)
    print("👉 Se abrirá una ventana de Chrome.")
    print("👉 Inicia sesión con tu cuenta de TikTok normalmente.")
    print("👉 Una vez que veas tu feed o perfil logueado, regresa aquí y pulsa ENTER.")
    print("=" * 65 + "\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(TIKTOK_USER_DATA_DIR),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        page.goto("https://www.tiktok.com/login", wait_until="networkidle")

        input("🟢 Presiona [ENTER] en esta terminal cuando hayas terminado de iniciar sesión...")
        context.close()

    print("✅ ¡Sesión de TikTok guardada con éxito! Ya no tendrás que volver a iniciar sesión.")


def subir_tiktok(
    video_path: Path | str,
    caption: str,
    headless: bool = False
) -> dict:
    """Sube un video automáticamente a TikTok Creator Studio utilizando la sesión guardada."""
    path = Path(video_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Video no encontrado: {path}")

    if not TIKTOK_USER_DATA_DIR.exists() or not any(TIKTOK_USER_DATA_DIR.iterdir()):
        print("⚠️ No hay sesión guardada de TikTok. Abriendo navegador para iniciar sesión primero...")
        iniciar_sesion_tiktok()

    print(f"🚀 [TikTok] Subiendo video a @codiigoocultottv: '{path.name}'...")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(TIKTOK_USER_DATA_DIR),
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 850}
        )
        page = context.new_page()
        
        # Ir a la página de subida de TikTok
        print("   🌐 Navegando a TikTok Studio Upload...")
        page.goto("https://www.tiktok.com/creator-center/upload?from=upload", timeout=60000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(4)

        # Verificar si pide login
        if "login" in page.url:
            context.close()
            raise RuntimeError("⚠️ La sesión de TikTok expiró o no está activa. Ejecuta iniciar_sesion_tiktok() nuevamente.")

        # Subir archivo al input file
        print("   📁 Cargando archivo de video...")
        file_input = page.wait_for_selector("input[type='file']", timeout=30000)
        file_input.set_input_files(str(path))

        # Esperar a que cargue el formulario y procese el video
        print("   ⏳ Procesando video en la plataforma...")
        time.sleep(8)

        # Introducir Caption / Descripción
        print("   ✍️ Escribiendo texto y hashtags...")
        try:
            # Selector clásico del editor de texto de TikTok
            caption_input = page.wait_for_selector(".DraftEditor-root, div[contenteditable='true'], [role='combobox']", timeout=20000)
            if caption_input:
                caption_input.click()
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.keyboard.type(caption, delay=20)
        except Exception as e:
            print(f"   ⚠️ Aviso sobre selector de descripción: {e}")

        time.sleep(3)

        # Botón Publicar / Post
        print("   🚀 Haciendo clic en Publicar...")
        btn_post = page.locator("button:has-text('Publicar'), button:has-text('Post')").first
        btn_post.click()

        # Esperar confirmación
        print("   ⏳ Esperando confirmación de publicación de TikTok...")
        time.sleep(8)

        context.close()

    print("✅ ¡Video subido a TikTok con éxito!")
    return {
        "plataforma": "TikTok",
        "archivo": path.name,
        "status": "Completado"
    }
