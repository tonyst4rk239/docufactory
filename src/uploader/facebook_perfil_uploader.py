"""Subida de Reels al PERFIL personal de Facebook ("Codigo Ocultotv") con Playwright.

La Graph API solo publica en Páginas; para el perfil usamos la sesión guardada en
assets/credentials/fb_perfil_browser_profile (igual que tiktok_uploader.py).
Funciona en Windows y Linux (en Linux necesita un DISPLAY porque corre con ventana).
"""
from __future__ import annotations

import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent.parent
CREDENTIALS_DIR = RAIZ / "assets" / "credentials"
FB_PERFIL_USER_DATA_DIR = CREDENTIALS_DIR / "fb_perfil_browser_profile"
LOGS_DIR = RAIZ / "logs" / "fb_perfil"

URL_CREAR = "https://www.facebook.com/reels/create/"
ARGS_NAVEGADOR = ["--disable-blink-features=AutomationControlled"]
SUBIDA_TIMEOUT_S = 600
CONFIRMACION_TIMEOUT_S = 240

_MARCAS_BLOQUEO = ("checkpoint", "two_step_verification", "/login", "login.php", "recover", "captcha")


class FbPerfilBloqueado(RuntimeError):
    """Facebook pide login, checkpoint, 2FA o captcha: requiere intervención humana."""


def sesion_fb_perfil_existe() -> bool:
    return FB_PERFIL_USER_DATA_DIR.exists() and (FB_PERFIL_USER_DATA_DIR / "Default").exists()


def _abrir(p, headless: bool = False):
    return p.chromium.launch_persistent_context(
        user_data_dir=str(FB_PERFIL_USER_DATA_DIR),
        headless=headless,
        args=ARGS_NAVEGADOR,
        viewport={"width": 1280, "height": 900},
        locale="es-MX",
    )


def iniciar_sesion_fb_perfil() -> None:
    """Abre el navegador una vez para que Francisco inicie sesión en su perfil."""
    FB_PERFIL_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("👉 Inicia sesión en Facebook con el perfil 'Codigo Ocultotv' y pulsa ENTER aquí al terminar.")
    with sync_playwright() as p:
        ctx = _abrir(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        input("🟢 ENTER cuando veas tu perfil con la sesión iniciada...")
        ctx.close()
    print("✅ Sesión del perfil de Facebook guardada.")


def _captura(page, nombre: str) -> Path | None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ruta = LOGS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{nombre}.png"
    try:
        page.screenshot(path=str(ruta), full_page=False)
        return ruta
    except Exception:
        return None


def _revisar_bloqueo(page) -> None:
    url = page.url.lower()
    texto = ""
    try:
        texto = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        pass
    pide_login = "inicia sesión" in texto and "contraseña" in texto and "crear reel" not in texto
    if any(m in url for m in _MARCAS_BLOQUEO) or pide_login or "confirma que eres tú" in texto:
        shot = _captura(page, "bloqueo")
        raise FbPerfilBloqueado(f"Facebook pide verificación/login (url: {page.url}). Captura: {shot}")


def _url_perfil(page) -> str:
    page.goto("https://www.facebook.com/me", wait_until="domcontentloaded", timeout=60000)
    time.sleep(5)
    _revisar_bloqueo(page)
    return page.url.split("#")[0]


def _ids_reels_perfil(page, url_perfil: str) -> list[str]:
    """IDs de reels visibles en la pestaña Reels del perfil (más reciente primero)."""
    if "profile.php" in url_perfil:
        url = re.sub(r"&sk=[^&]*", "", url_perfil) + "&sk=reels_tab"
    else:
        url = url_perfil.rstrip("/") + "/reels/"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(6)
    _revisar_bloqueo(page)
    hrefs = page.eval_on_selector_all("a[href*='/reel/']", "els => els.map(e => e.href)")
    ids: list[str] = []
    for h in hrefs:
        m = re.search(r"/reel/(\d+)", h)
        if m and m.group(1) not in ids:
            ids.append(m.group(1))
    return ids


def _huella(descripcion: str) -> str:
    """Primera línea con texto, para reconocer un reel ya publicado."""
    for linea in descripcion.splitlines():
        if linea.strip():
            return linea.strip()[:40]
    return ""


def _reel_con_texto(page, ids: list[str], huella: str, maximo: int = 6) -> str | None:
    if not huella:
        return None
    for rid in ids[:maximo]:
        try:
            page.goto(f"https://www.facebook.com/reel/{rid}", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            if huella in page.locator("body").inner_text(timeout=10000):
                return rid
        except Exception:
            continue
    return None


def _escribir_descripcion(page, descripcion: str) -> None:
    editor = page.locator("div[contenteditable='true'][role='textbox']").first
    editor.wait_for(state="visible", timeout=30000)
    editor.click()
    page.keyboard.press("Meta+A" if sys.platform == "darwin" else "Control+A")
    page.keyboard.press("Backspace")
    lineas = descripcion.strip().split("\n")
    for i, linea in enumerate(lineas):
        if linea:
            page.keyboard.insert_text(linea)
        if i < len(lineas) - 1:
            page.keyboard.press("Enter")
    time.sleep(1)
    page.keyboard.press("Escape")
    escrito = editor.inner_text().strip()
    if re.sub(r"\s+", " ", escrito) != re.sub(r"\s+", " ", descripcion.strip()):
        print(f"   ⚠️ La descripción escrita difiere de la original ({len(escrito)} vs {len(descripcion.strip())} caracteres)")


def _esperar_subida(page) -> None:
    preview = page.locator("[aria-label='Vista previa de la publicación']").first
    inicio = time.time()
    while time.time() - inicio < SUBIDA_TIMEOUT_S:
        try:
            t = preview.inner_text(timeout=5000)
        except Exception:
            t = ""
        if t and "Subiendo" not in t and "Uploading" not in t and "Procesando" not in t:
            return
        time.sleep(3)
    raise RuntimeError("El video no terminó de subirse a Facebook (sigue en 'Subiendo').")


def _boton(page, nombre: str):
    return page.locator(f"[role='button'][aria-label='{nombre}']").or_(
        page.get_by_role("button", name=nombre, exact=True)).first


def _asegurar_publico(page) -> None:
    fila = page.locator("[role='button']:has-text('Destinatarios de la publicación')").first
    fila.wait_for(state="visible", timeout=30000)
    if "Público" in fila.inner_text():
        return
    fila.click()
    time.sleep(2)
    page.locator("[role='radio']:has-text('Público'), [role='dialog'] :text-is('Público')").first.click()
    time.sleep(1)
    for nombre in ("Guardar", "Listo", "Hecho"):
        b = page.get_by_role("button", name=nombre, exact=True)
        if b.count() and b.first.is_visible():
            b.first.click()
            break
    time.sleep(2)
    fila = page.locator("[role='button']:has-text('Destinatarios de la publicación')").first
    if "Público" not in fila.inner_text():
        raise RuntimeError("No pude poner la audiencia en Público.")


def _sesion(p, headless: bool):
    ctx = _abrir(p, headless=headless)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.on("dialog", _aceptar_dialogo)
    return ctx, page


def buscar_reel_en_perfil(huella: str, excluir: list[str] | None = None, headless: bool = False
                          ) -> tuple[str, list[str], str | None]:
    """Abre el perfil y devuelve (url_perfil, ids_de_reels, id_del_reel_con_esa_huella|None)."""
    with sync_playwright() as p:
        ctx, page = _sesion(p, headless)
        try:
            url_perfil = _url_perfil(page)
            ids = _ids_reels_perfil(page, url_perfil)
            candidatos = [i for i in ids if i not in (excluir or [])]
            return url_perfil, ids, _reel_con_texto(page, candidatos, huella)
        except FbPerfilBloqueado:
            raise
        except Exception as e:
            shot = _captura(page, "error_perfil")
            raise RuntimeError(f"{e} — captura: {shot}") from e
        finally:
            ctx.close()


def subir_reel_perfil(video_path: Path | str, descripcion: str, headless: bool = False,
                      publicar: bool = True) -> dict:
    """Publica un Reel en el perfil personal. Nunca publica dos veces el mismo texto.

    publicar=False llega hasta la pantalla final sin pulsar Publicar (prueba en seco).
    Devuelve {'plataforma','status','url','reel_id'}; status: Completado | YaPublicado | Prueba.

    Cada fase abre su propio navegador: si se navega por el perfil antes de "Crear reel"
    en la misma sesión, Facebook deja la subida colgada en "Subiendo 0%".
    """
    path = Path(video_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Video no encontrado: {path}")
    if not sesion_fb_perfil_existe():
        raise RuntimeError("No hay sesión del perfil de Facebook. Ejecuta 'python subir_video.py login-fbperfil'.")

    huella = _huella(descripcion)
    print(f"🚀 [FB perfil] Subiendo '{path.name}' al perfil personal...")

    # Fase 1: evitar doble publicación
    print("   🔎 Revisando si ya está en los reels del perfil...")
    url_perfil, ids_antes, ya = buscar_reel_en_perfil(huella, headless=headless)
    if ya:
        url = f"https://www.facebook.com/reel/{ya}"
        print(f"   ⏭️ Ya estaba publicado en el perfil: {url} (no se vuelve a subir)")
        return {"plataforma": "Facebook perfil", "status": "YaPublicado", "url": url, "reel_id": ya}

    # Fase 2: crear y publicar
    with sync_playwright() as p:
        ctx, page = _sesion(p, headless)
        try:
            print("   🌐 Abriendo 'Crear reel'...")
            page.goto(URL_CREAR, wait_until="domcontentloaded", timeout=60000)
            time.sleep(6)
            _revisar_bloqueo(page)

            print("   📁 Cargando video...")
            page.locator("input[type='file']").first.set_input_files(str(path))
            print("   ⏳ Esperando a que Facebook termine de recibir el video...")
            time.sleep(5)
            _esperar_subida(page)
            print("   ✍️ Escribiendo descripción...")
            _escribir_descripcion(page, descripcion)

            _boton(page, "Siguiente").click()
            time.sleep(4)
            _asegurar_publico(page)
            print("   🌍 Audiencia: Público")

            if not publicar:
                shot = _captura(page, "prueba_en_seco")
                print(f"   🧪 Prueba en seco: no se pulsó Publicar. Captura: {shot}")
                return {"plataforma": "Facebook perfil", "status": "Prueba", "url": None, "reel_id": None}

            print("   🚀 Publicando...")
            _boton(page, "Publicar").click()
            inicio = time.time()
            while time.time() - inicio < 180 and "/reels/create" in page.url:
                time.sleep(2)
            _captura(page, "tras_publicar")
            if "/reels/create" in page.url:
                raise RuntimeError("Facebook no salió de 'Crear reel' tras pulsar Publicar. "
                                   "Revisa el perfil antes de reintentar.")
            time.sleep(10)  # deja que termine de enviar antes de cerrar
        except FbPerfilBloqueado:
            raise
        except Exception as e:
            shot = _captura(page, "error")
            raise RuntimeError(f"{e} — captura: {shot}") from e
        finally:
            ctx.close()

    # Fase 3: localizar el reel nuevo
    print("   🔎 Buscando el reel nuevo en la pestaña Reels del perfil...")
    nuevo = None
    inicio = time.time()
    while time.time() - inicio < CONFIRMACION_TIMEOUT_S and not nuevo:
        time.sleep(20)
        try:
            _, ids, nuevo = buscar_reel_en_perfil(huella, excluir=ids_antes, headless=headless)
        except FbPerfilBloqueado:
            raise
        except Exception as e:
            print(f"   ⚠️ No pude leer los reels del perfil: {e}")
    url = f"https://www.facebook.com/reel/{nuevo}" if nuevo else None
    print("✅ Reel publicado en el perfil. " + (f"🔗 {url}" if url else
          "(la URL aún no aparece en la pestaña Reels; puede seguir procesándose)"))
    return {"plataforma": "Facebook perfil", "status": "Completado", "url": url, "reel_id": nuevo}


def _aceptar_dialogo(dialogo) -> None:
    try:
        dialogo.accept()
    except Exception:
        pass
