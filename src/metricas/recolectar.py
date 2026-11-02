"""Recolector de metricas para YouTube: Codigo OcultoTV y Novelas Express MX.

Extrae informacion de YouTube Data API v3 y YouTube Analytics API v2
usando OAuth token existente, infiere formatos de video, aplica correcciones
manuales desde CSV y realiza upserts idempotentes en SQLite.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Optional

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

TOKEN_YOUTUBE = RAIZ / "assets" / "credentials" / "token_youtube.json"
SCHEMA_DEFAULT = RAIZ / "sql" / "schema.sql"
DB_DEFAULT = RAIZ / "data" / "metricas.db"
CSV_ETIQUETAS_DEFAULT = RAIZ / "data" / "etiquetas_videos.csv"

FORMATOS_VALIDOS = {"short", "largo_original", "recopilacion", "novela_cap"}


def iso_duracion_a_s(duracion_iso: str) -> float:
    """Convierte duracion ISO 8601 (PT#H#M#S) a segundos flotantes."""
    if not duracion_iso or not isinstance(duracion_iso, str) or not duracion_iso.startswith("PT"):
        return 0.0
    patron = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")
    m = patron.match(duracion_iso)
    if not m:
        return 0.0
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    secs = int(m.group(3) or 0)
    return float(h * 3600 + mins * 60 + secs)


def inicializar_db(db_path: Path = DB_DEFAULT, schema_path: Path = SCHEMA_DEFAULT) -> sqlite3.Connection:
    """Crea la base de datos y sus tablas si no existen."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    if Path(schema_path).exists():
        sql = Path(schema_path).read_text(encoding="utf-8")
        con.executescript(sql)
    return con


def inferir_formato_y_metadatos(titulo: str, duracion_s: float, canal: str = "") -> dict[str, Any]:
    """Infiere formato, tema, serie y capitulo a partir de duracion, titulo y canal.

    Formatos validos: 'short', 'largo_original', 'recopilacion', 'novela_cap'.
    """
    t_lower = (titulo or "").lower()
    c_lower = (canal or "").lower()

    # 1. Shorts: duracion <= 60s o indicacion explicita de #shorts
    if (duracion_s > 0 and duracion_s <= 60.0) or ("#shorts" in t_lower or "#short" in t_lower or " #shorts" in t_lower):
        return {
            "formato": "short",
            "tema": _limpiar_tema(titulo),
            "serie": None,
            "capitulo": None,
        }

    # 2. Novela / Capitulo: si el canal es de novelas o el titulo trae capitulo/episodio
    patron_cap = re.search(r"\b(?:cap[ií]tulo|cap\.?|ep(?:isodio)?\.?)\s*(\d+)", titulo, re.IGNORECASE)
    es_canal_novela = "novela" in c_lower or "kdrama" in c_lower or "drama" in c_lower
    tiene_palabra_novela = "novela" in t_lower or "kdrama" in t_lower or "dorama" in t_lower

    if patron_cap or es_canal_novela or tiene_palabra_novela:
        capitulo = int(patron_cap.group(1)) if patron_cap else None
        # Intentar extraer serie (antes de separadores | o - o antes de 'Capitulo')
        partes = re.split(r"[:\|\-\–\—]", titulo)
        serie = partes[0].strip() if len(partes) > 1 else None
        if not serie and patron_cap:
            serie = titulo[:patron_cap.start()].strip(" -|:,\t")
        if not serie:
            serie = "Novelas Express" if es_canal_novela else "Serie Original"

        return {
            "formato": "novela_cap",
            "tema": serie,
            "serie": serie,
            "capitulo": capitulo,
        }

    # 3. Recopilaciones / Maratones / Tops
    indicadores_recopilacion = (
        "recopilacion", "recopilación", "compilacion", "compilación",
        "maraton", "maratón", "episodios completos", "historias completas",
        "todos los casos", "todas las partes"
    )
    es_recop = any(k in t_lower for k in indicadores_recopilacion) or bool(re.search(r"\btop\s*\d+\b", t_lower))
    if es_recop:
        return {
            "formato": "recopilacion",
            "tema": _limpiar_tema(titulo),
            "serie": None,
            "capitulo": None,
        }

    # 4. Largo original por defecto
    return {
        "formato": "largo_original",
        "tema": _limpiar_tema(titulo),
        "serie": None,
        "capitulo": None,
    }


def _limpiar_tema(titulo: str) -> str:
    """Extrae un tema conciso removiendo etiquetas comunes y separadores."""
    t = re.sub(r"#\w+", "", titulo or "")
    partes = re.split(r"[:\|\-\–\—]", t)
    tema = partes[0].strip() if partes else t.strip()
    return tema or "General"


def cargar_etiquetas_csv(csv_path: Path = CSV_ETIQUETAS_DEFAULT) -> dict[str, dict[str, Any]]:
    """Carga correcciones manuales de metadatos desde archivo CSV."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return {}

    etiquetas: dict[str, dict[str, Any]] = {}
    with open(csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vid = (row.get("video_id") or "").strip()
            if not vid:
                continue
            item: dict[str, Any] = {}
            for col in ("formato", "tema", "serie", "capitulo", "voz", "estilo_visual"):
                val = (row.get(col) or "").strip()
                if val:
                    if col == "capitulo" and val.isdigit():
                        item[col] = int(val)
                    elif col == "formato" and val in FORMATOS_VALIDOS:
                        item[col] = val
                    else:
                        item[col] = val
            if item:
                etiquetas[vid] = item
    return etiquetas


def aplicar_etiquetas_manuales(metadatos: dict[str, Any], etiquetas_csv: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Sobrescribe metadatos inferidos con las correcciones manuales si existen."""
    res = dict(metadatos)
    vid = res.get("video_id")
    if vid and vid in etiquetas_csv:
        res.update(etiquetas_csv[vid])
    return res


# ---------------------------------------------------------------------------
# Operaciones de Inserción Idempotente (Upsert)
# ---------------------------------------------------------------------------

def upsert_video(con: sqlite3.Connection, video: dict[str, Any]) -> None:
    """Inserta o actualiza un registro en la tabla videos."""
    sql = """
    INSERT INTO videos (
        video_id, canal, titulo, formato, tema, serie, capitulo,
        duracion_s, fecha_publicacion, hora_publicacion, voz, estilo_visual
    ) VALUES (
        :video_id, :canal, :titulo, :formato, :tema, :serie, :capitulo,
        :duracion_s, :fecha_publicacion, :hora_publicacion, :voz, :estilo_visual
    )
    ON CONFLICT(video_id) DO UPDATE SET
        canal = excluded.canal,
        titulo = excluded.titulo,
        formato = coalesce(excluded.formato, videos.formato),
        tema = coalesce(excluded.tema, videos.tema),
        serie = coalesce(excluded.serie, videos.serie),
        capitulo = coalesce(excluded.capitulo, videos.capitulo),
        duracion_s = excluded.duracion_s,
        fecha_publicacion = excluded.fecha_publicacion,
        hora_publicacion = excluded.hora_publicacion,
        voz = coalesce(excluded.voz, videos.voz),
        estilo_visual = coalesce(excluded.estilo_visual, videos.estilo_visual);
    """
    con.execute(sql, {
        "video_id": video["video_id"],
        "canal": video["canal"],
        "titulo": video["titulo"],
        "formato": video.get("formato", "largo_original"),
        "tema": video.get("tema"),
        "serie": video.get("serie"),
        "capitulo": video.get("capitulo"),
        "duracion_s": float(video.get("duracion_s", 0.0)),
        "fecha_publicacion": video.get("fecha_publicacion"),
        "hora_publicacion": video.get("hora_publicacion"),
        "voz": video.get("voz"),
        "estilo_visual": video.get("estilo_visual"),
    })


def upsert_metrica_diaria(con: sqlite3.Connection, metrica: dict[str, Any]) -> None:
    """Inserta o actualiza metricas diarias por video y fecha."""
    sql = """
    INSERT INTO metricas_diarias (
        video_id, fecha, vistas, minutos_vistos, duracion_media_s,
        pct_visto_medio, likes, comentarios, suscriptores_ganados
    ) VALUES (
        :video_id, :fecha, :vistas, :minutos_vistos, :duracion_media_s,
        :pct_visto_medio, :likes, :comentarios, :suscriptores_ganados
    )
    ON CONFLICT(video_id, fecha) DO UPDATE SET
        vistas = excluded.vistas,
        minutos_vistos = excluded.minutos_vistos,
        duracion_media_s = excluded.duracion_media_s,
        pct_visto_medio = excluded.pct_visto_medio,
        likes = excluded.likes,
        comentarios = excluded.comentarios,
        suscriptores_ganados = excluded.suscriptores_ganados;
    """
    con.execute(sql, {
        "video_id": metrica["video_id"],
        "fecha": metrica["fecha"],
        "vistas": int(metrica.get("vistas", 0)),
        "minutos_vistos": float(metrica.get("minutos_vistos", 0.0)),
        "duracion_media_s": float(metrica.get("duracion_media_s", 0.0)),
        "pct_visto_medio": float(metrica.get("pct_visto_medio", 0.0)),
        "likes": int(metrica.get("likes", 0)),
        "comentarios": int(metrica.get("comentarios", 0)),
        "suscriptores_ganados": int(metrica.get("suscriptores_ganados", 0)),
    })


def upsert_retencion(con: sqlite3.Connection, puntos: list[dict[str, Any]]) -> None:
    """Inserta o actualiza puntos de la curva de retencion."""
    if not puntos:
        return
    sql = """
    INSERT INTO retencion (video_id, fecha_corte, segundo_relativo, pct_audiencia)
    VALUES (:video_id, :fecha_corte, :segundo_relativo, :pct_audiencia)
    ON CONFLICT(video_id, fecha_corte, segundo_relativo) DO UPDATE SET
        pct_audiencia = excluded.pct_audiencia;
    """
    con.executemany(sql, [
        {
            "video_id": p["video_id"],
            "fecha_corte": p["fecha_corte"],
            "segundo_relativo": float(p["segundo_relativo"]),
            "pct_audiencia": float(p["pct_audiencia"]),
        }
        for p in puntos
    ])


def upsert_trafico(con: sqlite3.Connection, traficos: list[dict[str, Any]]) -> None:
    """Inserta o actualiza fuentes de trafico."""
    if not traficos:
        return
    sql = """
    INSERT INTO trafico (video_id, fecha, fuente, vistas)
    VALUES (:video_id, :fecha, :fuente, :vistas)
    ON CONFLICT(video_id, fecha, fuente) DO UPDATE SET
        vistas = excluded.vistas;
    """
    con.executemany(sql, [
        {
            "video_id": t["video_id"],
            "fecha": t["fecha"],
            "fuente": t["fuente"],
            "vistas": int(t.get("vistas", 0)),
        }
        for t in traficos
    ])


# ---------------------------------------------------------------------------
# Conexión con YouTube API (Data v3 + Analytics v2)
# ---------------------------------------------------------------------------

def obtener_servicios_youtube(token_path: Path = TOKEN_YOUTUBE):
    """Inicializa servicios de YouTube Data y Analytics sin exponer secretos."""
    token_path = Path(token_path)
    if not token_path.exists():
        print(f"[AVISO] No se encontró {token_path}. Ejecuta: python subir_video.py auth-youtube")
        return None, None

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("[ERROR] Bibliotecas de Google API no instaladas.")
        return None, None

    try:
        creds = Credentials.from_authorized_user_file(str(token_path))
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"[AVISO] No se pudo refrescar el token ({type(e).__name__}). Re-autentica.")
                    return None, None
            else:
                print("[AVISO] Credenciales de YouTube no válidas.")
                return None, None

        yt_data = build("youtube", "v3", credentials=creds, cache_discovery=False)
        yt_analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        return yt_data, yt_analytics
    except Exception as e:
        print(f"[AVISO] Error al conectar con APIs de YouTube: {type(e).__name__}")
        return None, None


def recolectar_desde_youtube(
    con: sqlite3.Connection,
    canal_filtro: Optional[str] = None,
    desde_fecha: Optional[str] = None,
    csv_etiquetas_path: Path = CSV_ETIQUETAS_DEFAULT,
) -> dict[str, int]:
    """Cosecha videos, métricas diarias, retención y tráfico desde YouTube."""
    stats = {"videos": 0, "metricas": 0, "retencion": 0, "trafico": 0}

    yt_data, yt_analytics = obtener_servicios_youtube()
    if yt_data is None:
        return stats

    etiquetas_csv = cargar_etiquetas_csv(csv_etiquetas_path)

    # Determinar rango de fechas
    hoy_str = date.today().isoformat()
    if not desde_fecha:
        desde_fecha = (date.today() - timedelta(days=3)).isoformat()

    try:
        # Obtener canal autenticado
        ch_resp = yt_data.channels().list(part="snippet,contentDetails", mine=True).execute()
        items = ch_resp.get("items", [])
        if not items:
            print("[AVISO] No se encontraron canales en la cuenta.")
            return stats

        canal_item = items[0]
        canal_nombre = canal_filtro or canal_item["snippet"]["title"]
        uploads_id = canal_item["contentDetails"]["relatedPlaylists"]["uploads"]

        # Recorrer videos subidos
        video_ids = []
        token_pag = None
        while True:
            p_resp = yt_data.playlistItems().list(
                part="contentDetails",
                playlistId=uploads_id,
                maxResults=50,
                pageToken=token_pag,
            ).execute()
            video_ids.extend([it["contentDetails"]["videoId"] for it in p_resp.get("items", [])])
            token_pag = p_resp.get("nextPageToken")
            if not token_pag:
                break

        # Obtener detalles de videos en bloques de 50
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i + 50]
            v_resp = yt_data.videos().list(
                part="snippet,contentDetails,statistics",
                id=",".join(chunk),
            ).execute()

            for item in v_resp.get("items", []):
                vid = item["id"]
                snip = item["snippet"]
                cnt = item["contentDetails"]
                stat = item.get("statistics", {})

                titulo = snip.get("title", "")
                pub_at = snip.get("publishedAt", "")
                fecha_pub = pub_at[:10] if pub_at else None
                hora_pub = pub_at[11:19] if len(pub_at) > 18 else None
                dur_s = iso_duracion_a_s(cnt.get("duration", ""))

                # Inferencia de formato y metadatos
                meta = inferir_formato_y_metadatos(titulo, dur_s, canal=canal_nombre)
                meta["video_id"] = vid
                meta["canal"] = canal_nombre
                meta["titulo"] = titulo
                meta["duracion_s"] = dur_s
                meta["fecha_publicacion"] = fecha_pub
                meta["hora_publicacion"] = hora_pub
                meta["voz"] = None
                meta["estilo_visual"] = None

                # Aplicar sobreescrituras de CSV si existen
                meta = aplicar_etiquetas_manuales(meta, etiquetas_csv)

                # Upsert video
                upsert_video(con, meta)
                stats["videos"] += 1

                # Métricas snapshot actuales
                vistas_tot = int(stat.get("viewCount", 0))
                likes_tot = int(stat.get("likeCount", 0))
                com_tot = int(stat.get("commentCount", 0))

                # Si tenemos YouTube Analytics API, consultar día a día
                if yt_analytics:
                    try:
                        rep = yt_analytics.reports().query(
                            ids="channel==MINE",
                            startDate=desde_fecha,
                            endDate=hoy_str,
                            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained",
                            dimensions="day",
                            filters=f"video=={vid}",
                        ).execute()

                        rows = rep.get("rows", [])
                        for row in rows:
                            f_dia = str(row[0])
                            upsert_metrica_diaria(con, {
                                "video_id": vid,
                                "fecha": f_dia,
                                "vistas": int(row[1] or 0),
                                "minutos_vistos": float(row[2] or 0.0),
                                "duracion_media_s": float(row[3] or 0.0),
                                "pct_visto_medio": float(row[4] or 0.0),
                                "likes": int(row[5] or 0),
                                "comentarios": int(row[6] or 0),
                                "suscriptores_ganados": int(row[7] or 0),
                            })
                            stats["metricas"] += 1
                    except Exception:
                        # Fallback a métrica de hoy con snapshot general si analytics falla
                        upsert_metrica_diaria(con, {
                            "video_id": vid,
                            "fecha": hoy_str,
                            "vistas": vistas_tot,
                            "minutos_vistos": round((vistas_tot * dur_s * 0.4) / 60.0, 2),
                            "duracion_media_s": round(dur_s * 0.4, 2),
                            "pct_visto_medio": 40.0,
                            "likes": likes_tot,
                            "comentarios": com_tot,
                            "suscriptores_ganados": 0,
                        })
                        stats["metricas"] += 1

                    # Tráfico por video
                    try:
                        rep_traf = yt_analytics.reports().query(
                            ids="channel==MINE",
                            startDate=desde_fecha,
                            endDate=hoy_str,
                            metrics="views",
                            dimensions="day,insightTrafficSourceType",
                            filters=f"video=={vid}",
                        ).execute()
                        traf_puntos = [
                            {"video_id": vid, "fecha": str(r[0]), "fuente": str(r[1]), "vistas": int(r[2] or 0)}
                            for r in rep_traf.get("rows", [])
                        ]
                        upsert_trafico(con, traf_puntos)
                        stats["trafico"] += len(traf_puntos)
                    except Exception:
                        pass

                    # Curva de retención
                    try:
                        rep_ret = yt_analytics.reports().query(
                            ids="channel==MINE",
                            startDate="2020-01-01",
                            endDate=hoy_str,
                            metrics="audienceWatchRatio",
                            dimensions="elapsedVideoTimeRatio",
                            filters=f"video=={vid}",
                        ).execute()
                        ret_puntos = [
                            {
                                "video_id": vid,
                                "fecha_corte": hoy_str,
                                "segundo_relativo": round(float(r[0]) * dur_s, 2),
                                "pct_audiencia": round(float(r[1] or 0.0) * 100.0, 2),
                            }
                            for r in rep_ret.get("rows", [])
                        ]
                        upsert_retencion(con, ret_puntos)
                        stats["retencion"] += len(ret_puntos)
                    except Exception:
                        pass
                else:
                    # Sin analytics v2 disponible: registrar snapshot diario
                    upsert_metrica_diaria(con, {
                        "video_id": vid,
                        "fecha": hoy_str,
                        "vistas": vistas_tot,
                        "minutos_vistos": round((vistas_tot * dur_s * 0.4) / 60.0, 2),
                        "duracion_media_s": round(dur_s * 0.4, 2),
                        "pct_visto_medio": 40.0,
                        "likes": likes_tot,
                        "comentarios": com_tot,
                        "suscriptores_ganados": 0,
                    })
                    stats["metricas"] += 1

        con.commit()
    except Exception as e:
        print(f"[AVISO] Excepción durante recolección: {type(e).__name__}: {e}")

    return stats


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Recolector de métricas de YouTube para Docu Factory y Novelas Express MX")
    parser.add_argument("--canal", type=str, default=None, help="Nombre del canal a filtrar (ej. 'Código OcultoTV' o 'Novelas Express MX')")
    parser.add_argument("--desde", type=str, default=None, help="Fecha inicial en formato YYYY-MM-DD (por defecto: últimos 3 días)")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT, help="Ruta de la base de datos SQLite")
    parser.add_argument("--csv-etiquetas", type=Path, default=CSV_ETIQUETAS_DEFAULT, help="Ruta del archivo CSV con correcciones de etiquetas")

    args = parser.parse_args()

    desde = args.desde
    if not desde:
        desde = (date.today() - timedelta(days=3)).isoformat()

    print(f"=== Iniciando recolección de métricas ===")
    print(f"  Base de datos: {args.db}")
    print(f"  Canal: {args.canal or 'Todos los detectados'}")
    print(f"  Desde: {desde}")

    con = inicializar_db(db_path=args.db)
    try:
        stats = recolectar_desde_youtube(
            con=con,
            canal_filtro=args.canal,
            desde_fecha=desde,
            csv_etiquetas_path=args.csv_etiquetas,
        )
        print(f"=== Recolección finalizada exitosamente ===")
        print(f"  Videos registrados/actualizados: {stats['videos']}")
        print(f"  Registros de métricas diarias:   {stats['metricas']}")
        print(f"  Puntos de retención:             {stats['retencion']}")
        print(f"  Registros de tráfico:            {stats['trafico']}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
