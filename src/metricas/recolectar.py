"""Recolector de metricas para YouTube: Codigo OcultoTV y Novelas Express MX.

Extrae informacion de YouTube Data API v3 y YouTube Analytics API v2
usando OAuth token correspondiente por canal, infiere formatos de video con reglas
estrictas, clasifica temas por diccionario de categorias, convierte horas a America/Merida,
aplica correcciones manuales desde CSV y realiza upserts idempotentes en SQLite.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from typing import Any, Optional
import wave

try:
    from zoneinfo import ZoneInfo
    TZ_MERIDA = ZoneInfo("America/Merida")
except Exception:
    # Merida es UTC-6 fijo
    TZ_MERIDA = timezone(timedelta(hours=-6))

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

TOKEN_CODIGO = RAIZ / "assets" / "credentials" / "token_youtube.json"
TOKEN_NOVELAS = RAIZ / "assets" / "credentials" / "token_youtube_novelas.json"
SCHEMA_DEFAULT = RAIZ / "sql" / "schema.sql"
DB_DEFAULT = RAIZ / "data" / "metricas.db"
CSV_ETIQUETAS_DEFAULT = RAIZ / "data" / "etiquetas_videos.csv"

NOVELAS_CHANNEL_ID = "UC8O5Zv0nsHRfaXij9uJNYbg"

MAPA_CANAL_TOKEN = {
    "Código OcultoTV": TOKEN_CODIGO,
    "Codigo OcultoTV": TOKEN_CODIGO,
    "Novelas Express MX": TOKEN_NOVELAS,
    "Novelas Express": TOKEN_NOVELAS,
}

FORMATOS_VALIDOS = {"short", "largo_original", "recopilacion", "novela_cap"}

CATEGORIAS_TEMAS = [
    "muerte_mx",
    "novela",
    "crimen",
    "reality",
    "viral",
    "paranormal",
    "leyenda",
    "religión",
    "historia",
    "tecnologia",
]

DICCIONARIO_TEMAS_REGEX = {
    "muerte_mx": [
        re.compile(p, re.IGNORECASE) for p in [
            r"\bmictl\w*", r"\bmuertos?\b", r"\bofrendas?\b", r"\bcementerios?\b",
            r"\bcatrinas?\b", r"\bxolo\w*", r"\b[aá]nimas?\b"
        ]
    ],
    "novela": [
        re.compile(p, re.IGNORECASE) for p in [
            r"\bnovela\b", r"\bkdrama\b", r"\bdorama\b", r"\bcap[ií]tulo\b", r"\bcap\.?\b",
            r"\bepisodio\b", r"\btelenovela\b", r"\bserie\b", r"\bromance\b"
        ]
    ],
    "crimen": [
        re.compile(p, re.IGNORECASE) for p in [
            r"\bcrimen\b", r"\basesin\w*", r"\bhomicid\w*", r"\bnarco\w*", r"\bc[aá]rtel\b",
            r"\bprisi[oó]n\b", r"\bc[aá]rcel\b", r"\brobo\b", r"\bpolic[ií]a\b", r"\bdelito\b",
            r"\bjuicio\b", r"\bforense\b", r"\bcondena\b", r"\bdesaparici[oó]n\b", r"\bsecuestr\w*",
            r"\bculpable\b", r"\binocente\b", r"\bdiddy\b", r"\bsean diddy\b"
        ]
    ],
    "reality": [
        re.compile(p, re.IGNORECASE) for p in [
            r"\breality\b", r"\bacapulco shore\b", r"\bcasa de los famosos\b", r"\bpol[eé]mica\b",
            r"\besc[aá]ndalo\b", r"\bpelea\b", r"\binfluencer\w*", r"\bchisme\w*", r"\bfar[aá]ndula\b",
            r"\bdesplante\b", r"\ben vivo\b", r"\bconcierto\b", r"\bgranja vip\b", r"\bla granja\b",
            r"\bram[oó]n ayala\b", r"\bayala\b", r"\bnatanael cano\b", r"\bbogueto\b", r"\bjosi cuen\b",
            r"\bmanelyk\b", r"\bsydney sweeney\b"
        ]
    ],
    "paranormal": [
        re.compile(p, re.IGNORECASE) for p in [
            r"\bparanormal\w*", r"\bfantasma\w*", r"\bovni\b", r"\bufo\b", r"\bextraterrestre\w*",
            r"\balien\w*", r"\bdemonio\w*", r"\bposesi[oó]n\b", r"\bexorcismo\b", r"\bmisterio\w*",
            r"\baparici[oó]n\b", r"\bente\b", r"\bouija\b", r"\bterror\b", r"\bespectro\b",
            r"\bpoltergeist\b", r"\benigma\w*", r"\baterrador\w*", r"\btenebros\w*", r"\bperturbador\w*"
        ]
    ],
    "leyenda": [
        re.compile(p, re.IGNORECASE) for p in [
            r"\bleyenda\w*", r"\bmito\w*", r"\bfolclor\w*", r"\bcriptozoolog[ií]a\b", r"\bnahual\w*",
            r"\bchupacabras\b", r"\bmonstruo\w*", r"\bmaldici[oó]n\b", r"\burbana\b", r"\bla llorona\b",
            r"\bpascualita\b"
        ]
    ],
    "religión": [
        re.compile(p, re.IGNORECASE) for p in [
            r"\breligi[oó]n\b", r"\bbiblia\b", r"\bb[ií]blico\w*", r"\bdios\b", r"\biglesia\b",
            r"\bvaticano\b", r"\bpapas?\b", r"\bsanto\w*", r"\bapocalipsis\b", r"\bprofec[ií]a\w*",
            r"\bmilagro\w*", r"\bjes[uú]s\b", r"\bcristo\b", r"\bfe\b", r"\bsagradas?\b",
            r"\barca de no[eé]\b", r"\bno[eé]\b", r"\barca\b"
        ]
    ],
    "historia": [
        re.compile(p, re.IGNORECASE) for p in [
            r"\bhistoria\w*", r"\bhist[oó]rico\w*", r"\bguerra\w*", r"\bimperio\w*", r"\brevoluci[oó]n\b",
            r"\bsiglo\b", r"\barqueolog[ií]a\b", r"\bantiguo\w*", r"\bmaya\w*", r"\begipto\b",
            r"\bcivilizaci[oó]n\b", r"\binvento\w*", r"\btransistor\b"
        ]
    ],
    "tecnologia": [
        re.compile(p, re.IGNORECASE) for p in [
            r"\btecnolog[ií]a\w*", r"\btecnol[oó]gic\w*", r"\benjambres?\b", r"\binteligencia artificial\b",
            r"\bia\b", r"\brobot\w*", r"\bciber\w*", r"\bcu[aá]ntic\w*", r"\bcomputaci[oó]n\b", r"\baut[oó]nom\w*"
        ]
    ],
    "viral": [
        re.compile(p, re.IGNORECASE) for p in [
            r"\bviral\b", r"\breal o ia\b", r"\bburro\w*", r"\btrend\w*", r"\btiktok\w*"
        ]
    ],
}


def _fecha_local(fmt: str, val: Any) -> Optional[str]:
    """Función SQL fecha_local(formato, fecha) para soporte nativo de semanas ISO (%G-%V)."""
    if not val:
        return None
    try:
        s = str(val)[:10]
        dt = date.fromisoformat(s)
        return dt.strftime(fmt)
    except Exception:
        return None


def guardar_token_atomicamente(token_file: Path, creds_json: str) -> None:
    """Escribe a un archivo temporal y luego renombra atómicamente. Nunca toca token_youtube.bak.json."""
    token_file = Path(token_file)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = token_file.with_name(f".tmp_{token_file.stem}_{os.getpid()}.json")
    try:
        temp_file.write_text(creds_json, encoding="utf-8")
        temp_file.replace(token_file)
    except Exception:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        raise


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


def convertir_a_merida(iso_utc_str: str) -> tuple[Optional[str], Optional[str]]:
    """Convierte una marca temporal ISO UTC (publishedAt) a fecha y hora en America/Merida."""
    if not iso_utc_str:
        return None, None
    try:
        s = iso_utc_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(s)
        dt_merida = dt_utc.astimezone(TZ_MERIDA)
        return dt_merida.strftime("%Y-%m-%d"), dt_merida.strftime("%H:%M:%S")
    except Exception:
        return iso_utc_str[:10], iso_utc_str[11:19] if len(iso_utc_str) > 18 else None


def clasificar_tema(titulo: str, canal: str = "", tema_csv: str = "") -> str:
    """Asigna la categoría del tema según CSV o diccionario de palabras clave.

    Categorías válidas: muerte_mx, leyenda, paranormal, religión, crimen, reality, historia, novela.
    Nunca retorna el título bruto.
    """
    if tema_csv and tema_csv.strip():
        return tema_csv.strip()

    c_lower = (canal or "").lower()
    t_lower = (titulo or "").lower()

    if "novela" in c_lower:
        return "novela"

    for cat in CATEGORIAS_TEMAS:
        for reg in DICCIONARIO_TEMAS_REGEX[cat]:
            if reg.search(t_lower):
                return cat

    return "novela" if "novela" in c_lower else "otro"


def inferir_formato_y_metadatos(
    titulo: str,
    duracion_s: float,
    canal: str = "",
    es_vertical: bool = False,
    formato_csv: str = "",
    tema_csv: str = "",
    serie_csv: str = "",
    capitulo_csv: Optional[int] = None,
) -> dict[str, Any]:
    """Infiere formato, tema, serie y capitulo con reglas estrictas:

    1. recopilacion: SOLO desde CSV o si el titulo trae exactamente '[Recopilación]' (nunca por 'Top N').
    2. novela_cap: EN EL CANAL NOVELAS EXPRESS MX se clasifica ANTES de la regla de Short (<=180 s).
    3. short: duracion <= 180 s o es vertical (aspecto 9:16 o #shorts) en otros canales.
    4. largo_original: resto de videos.
    """
    t_lower = (titulo or "").lower()
    c_lower = (canal or "").lower()
    es_canal_novela = "novela" in c_lower

    # 1. Recopilación: ÚNICAMENTE si viene en CSV o trae etiqueta explícita [Recopilación]
    tiene_tag_recopilacion = bool(re.search(r"\[recopilaci[oó]n\]", titulo or "", re.IGNORECASE))
    if formato_csv == "recopilacion" or tiene_tag_recopilacion:
        formato = "recopilacion"
        tema = clasificar_tema(titulo, canal, tema_csv)
        return {
            "formato": formato,
            "tema": tema,
            "serie": serie_csv or None,
            "capitulo": capitulo_csv,
        }

    # 2. Novela Cap: En Novelas Express MX, se clasifica ANTES de la regla de Short (<=180 s)
    if es_canal_novela:
        formato = "novela_cap"
        tema = clasificar_tema(titulo, canal, tema_csv)
        patron_cap = re.search(r"\b(?:cap[ií]tulo|cap\.?|ep(?:isodio)?\.?)\s*(\d+)", titulo, re.IGNORECASE)
        cap = capitulo_csv if capitulo_csv is not None else (int(patron_cap.group(1)) if patron_cap else None)
        serie = serie_csv
        if not serie:
            partes = re.split(r"[:\|\-\–\—]", titulo)
            serie = partes[0].strip() if len(partes) > 1 else None
            if not serie and patron_cap:
                serie = titulo[:patron_cap.start()].strip(" -|:,\t")
            if not serie:
                serie = "Novelas Express"
        return {
            "formato": formato,
            "tema": tema,
            "serie": serie,
            "capitulo": cap,
        }

    # 3. Short: duracion <= 180s o vertical
    tiene_hashtag_short = bool(re.search(r"#shorts?\b", t_lower))
    if (duracion_s > 0 and duracion_s <= 180.0) or es_vertical or tiene_hashtag_short:
        formato = "short"
        tema = clasificar_tema(titulo, canal, tema_csv)
        return {
            "formato": formato,
            "tema": tema,
            "serie": serie_csv or None,
            "capitulo": capitulo_csv,
        }

    # 4. Largo original por defecto
    formato = formato_csv if formato_csv in FORMATOS_VALIDOS else "largo_original"
    tema = clasificar_tema(titulo, canal, tema_csv)
    return {
        "formato": formato,
        "tema": tema,
        "serie": serie_csv or None,
        "capitulo": capitulo_csv,
    }


def inicializar_db(db_path: Path = DB_DEFAULT, schema_path: Path = SCHEMA_DEFAULT) -> sqlite3.Connection:
    """Crea la base de datos y sus tablas si no existen."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    con.create_function("fecha_local", 2, _fecha_local)
    if Path(schema_path).exists():
        sql = Path(schema_path).read_text(encoding="utf-8")
        con.executescript(sql)
    return con


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
    """Inserta o actualiza metricas diarias reales (nunca datos inventados)."""
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


def upsert_escenas(con: sqlite3.Connection, video_id: str, lista_escenas: list[dict[str, Any]]) -> None:
    """Inserta o actualiza las escenas con tiempos para cruzarlas con la curva de retención."""
    if not lista_escenas:
        return
    sql = """
    INSERT INTO escenas (video_id, n_escena, inicio_s, fin_s, texto, broll_fuente)
    VALUES (:video_id, :n_escena, :inicio_s, :fin_s, :texto, :broll_fuente)
    ON CONFLICT(video_id, n_escena) DO UPDATE SET
        inicio_s = excluded.inicio_s,
        fin_s = excluded.fin_s,
        texto = excluded.texto,
        broll_fuente = excluded.broll_fuente;
    """
    con.executemany(sql, [
        {
            "video_id": video_id,
            "n_escena": int(e.get("n_escena", 1)),
            "inicio_s": round(float(e.get("inicio_s", 0.0)), 2),
            "fin_s": round(float(e.get("fin_s", 0.0)), 2),
            "texto": e.get("texto") or "",
            "broll_fuente": e.get("broll_fuente") or "",
        }
        for e in lista_escenas
    ])


REGEX_PUBLICADO_YT = re.compile(r"(?:youtu\.be/|shorts/|v=)([A-Za-z0-9_-]{11})")


def _obtener_duracion_archivo(ruta: Path) -> float:
    """Obtiene la duración en segundos usando wave o ffprobe."""
    if not ruta or not ruta.exists():
        return 0.0
    if ruta.suffix.lower() == ".wav":
        try:
            with wave.open(str(ruta), "rb") as wf:
                return wf.getnframes() / float(wf.getframerate())
        except Exception:
            pass

    ffprobe = "ffprobe"
    try:
        from src import config
        ffprobe = config.ffmpeg_bin("ffprobe") or "ffprobe"
    except Exception:
        pass

    try:
        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(ruta),
        ]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _obtener_duracion_render_proyecto(carpeta: Path) -> float:
    """Calcula la duración en segundos del render o del guion del proyecto."""
    candidatos = [
        carpeta / "render" / "video_16x9.mp4",
        carpeta / "renders" / "video_con_voz_ia.mp4",
        carpeta / "renders" / "tiktok_con_voz_ia.mp4",
    ]
    if (carpeta / "renders").exists():
        candidatos.extend((carpeta / "renders").glob("*.mp4"))
    if (carpeta / "render").exists():
        candidatos.extend((carpeta / "render").glob("*.mp4"))
    candidatos.extend(carpeta.glob("*.mp4"))

    for c in candidatos:
        if c.exists() and c.is_file() and c.stat().st_size > 1000:
            dur = _obtener_duracion_archivo(c)
            if dur > 0.1:
                return dur

    proj_json = carpeta / "proyecto.json"
    if proj_json.exists():
        try:
            d = json.loads(proj_json.read_text(encoding="utf-8"))
            if "minutos" in d and float(d["minutos"]) > 0:
                return float(d["minutos"]) * 60.0
        except Exception:
            pass

    dir_voz = carpeta / "voz"
    guion_path = carpeta / "guion" / "guion.json"
    if not guion_path.exists():
        guion_path = carpeta / "guion" / "guion_tiktok.json"
    if guion_path.exists():
        try:
            g = json.loads(guion_path.read_text(encoding="utf-8"))
            escenas = g.get("escenas") or []
            total_dur = 0.0
            for idx, esc in enumerate(escenas, start=1):
                eid = esc.get("id") or idx
                d_esc = 0.0
                for wc in [dir_voz / f"escena_{eid:03d}.wav", dir_voz / f"escena_{eid}.wav", dir_voz / f"escena_{eid:03d}.mp3"]:
                    if wc.exists():
                        d_esc = _obtener_duracion_archivo(wc)
                        if d_esc > 0.1:
                            break
                if d_esc <= 0.1:
                    palabras = len((esc.get("voz") or "").split())
                    d_esc = max(2.5, palabras / 2.5)
                total_dur += d_esc
            if total_dur > 0.1:
                return total_dur
        except Exception:
            pass

    return 0.0


def buscar_video_id_en_proyecto(carpeta: Path) -> tuple[Optional[str], bool]:
    """Busca video_id en publicacion/PUBLICADO.txt, publicacion*.json o similar dentro del proyecto.

    Retorna (video_id, es_short). Nunca empata por título parecido.
    Decide es_short por la URL (/shorts/) o por la duración del render, no por el nombre del archivo.
    """
    carpeta = Path(carpeta)

    # 1. Leer publicacion/PUBLICADO.txt (o PUBLICADO.txt en la raíz)
    txt_candidatos = [
        carpeta / "publicacion" / "PUBLICADO.txt",
        carpeta / "PUBLICADO.txt",
    ]
    if (carpeta / "publicacion").exists():
        txt_candidatos.extend((carpeta / "publicacion").glob("*PUBLICADO*.txt"))
    txt_candidatos.extend(carpeta.glob("*PUBLICADO*.txt"))

    for p_txt in txt_candidatos:
        if p_txt.exists() and p_txt.is_file():
            try:
                contenido = p_txt.read_text(encoding="utf-8", errors="ignore")
                m = REGEX_PUBLICADO_YT.search(contenido)
                if m:
                    vid = m.group(1)
                    if "/shorts/" in contenido:
                        es_short = True
                    else:
                        dur = _obtener_duracion_render_proyecto(carpeta)
                        es_short = (dur <= 180.0) if dur > 0 else False
                    return vid, es_short
            except Exception:
                pass

    # 2. Leer archivos JSON (publicacion*.json, publicacion/*.json, proyecto.json)
    json_candidatos = list(carpeta.glob("publicacion*.json"))
    if (carpeta / "publicacion").exists():
        json_candidatos.extend((carpeta / "publicacion").glob("*.json"))
    proj_json = carpeta / "proyecto.json"
    if proj_json.exists():
        json_candidatos.append(proj_json)

    for p in json_candidatos:
        try:
            contenido = p.read_text(encoding="utf-8")
            d = json.loads(contenido)
            if isinstance(d, dict):
                vid = d.get("video_id") or d.get("yt_id") or d.get("id")
                url = str(d.get("url") or "")
                if (not vid or len(str(vid)) != 11) and url:
                    m = REGEX_PUBLICADO_YT.search(url)
                    if m:
                        vid = m.group(1)
                elif not vid or len(str(vid)) != 11:
                    m = REGEX_PUBLICADO_YT.search(contenido)
                    if m:
                        vid = m.group(1)

                if vid and isinstance(vid, str) and len(vid) == 11:
                    if "/shorts/" in url or "/shorts/" in contenido:
                        es_short = True
                    elif "es_short" in d and isinstance(d["es_short"], bool):
                        es_short = d["es_short"]
                    else:
                        dur = _obtener_duracion_render_proyecto(carpeta)
                        es_short = (dur <= 180.0) if dur > 0 else False
                    return vid, es_short
        except Exception:
            pass

    return None, False


def vincular_escenas_locales(con: sqlite3.Connection, dir_proyectos: Path = RAIZ / "proyectos") -> int:
    """Inspecciona proyectos locales y vincula su cronología con los videos en la base.

    Solo empata por video_id guardado al subir (publicacion*.json, PUBLICADO.txt o similar),
    nunca por título parecido, y nunca un Short con un proyecto largo.
    """
    dir_proyectos = Path(dir_proyectos)
    if not dir_proyectos.exists():
        return 0

    cur = con.execute("SELECT video_id, titulo, formato FROM videos")
    videos_bd = {r["video_id"]: dict(r) for r in cur.fetchall()}
    if not videos_bd:
        return 0

    total_escenas = 0

    for carpeta in dir_proyectos.iterdir():
        if not carpeta.is_dir():
            continue
        guion_path = carpeta / "guion" / "guion.json"
        if not guion_path.exists():
            guion_path = carpeta / "guion" / "guion_tiktok.json"
        if not guion_path.exists():
            continue

        vid, proj_es_short = buscar_video_id_en_proyecto(carpeta)
        if not vid or vid not in videos_bd:
            # Nunca empatar por título parecido
            continue

        v_bd = videos_bd[vid]
        es_video_short = (v_bd.get("formato") == "short")
        # Nunca empatar un Short con un proyecto largo
        if es_video_short != proj_es_short:
            continue

        try:
            g_data = json.loads(guion_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        escenas_raw = g_data.get("escenas", [])
        lista_a_guardar = []
        t_acum = 0.0
        dir_voz = carpeta / "voz"

        for idx, esc in enumerate(escenas_raw, start=1):
            n_esc = esc.get("id") or idx
            dur_esc = 0.0
            wav_candidatos = [
                dir_voz / f"escena_{n_esc:03d}.wav",
                dir_voz / f"escena_{n_esc}.wav",
                dir_voz / f"escena_{n_esc:03d}.mp3",
                dir_voz / f"escena_{n_esc}.mp3",
            ]
            for wc in wav_candidatos:
                if wc.exists():
                    d_wc = _obtener_duracion_archivo(wc)
                    if d_wc > 0.1:
                        dur_esc = d_wc
                        break

            if dur_esc <= 0.0:
                palabras = len((esc.get("voz") or "").split())
                dur_esc = max(2.5, palabras / 2.5)

            t_inicio = t_acum
            t_fin = t_acum + dur_esc
            t_acum = t_fin

            texto = esc.get("voz") or esc.get("texto_pantalla") or ""
            broll = esc.get("broll_query_en") or esc.get("broll_descripcion") or esc.get("broll") or ""

            lista_a_guardar.append({
                "n_escena": n_esc,
                "inicio_s": t_inicio,
                "fin_s": t_fin,
                "texto": texto,
                "broll_fuente": broll,
            })

        if lista_a_guardar:
            upsert_escenas(con, vid, lista_a_guardar)
            total_escenas += len(lista_a_guardar)

    return total_escenas


# ---------------------------------------------------------------------------
# Conexión Multi-canal y Verificación de Channel ID
# ---------------------------------------------------------------------------

def resolver_token(canal: str, token_cli: Optional[Path] = None) -> Path:
    if token_cli:
        return Path(token_cli)
    for k, v in MAPA_CANAL_TOKEN.items():
        if k.lower() in (canal or "").lower() or (canal or "").lower() in k.lower():
            return v
    return TOKEN_CODIGO


def obtener_servicios_youtube(canal: str = "Código OcultoTV", token_path: Optional[Path] = None):
    """Inicializa servicios de YouTube y valida estrictamente el Channel ID."""
    token_file = resolver_token(canal, token_path)
    if not token_file.exists():
        raise FileNotFoundError(
            f"No existe el archivo de token para el canal '{canal}': {token_file}\n"
            f"Ejecuta: python src/metricas/autorizar_canal.py --canal '{canal}'"
        )

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError("Bibliotecas google-api-python-client y google-auth-oauthlib no instaladas.")

    creds = Credentials.from_authorized_user_file(str(token_file))
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Escritura atómica a archivo temporal sin tocar backups
            guardar_token_atomicamente(token_file, creds.to_json())
        else:
            raise RuntimeError(f"El token {token_file.name} no es válido ni renovable. Re-autoriza el canal.")

    yt_data = build("youtube", "v3", credentials=creds, cache_discovery=False)
    yt_analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

    # Verificación de identidad del canal
    ch_resp = yt_data.channels().list(part="id,snippet,contentDetails", mine=True).execute()
    items = ch_resp.get("items", [])
    if not items:
        raise RuntimeError(f"No se encontró ningún canal en la cuenta asociada a {token_file.name}.")

    ch_actual = items[0]
    actual_id = ch_actual["id"]
    actual_title = ch_actual["snippet"]["title"]

    # Si es Novelas Express MX, validar obligatoriamente su channel ID
    if "novela" in (canal or "").lower():
        if actual_id != NOVELAS_CHANNEL_ID:
            raise RuntimeError(
                f"Error de verificación de canal: el token autenticado ({token_file.name}) "
                f"corresponde al canal '{actual_title}' (ID: {actual_id}), "
                f"pero se esperaba estrictamente Novelas Express MX (ID: {NOVELAS_CHANNEL_ID})."
            )

    return yt_data, yt_analytics, ch_actual


# ---------------------------------------------------------------------------
# Cosecha de Datos con YouTube Analytics (Sin datos inventados)
# ---------------------------------------------------------------------------

def recolectar_desde_youtube(
    con: sqlite3.Connection,
    canal_filtro: Optional[str] = None,
    desde_fecha: Optional[str] = None,
    token_path: Optional[Path] = None,
    csv_etiquetas_path: Path = CSV_ETIQUETAS_DEFAULT,
) -> tuple[dict[str, int], list[str]]:
    """Cosecha videos y métricas reales desde YouTube.

    Retorna (estadísticas, lista_de_errores). Si falla Analytics, no inventa datos.
    """
    stats = {"videos": 0, "metricas": 0, "retencion": 0, "trafico": 0}
    errores: list[str] = []

    canal_objetivo = canal_filtro or "Código OcultoTV"

    try:
        yt_data, yt_analytics, canal_info = obtener_servicios_youtube(canal=canal_objetivo, token_path=token_path)
    except Exception as e:
        errores.append(f"Error crítico de autenticación/verificación para '{canal_objetivo}': {e}")
        return stats, errores

    canal_nombre = canal_info["snippet"]["title"]
    uploads_id = canal_info["contentDetails"]["relatedPlaylists"]["uploads"]
    etiquetas_csv = cargar_etiquetas_csv(csv_etiquetas_path)

    hoy_str = date.today().isoformat()
    if not desde_fecha:
        desde_fecha = (date.today() - timedelta(days=3)).isoformat()

    try:
        # Obtener lista de videos subidos
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

        # Detalles por bloques de 50
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

                titulo = snip.get("title", "")
                pub_at = snip.get("publishedAt", "")
                fecha_pub, hora_pub = convertir_a_merida(pub_at)
                dur_s = iso_duracion_a_s(cnt.get("duration", ""))

                csv_item = etiquetas_csv.get(vid, {})
                if not csv_item:
                    t_min = titulo.lower()
                    for c_id, c_val in etiquetas_csv.items():
                        if c_id.lower() in t_min or (len(c_id) >= 6 and c_id[:6].lower() in t_min):
                            csv_item = c_val
                            break

                # Inferencia con reglas estrictas
                meta = inferir_formato_y_metadatos(
                    titulo=titulo,
                    duracion_s=dur_s,
                    canal=canal_nombre,
                    es_vertical=False,
                    formato_csv=csv_item.get("formato", ""),
                    tema_csv=csv_item.get("tema", ""),
                    serie_csv=csv_item.get("serie", ""),
                    capitulo_csv=csv_item.get("capitulo"),
                )
                meta["video_id"] = vid
                meta["canal"] = canal_nombre
                meta["titulo"] = titulo
                meta["duracion_s"] = dur_s
                meta["fecha_publicacion"] = fecha_pub
                meta["hora_publicacion"] = hora_pub
                meta["voz"] = csv_item.get("voz")
                meta["estilo_visual"] = csv_item.get("estilo_visual")

                upsert_video(con, meta)
                stats["videos"] += 1

                # Consulta obligatoria a YouTube Analytics API (sin datos inventados)
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
                        upsert_metrica_diaria(con, {
                            "video_id": vid,
                            "fecha": str(row[0]),
                            "vistas": int(row[1] or 0),
                            "minutos_vistos": float(row[2] or 0.0),
                            "duracion_media_s": float(row[3] or 0.0),
                            "pct_visto_medio": float(row[4] or 0.0),
                            "likes": int(row[5] or 0),
                            "comentarios": int(row[6] or 0),
                            "suscriptores_ganados": int(row[7] or 0),
                        })
                        stats["metricas"] += 1
                except Exception as e_an:
                    errores.append(f"Video {vid} ('{titulo}'): fallo al obtener métricas diarias de Analytics: {e_an}")

                # Fuentes de tráfico
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
                except Exception as e_tr:
                    errores.append(f"Video {vid} ('{titulo}'): fallo en fuentes de tráfico: {e_tr}")

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
                except Exception as e_rt:
                    errores.append(f"Video {vid} ('{titulo}'): fallo en curva de retención: {e_rt}")

        con.commit()
    except Exception as e_gen:
        errores.append(f"Excepción general en recolección: {e_gen}")

    return stats, errores


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Recolector de métricas de YouTube para Docu Factory y Novelas Express MX")
    parser.add_argument("--canal", type=str, default="Código OcultoTV", help="Nombre del canal: 'Código OcultoTV' o 'Novelas Express MX'")
    parser.add_argument("--desde", type=str, default=None, help="Fecha inicial en formato YYYY-MM-DD (por defecto: últimos 3 días)")
    parser.add_argument("--token", type=Path, default=None, help="Ruta personalizada del archivo de token OAuth")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT, help="Ruta de la base de datos SQLite")
    parser.add_argument("--csv-etiquetas", type=Path, default=CSV_ETIQUETAS_DEFAULT, help="Ruta del archivo CSV con correcciones de etiquetas")

    args = parser.parse_args()

    desde = args.desde
    if not desde:
        desde = (date.today() - timedelta(days=3)).isoformat()

    print(f"=== Iniciando recolección de métricas ===")
    print(f"  Base de datos: {args.db}")
    print(f"  Canal:         {args.canal}")
    print(f"  Desde:         {desde}")

    con = inicializar_db(db_path=args.db)
    errores_totales: list[str] = []

    try:
        stats, errs = recolectar_desde_youtube(
            con=con,
            canal_filtro=args.canal,
            desde_fecha=desde,
            token_path=args.token,
            csv_etiquetas_path=args.csv_etiquetas,
        )
        errores_totales.extend(errs)

        escenas_vinculadas = vincular_escenas_locales(con)
        con.commit()

        print(f"\n=== Resultados de la Recolección ===")
        print(f"  Videos registrados/actualizados: {stats['videos']}")
        print(f"  Registros de métricas diarias:   {stats['metricas']}")
        print(f"  Puntos de retención:             {stats['retencion']}")
        print(f"  Registros de tráfico:            {stats['trafico']}")
        print(f"  Escenas de proyectos vinculadas: {escenas_vinculadas}")

        if errores_totales:
            print(f"\n❌ Resumen de Errores ({len(errores_totales)} fallo(s)):", file=sys.stderr)
            for err in errores_totales:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)
        else:
            print("\n[OK] Recolección completada sin errores.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
