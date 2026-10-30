"""Modulo de sincronizacion y consulta de analiticas para Docu Factory.

Sincroniza metricas desde YouTube Analytics API, YouTube Data API v3,
y prepara la integracion para Facebook Graph API y TikTok Display API.
Registra el desempeno diario, curvas de retencion y feedback en SQLite.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import sys
from typing import Any, Optional
from difflib import SequenceMatcher

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from datos.db import (
    DB_PATH,
    obtener_conexion,
    guardar_publicacion,
    guardar_analitica_diaria,
    guardar_curva_retencion,
    guardar_comentarios,
)

TOKEN_YOUTUBE = RAIZ / "assets" / "credentials" / "token_youtube.json"
DIR_REPORTES = RAIZ / "reportes"
DIR_CONSULTAS = RAIZ / "datos" / "consultas"


# ---------------------------------------------------------------------------
# Clasificacion de Sentimiento y Peticiones en Comentarios
# ---------------------------------------------------------------------------

PALABRAS_POSITIVAS = {
    "excelente", "increible", "increíble", "buenisimo", "buenísimo", "buen video",
    "genial", "fascinante", "gran video", "crack", "felicidades", "maravilla",
    "me encanto", "me encantó", "me gusto", "me gustó", "buen trabajo", "amo este canal",
    "muy bueno", "calidad", "interesante", "temazo", "wow", "brutal", "gracias",
    "suscrito", "nuevo sub", "obra de arte", "top", "sigan asi", "sigan así",
}

PALABRAS_NEGATIVAS = {
    "aburrido", "malisimo", "malísimo", "pesimo", "pésimo", "mentira", "falso",
    "fake", "clickbait", "desinformacion", "desinformación", "horrible", "basura",
    "cringe", "perdida de tiempo", "pérdida de tiempo", "no me gusto", "no me gustó",
    "malo", "estafa", "decepcion", "decepción", "asco", "terrible", "mediocre",
}

PATRONES_PARTE_2 = [
    re.compile(r"\b(parte\s*2|parte\s*dos|segunda\s*parte|part\s*2|pt\.?\s*2|siguiente\s*parte|otra\s*parte)\b", re.IGNORECASE),
    re.compile(r"\b(continuaci[oó]n|segundo\s*video|segunda\s*entrega)\b", re.IGNORECASE),
    re.compile(r"\b(haz\s+(la\s+)?segunda|para\s+la\s+segunda|esperando\s+la\s+parte\s*2|necesito\s+parte\s*2|habr[aá]\s+parte\s*2)\b", re.IGNORECASE),
]

PATRONES_TEMA = [
    re.compile(r"(?:haz|hagan|puedes hacer|podr[ií]as hacer|habla|hagan un video|haz un video|haz uno)\s+(?:de|sobre|acerca de)\s+([^!?\.\n]{4,80})", re.IGNORECASE),
    re.compile(r"(?:para el pr[oó]ximo|para la pr[oó]xima|el siguiente que sea de)\s+([^!?\.\n]{4,80})", re.IGNORECASE),
    re.compile(r"(?:deber[ií]as hablar de|te falt[oó] hablar de)\s+([^!?\.\n]{4,80})", re.IGNORECASE),
]


def clasificar_sentimiento(texto: str) -> str:
    """Clasifica el sentimiento del comentario en '+' (positivo), '-' (negativo) o '=' (neutro)."""
    t = texto.lower()
    score_pos = sum(1 for p in PALABRAS_POSITIVAS if p in t)
    score_neg = sum(1 for p in PALABRAS_NEGATIVAS if p in t)
    if score_pos > score_neg:
        return "+"
    elif score_neg > score_pos:
        return "-"
    return "="


def detectar_pide_segunda_parte(texto: str) -> bool:
    """Detecta si el comentario solicita una continuación o segunda parte."""
    for p in PATRONES_PARTE_2:
        if p.search(texto):
            return True
    return False


def detectar_tema_sugerido(texto: str) -> Optional[str]:
    """Extrae un tema sugerido por la audiencia si está presente en el comentario."""
    for p in PATRONES_TEMA:
        m = p.search(texto)
        if m:
            tema = m.group(1).strip()
            # Limpiar puntuación final
            tema = re.sub(r"[,\.?!;]+$", "", tema).strip()
            if 3 < len(tema) <= 60:
                return tema
    return None


def similitud_titulos(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


# ---------------------------------------------------------------------------
# Sincronización con YouTube (Data API v3 y Analytics API v2)
# ---------------------------------------------------------------------------

def obtener_servicios_youtube():
    """Inicializa clientes de YouTube Data v3 y YouTube Analytics v2 de forma segura."""
    if not TOKEN_YOUTUBE.exists():
        print(f"[AVISO] No se encontró el archivo de credenciales {TOKEN_YOUTUBE}")
        print("        Ejecuta: python subir_video.py auth-youtube")
        return None, None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("[ERROR] Falta instalar google-api-python-client google-auth-oauthlib")
        return None, None

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_YOUTUBE))
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"[AVISO] No se pudo refrescar el token de YouTube ({e}).")
                    print("        Ejecuta: python subir_video.py auth-youtube")
                    return None, None
            else:
                print("[AVISO] Credenciales de YouTube no válidas.")
                return None, None

        yt_data = build("youtube", "v3", credentials=creds, cache_discovery=False)
        yt_analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        return yt_data, yt_analytics
    except Exception as e:
        print(f"[AVISO] Error al inicializar APIs de YouTube: {e}")
        return None, None


def actualizar_youtube(dias: int = 30, video_filtro: Optional[str] = None) -> dict[str, int]:
    """Descarga analíticas, curvas de retención y comentarios desde YouTube."""
    con = obtener_conexion()
    stats = {"videos_procesados": 0, "analiticas_guardadas": 0, "curvas_guardadas": 0, "comentarios_guardados": 0}

    yt_data, yt_analytics = obtener_servicios_youtube()
    if yt_data is None:
        con.close()
        return stats

    try:
        # 1. Obtener lista de videos del canal
        ch = yt_data.channels().list(part="contentDetails", mine=True).execute()["items"][0]
        uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

        yt_video_items = []
        tok = None
        while True:
            r = yt_data.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50, pageToken=tok).execute()
            ids = [i["contentDetails"]["videoId"] for i in r.get("items", [])]
            if ids:
                for chunk in [ids[i:i + 50] for i in range(0, len(ids), 50)]:
                    detalles = yt_data.videos().list(
                        part="snippet,status,contentDetails,statistics",
                        id=",".join(chunk),
                    ).execute()
                    yt_video_items.extend(detalles.get("items", []))
            tok = r.get("nextPageToken")
            if not tok:
                break

        # Obtener mapa de videos locales de la base
        cur_v = con.execute("SELECT id, slug, titulo, formato FROM videos")
        videos_locales = [dict(row) for row in cur_v.fetchall()]

        # Obtener publicaciones existentes
        cur_p = con.execute("SELECT id, video_id, url, video_platform_id FROM publicaciones WHERE plataforma = 'youtube'")
        pubs_por_yt_id = {row["video_platform_id"]: row["video_id"] for row in cur_p.fetchall() if row["video_platform_id"]}

        fecha_fin = date.today().isoformat()
        fecha_inicio = (date.today() - timedelta(days=dias)).isoformat()

        for item in yt_video_items:
            yt_id = item["id"]
            titulo = item["snippet"]["title"]
            pub_at = item["snippet"]["publishedAt"]
            privacy = item["status"].get("privacyStatus", "public")
            st = item.get("statistics", {})

            vistas = int(st.get("viewCount", 0))
            likes = int(st.get("likeCount", 0))
            n_comentarios = int(st.get("commentCount", 0))

            # Determinar video_id local correspondiente
            video_id_local = pubs_por_yt_id.get(yt_id)
            if not video_id_local:
                # Intentar emparejar por similitud de título
                mejor_match = None
                mejor_score = 0.0
                for vl in videos_locales:
                    sc = similitud_titulos(titulo, vl.get("titulo") or vl.get("slug"))
                    if sc > mejor_score:
                        mejor_score = sc
                        mejor_match = vl["id"]

                if mejor_score >= 0.55 and mejor_match:
                    video_id_local = mejor_match
                    guardar_publicacion({
                        "video_id": video_id_local,
                        "plataforma": "youtube",
                        "url": f"https://youtu.be/{yt_id}",
                        "fecha_hora_publicacion": pub_at,
                        "estado": "publico" if privacy == "public" else "oculto",
                        "video_platform_id": yt_id,
                    }, con=con)

            if not video_id_local:
                continue

            if video_filtro and video_filtro not in (video_id_local, yt_id):
                continue

            stats["videos_procesados"] += 1

            # 2. Consultar YouTube Analytics API
            retencion_promedio = 0.0
            subs_ganados = 0
            shares = 0
            fuentes_dict: dict[str, int] = {}
            puntos_curva: list[tuple[float, float]] = []

            if yt_analytics:
                try:
                    rep = yt_analytics.reports().query(
                        ids="channel==MINE",
                        startDate=fecha_inicio,
                        endDate=fecha_fin,
                        metrics="averageViewPercentage,subscribersGained,shares",
                        filters=f"video=={yt_id}",
                    ).execute()
                    rows = rep.get("rows", [])
                    if rows:
                        retencion_promedio = float(rows[0][0] or 0.0)
                        subs_ganados = int(rows[0][1] or 0)
                        shares = int(rows[0][2] or 0)
                except Exception as e:
                    # En videos muy recientes o sin datos analytics suficientes
                    pass

                # Fuentes de tráfico
                try:
                    rep_trafico = yt_analytics.reports().query(
                        ids="channel==MINE",
                        startDate=fecha_inicio,
                        endDate=fecha_fin,
                        metrics="views",
                        dimensions="insightTrafficSourceType",
                        filters=f"video=={yt_id}",
                    ).execute()
                    for r_row in rep_trafico.get("rows", []):
                        fuentes_dict[str(r_row[0])] = int(r_row[1] or 0)
                except Exception:
                    pass

                # Curva de retención (elapsedVideoTimeRatio)
                try:
                    rep_ret = yt_analytics.reports().query(
                        ids="channel==MINE",
                        startDate="2020-01-01",
                        endDate=fecha_fin,
                        metrics="audienceWatchRatio",
                        dimensions="elapsedVideoTimeRatio",
                        filters=f"video=={yt_id}",
                    ).execute()
                    for r_row in rep_ret.get("rows", []):
                        ratio_pct = round(float(r_row[0]) * 100, 2)
                        aud_rel = float(r_row[1] or 0.0)
                        puntos_curva.append((ratio_pct, aud_rel))
                except Exception:
                    pass

            # Calcular estimación de pct_pasa_3s a partir de la curva si está disponible
            pct_pasa_3s = 0.0
            if puntos_curva:
                # Buscar punto cercano a los primeros 3 segundos o ~5%
                candidatos = [p for p in puntos_curva if p[0] <= 10.0]
                if candidatos:
                    pct_pasa_3s = candidatos[-1][1] * 100

            # Guardar analitica diaria para hoy
            guardar_analitica_diaria({
                "video_id": video_id_local,
                "plataforma": "youtube",
                "fecha": date.today().isoformat(),
                "vistas": vistas,
                "retencion_promedio_pct": retencion_promedio,
                "pct_pasa_3s": round(pct_pasa_3s, 2),
                "likes": likes,
                "comentarios": n_comentarios,
                "compartidos": shares,
                "ctr_miniatura": 0.0,
                "suscriptores_ganados": subs_ganados,
                "fuentes_trafico": fuentes_dict,
            }, con=con)
            stats["analiticas_guardadas"] += 1

            # Guardar curva de retención si hubo datos
            if puntos_curva:
                guardar_curva_retencion(video_id_local, "youtube", puntos_curva, con=con)
                stats["curvas_guardadas"] += 1

            # 3. Descargar comentarios del video
            try:
                r_com = yt_data.commentThreads().list(
                    part="snippet",
                    videoId=yt_id,
                    maxResults=50,
                    textFormat="plainText",
                    order="time",
                ).execute()

                comentarios_a_guardar = []
                for item_c in r_com.get("items", []):
                    top = item_c["snippet"]["topLevelComment"]["snippet"]
                    txt = top.get("textDisplay") or ""
                    cid = item_c["id"]
                    f_com = top.get("publishedAt", "")[:10]

                    comentarios_a_guardar.append({
                        "video_id": video_id_local,
                        "plataforma": "youtube",
                        "fecha": f_com,
                        "texto": txt,
                        "sentimiento": clasificar_sentimiento(txt),
                        "pide_segunda_parte": detectar_pide_segunda_parte(txt),
                        "tema_sugerido": detectar_tema_sugerido(txt),
                        "comment_id": cid,
                    })

                n_ins = guardar_comentarios(comentarios_a_guardar, con=con)
                stats["comentarios_guardados"] += n_ins
            except Exception as e:
                # Comentarios desactivados o error de quota
                pass

        con.commit()
    finally:
        con.close()

    return stats


# ---------------------------------------------------------------------------
# Stubs de Plataformas Adicionales (Facebook Graph API y TikTok Display API)
# ---------------------------------------------------------------------------

def actualizar_facebook(video_filtro: Optional[str] = None) -> dict[str, int]:
    """Stub documentado para sincronizar analiticas de Facebook Page y Reels.

    Integracion futura con Meta Graph API:
    - Endpoint Video Insights:
      GET https://graph.facebook.com/v19.0/{video-id}/video_insights?metric=total_video_views,total_video_avg_time_watched,total_video_impressions,total_video_reactions_by_type_total
    - Autenticacion:
      Requiere FB_PAGE_ACCESS_TOKEN con permisos pages_read_engagement y read_insights.
    """
    con = obtener_conexion()
    try:
        cur = con.execute("SELECT count(*) as total FROM publicaciones WHERE plataforma in ('fb_pagina', 'fb_perfil')")
        total = cur.fetchone()["total"]
    finally:
        con.close()

    if total == 0:
        print("[INFO] Facebook: No hay publicaciones registradas para sincronizar.")
    else:
        print(f"[INFO] Facebook: {total} publicaciones registradas. Sincronización pendiente de FB_PAGE_ACCESS_TOKEN.")
    return {"videos_procesados": 0}


def actualizar_tiktok(video_filtro: Optional[str] = None) -> dict[str, int]:
    """Stub documentado para sincronizar analiticas de TikTok Videos.

    Integracion futura con TikTok Display API / Commercial Content API:
    - Endpoint Video Query:
      POST https://open.tiktokapis.com/v2/video/query/?fields=id,like_count,comment_count,share_count,view_count
    - Autenticacion:
      Requiere TIKTOK_ACCESS_TOKEN obtenido por flujo OAuth 2.0 con scope video.list.
    """
    con = obtener_conexion()
    try:
        cur = con.execute("SELECT count(*) as total FROM publicaciones WHERE plataforma = 'tiktok'")
        total = cur.fetchone()["total"]
    finally:
        con.close()

    if total == 0:
        print("[INFO] TikTok: No hay publicaciones registradas para sincronizar.")
    else:
        print(f"[INFO] TikTok: {total} publicaciones registradas. Sincronización pendiente de TIKTOK_ACCESS_TOKEN.")
    return {"videos_procesados": 0}


# ---------------------------------------------------------------------------
# Generador de Reportes y Exportación CSV
# ---------------------------------------------------------------------------

def ejecutar_consulta_sql(ruta_sql: Path, con: Any) -> tuple[list[str], list[list[Any]]]:
    """Ejecuta un archivo .sql y devuelve nombres de columnas y filas de resultados."""
    if not ruta_sql.exists():
        return [], []
    sql = ruta_sql.read_text(encoding="utf-8")
    # Remover posibles comentarios antes de la sentencia principal
    cur = con.execute(sql)
    columnas = [d[0] for d in cur.description] if cur.description else []
    filas = [list(r) for r in cur.fetchall()]
    return columnas, filas


def generar_reporte(formato: str = "ambos", salida_dir: Optional[Path] = None) -> None:
    """Ejecuta las consultas analiticas de datos/consultas/ y muestra/exporta el reporte."""
    con = obtener_conexion()
    salida = salida_dir or DIR_REPORTES
    salida.mkdir(parents=True, exist_ok=True)
    fecha_hoy = date.today().strftime("%Y%m%d")

    archivos_sql = sorted(DIR_CONSULTAS.glob("*.sql"))
    if not archivos_sql:
        print(f"[AVISO] No se encontraron archivos .sql en {DIR_CONSULTAS}")
        con.close()
        return

    csv_lineas = []
    print("=" * 80)
    print("         DOCU FACTORY - REPORTE ANALÍTICO DE RENDIMIENTO")
    print(f"         Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    for ruta in archivos_sql:
        nombre = ruta.stem
        try:
            columnas, filas = ejecutar_consulta_sql(ruta, con)
        except Exception as e:
            print(f"\n[ERROR] Al ejecutar {ruta.name}: {e}")
            continue

        print(f"\n--- {nombre.upper().replace('_', ' ')} ({len(filas)} registros) ---")
        if not filas:
            print("  (Sin datos suficientes)")
            continue

        # Formato de visualización en consola tipo tabla compacta
        # Ancho por columna
        col_widths = [max(len(str(col)), max(len(str(f[i] if f[i] is not None else "")) for f in filas)) for i, col in enumerate(columnas)]
        col_widths = [min(w, 40) for w in col_widths]  # limitar ancho

        header_str = " | ".join(str(col)[:col_widths[i]].ljust(col_widths[i]) for i, col in enumerate(columnas))
        print("  " + header_str)
        print("  " + "-+-".join("-" * col_widths[i] for i in range(len(columnas))))

        for fila in filas[:15]:  # Muestra máxima de 15 filas en consola
            row_str = " | ".join(str(fila[i] if fila[i] is not None else "")[:col_widths[i]].ljust(col_widths[i]) for i in range(len(columnas)))
            print("  " + row_str)
        if len(filas) > 15:
            print(f"  ... (+ {len(filas) - 15} filas más)")

        # Preparar para CSV
        csv_lineas.append(f"# {nombre}")
        csv_lineas.append(",".join(f'"{col}"' for col in columnas))
        for fila in filas:
            csv_lineas.append(",".join(f'"{str(val if val is not None else "").replace(chr(34), chr(39))}"' for val in fila))
        csv_lineas.append("")

    con.close()

    if formato in ("csv", "ambos"):
        archivo_csv = salida / f"analiticas_{fecha_hoy}.csv"
        archivo_csv.write_text("\n".join(csv_lineas), encoding="utf-8")
        print(f"\n[OK] Reporte exportado a CSV: {archivo_csv}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Gestor de analiticas y reportes de Docu Factory")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    # Subcomando: actualizar
    p_act = subparsers.add_parser("actualizar", help="Descarga metricas reales desde YouTube, FB y TikTok")
    p_act.add_argument("--dias", type=int, default=30, help="Dias de historial a sincronizar (default: 30)")
    p_act.add_argument("--plataforma", choices=["todas", "youtube", "facebook", "tiktok"], default="todas", help="Plataforma a actualizar")
    p_act.add_argument("--video", type=str, default=None, help="Filtrar por video_id especifico")

    # Subcomando: reporte
    p_rep = subparsers.add_parser("reporte", help="Ejecuta consultas analiticas y exporta a consola y CSV")
    p_rep.add_argument("--formato", choices=["consola", "csv", "ambos"], default="ambos", help="Formato de salida")
    p_rep.add_argument("--salida", type=Path, default=DIR_REPORTES, help="Directorio para guardar el CSV")

    args = parser.parse_args()

    if args.comando == "actualizar":
        print(f"=== Actualizando analíticas (Plataforma: {args.plataforma}, Dias: {args.dias}) ===")
        if args.plataforma in ("todas", "youtube"):
            st_yt = actualizar_youtube(dias=args.dias, video_filtro=args.video)
            print(f"[YouTube] Procesados: {st_yt['videos_procesados']} videos | Analíticas: {st_yt['analiticas_guardadas']} | Curvas: {st_yt['curvas_guardadas']} | Comentarios: {st_yt['comentarios_guardados']}")
        if args.plataforma in ("todas", "facebook"):
            actualizar_facebook(video_filtro=args.video)
        if args.plataforma in ("todas", "tiktok"):
            actualizar_tiktok(video_filtro=args.video)
        print("=== Actualización finalizada ===")

    elif args.comando == "reporte":
        generar_reporte(formato=args.formato, salida_dir=args.salida)


if __name__ == "__main__":
    main()
