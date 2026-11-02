"""Script para autorizar canales de YouTube via OAuth 2.0 y guardar su token correspondiente.

Canales soportados:
- 'Código OcultoTV' (Docu Factory) -> assets/credentials/token_youtube.json
- 'Novelas Express MX' (ID: UC8O5Zv0nsHRfaXij9uJNYbg) -> assets/credentials/token_youtube_novelas.json

Scopes requeridos:
- https://www.googleapis.com/auth/youtube.readonly
- https://www.googleapis.com/auth/yt-analytics.readonly
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from src.metricas.recolectar import guardar_token_atomicamente

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

CLIENT_SECRETS_FILE = RAIZ / "assets" / "credentials" / "client_secrets.json"
TOKEN_CODIGO = RAIZ / "assets" / "credentials" / "token_youtube.json"
TOKEN_NOVELAS = RAIZ / "assets" / "credentials" / "token_youtube_novelas.json"

NOVELAS_CHANNEL_ID = "UC8O5Zv0nsHRfaXij9uJNYbg"


def normalizar_canal(nombre: str) -> str:
    n = (nombre or "").strip().lower()
    if "novela" in n:
        return "Novelas Express MX"
    return "Código OcultoTV"


def resolver_token_path(canal_normalizado: str, custom_token: Path | None = None) -> Path:
    if custom_token:
        return Path(custom_token)
    if canal_normalizado == "Novelas Express MX":
        return TOKEN_NOVELAS
    return TOKEN_CODIGO


def autorizar_canal(
    canal: str = "Código OcultoTV",
    client_secrets_path: Path = CLIENT_SECRETS_FILE,
    token_salida: Path | None = None,
    port: int = 0,
) -> tuple[str, str, Path]:
    """Ejecuta el flujo OAuth local, valida el channel ID y guarda el token.

    Retorna (channel_id, channel_title, token_path).
    """
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    client_secrets = Path(client_secrets_path)
    if not client_secrets.exists():
        raise FileNotFoundError(
            f"No existe el archivo de credenciales de aplicación: {client_secrets}\n"
            "Descárgalo desde Google Cloud Console como client_secrets.json."
        )

    canal_norm = normalizar_canal(canal)
    dest_token = resolver_token_path(canal_norm, token_salida)
    dest_token.parent.mkdir(parents=True, exist_ok=True)

    print(f"=== Iniciando autorización OAuth para '{canal_norm}' ===")
    print(f"  Scopes solicitados: {', '.join(SCOPES)}")

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
    creds = flow.run_local_server(port=port)

    # Validar canal autenticado contra YouTube Data API
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ch_resp = yt.channels().list(part="id,snippet", mine=True).execute()
    items = ch_resp.get("items", [])
    if not items:
        raise RuntimeError("No se encontró ningún canal asociado a la cuenta de Google autenticada.")

    ch = items[0]
    actual_id = ch["id"]
    actual_title = ch["snippet"]["title"]

    # Validación estricta de channel ID para Novelas Express MX
    if canal_norm == "Novelas Express MX":
        if actual_id != NOVELAS_CHANNEL_ID:
            raise RuntimeError(
                f"Error de verificación de canal: Se autenticó el canal '{actual_title}' (ID: {actual_id}), "
                f"pero se esperaba estrictamente Novelas Express MX (ID: {NOVELAS_CHANNEL_ID}). "
                "Por favor selecciona la cuenta de Google correcta."
            )

    guardar_token_atomicamente(dest_token, creds.to_json())
    print(f"[OK] Canal validado exitosamente: '{actual_title}' (ID: {actual_id})")
    print(f"[OK] Token guardado en: {dest_token}")

    return actual_id, actual_title, dest_token


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Autorizar canal de YouTube para métricas analíticas")
    parser.add_argument(
        "--canal",
        type=str,
        default="Código OcultoTV",
        help="Canal a autorizar: 'novelas' (Novelas Express MX) o 'codigo' (Código OcultoTV)",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=None,
        help="Ruta de destino opcional para guardar el token OAuth",
    )
    parser.add_argument(
        "--client-secrets",
        type=Path,
        default=CLIENT_SECRETS_FILE,
        help="Ruta al archivo client_secrets.json",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Puerto local para el servidor OAuth (default: 0 dinámico)",
    )

    args = parser.parse_args()

    try:
        autorizar_canal(
            canal=args.canal,
            client_secrets_path=args.client_secrets,
            token_salida=args.token,
            port=args.port,
        )
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
