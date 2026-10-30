"""Docu Factory — Gestor de Base de Datos SQLite para Analíticas y Producción.

Maneja la conexión a datos/docufactory.db (excluida en .gitignore) y provee
funciones para insertar y consultar todas las características del video segundo a segundo.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Optional

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ / "datos"
DB_PATH = DIR_DATOS / "docufactory.db"
SCHEMA_PATH = DIR_DATOS / "schema.sql"


def obtener_conexion(ruta_db: Optional[Path] = None) -> sqlite3.Connection:
    """Abre conexión con SQLite habilitando claves foráneas y Row factory."""
    ruta = Path(ruta_db or DB_PATH)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    primera_vez = not ruta.exists() or ruta.stat().st_size == 0
    con = sqlite3.connect(str(ruta), timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    if primera_vez:
        inicializar_db(con=con)
    return con


def inicializar_db(ruta_db: Optional[Path] = None, con: Optional[sqlite3.Connection] = None) -> None:
    """Ejecuta el script de esquema schema.sql para crear tablas e índices."""
    cerrar = False
    if con is None:
        con = obtener_conexion(ruta_db)
        cerrar = True
    if SCHEMA_PATH.exists():
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        con.executescript(sql)
        con.commit()
    if cerrar:
        con.close()


# ---------------------------------------------------------------------------
# Extractores de Características y Medidores
# ---------------------------------------------------------------------------
def calcular_sha1(ruta: Path) -> str:
    """Calcula el hash SHA1 de un archivo para rastrear reutilización de B-roll."""
    if not ruta or not Path(ruta).exists() or Path(ruta).is_dir():
        return ""
    h = hashlib.sha1()
    try:
        with open(ruta, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def analizar_caracteristicas_titulo(titulo: str) -> dict[str, Any]:
    """Extrae métricas virales de un título."""
    tit = (titulo or "").strip()
    largo = len(tit)
    tiene_numero = 1 if re.search(r"\d+", tit) else 0
    letras = [c for c in tit if c.isalpha()]
    mayus = [c for c in letras if c.isupper()]
    pct_mayus = (len(mayus) / len(letras) * 100.0) if letras else 0.0

    # Emojis en rango unicode común
    patron_emoji = re.compile(
        "[\U00010000-\U0010ffff]|[\u2600-\u27ff]|[\u2300-\u23ff]",
        flags=re.UNICODE,
    )
    tiene_emoji = 1 if patron_emoji.search(tit) else 0
    tiene_signos = 1 if any(c in tit for c in ("?", "!", "¿", "¡", ":", "—", "-")) else 0

    return {
        "largo": largo,
        "tiene_numero": tiene_numero,
        "pct_mayusculas": round(pct_mayus, 1),
        "tiene_emoji": tiene_emoji,
        "tiene_signos": tiene_signos,
    }


def analizar_legibilidad_guion(texto_completo: str) -> dict[str, Any]:
    """Calcula métricas de texto, preguntas abiertas y entidades temporales/geográficas."""
    t = (texto_completo or "").strip()
    palabras = [w for w in re.findall(r"\b[A-Za-z0-9áéíóúÁÉÍÓÚñÑüÜ]+\b", t)]
    total_palabras = len(palabras)

    # Oraciones
    oraciones = [s.strip() for s in re.split(r"[.!?]+", t) if s.strip()]
    n_oraciones = max(1, len(oraciones))

    # Índice de legibilidad simplificado de Flesch-Szigriszt para español
    # 206.835 - 62.3 * (sílabas/palabras) - (palabras/oraciones)
    silabas_aprox = sum(max(1, len(re.findall(r"[aeiouáéíóúüAEIOUÁÉÍÓÚÜ]+", p))) for p in palabras)
    pal_por_oracion = total_palabras / n_oraciones
    sil_por_palabra = (silabas_aprox / max(1, total_palabras))
    legibilidad = max(0.0, min(100.0, 206.835 - (62.3 * sil_por_palabra) - pal_por_oracion))

    # Preguntas abiertas / retóricas
    preguntas = re.findall(r"[¿?]", t)
    n_preguntas = max(0, len(preguntas) // 2) if "¿" in t else len(preguntas)

    # Menciones de años (ej. 1945, 2026) y lugares
    fechas = sorted(list(set(re.findall(r"\b(1[89]\d\d|20\d\d)\b", t))))
    palabras_lugares = re.findall(
        r"\b(?:en|de|hacia|cerca de)\s+([A-ZÁÉÍÓÚ][a-záéíóú]+(?:\s+[A-ZÁÉÍÓÚ][a-záéíóú]+)?)\b",
        t,
    )
    lugares = sorted(list(set(palabras_lugares)))

    # Menciones de caso real / documentos oficiales / testigos
    palabras_caso_real = {"caso", "documento", "cia", "fbi", "archivo", "oficial", "desclasificado", "testigo", "víctima", "victima", "investigación", "informe"}
    menciona_caso_real = 1 if any(w.lower() in palabras_caso_real for w in palabras) else 0

    return {
        "palabras_totales": total_palabras,
        "legibilidad": round(legibilidad, 1),
        "n_preguntas_abiertas": n_preguntas,
        "menciona_caso_real": menciona_caso_real,
        "lugares": json.dumps(lugares, ensure_ascii=False),
        "fechas": json.dumps(fechas, ensure_ascii=False),
    }


def medir_lufs(ruta_audio_o_video: Path, ffmpeg: Optional[str] = None) -> Optional[float]:
    """Mide los LUFS integrados usando FFmpeg loudnorm con print_format=json."""
    if not ruta_audio_o_video or not Path(ruta_audio_o_video).exists():
        return None
    try:
        from src import config
        ffmpeg_bin = ffmpeg or config.ffmpeg_bin("ffmpeg") or "ffmpeg"
    except Exception:
        ffmpeg_bin = ffmpeg or "ffmpeg"

    cmd = [
        ffmpeg_bin, "-hide_banner", "-i", str(ruta_audio_o_video),
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-",
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        salida = res.stderr or ""
        m = re.search(r'"input_i"\s*:\s*"(-?\d+(?:\.\d+)?)"', salida)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Funciones de Inserción / Upsert
# ---------------------------------------------------------------------------
def guardar_video(datos: dict[str, Any], con: Optional[sqlite3.Connection] = None) -> None:
    """Inserta o actualiza un registro en la tabla videos."""
    campos = [
        "id", "slug", "formato", "tema", "tono", "duracion_s", "voz", "voz_fallback",
        "fecha_render", "titulo", "descripcion", "hashtags", "texto_miniatura",
        "fuente_tema", "tendencia_origen", "fecha_especial", "costo_voz_usd",
        "costo_ia_usd", "tiempo_render_s",
    ]
    vals = {k: datos.get(k) for k in campos}
    if not vals.get("id"):
        vals["id"] = vals.get("slug")
    if not vals.get("slug"):
        vals["slug"] = vals.get("id")

    sql = f"""
    INSERT INTO videos ({', '.join(campos)})
    VALUES ({', '.join(':' + k for k in campos)})
    ON CONFLICT(id) DO UPDATE SET
        formato = excluded.formato,
        tema = excluded.tema,
        tono = excluded.tono,
        duracion_s = excluded.duracion_s,
        voz = excluded.voz,
        voz_fallback = excluded.voz_fallback,
        fecha_render = coalesce(excluded.fecha_render, videos.fecha_render),
        titulo = coalesce(excluded.titulo, videos.titulo),
        descripcion = coalesce(excluded.descripcion, videos.descripcion),
        hashtags = coalesce(excluded.hashtags, videos.hashtags),
        texto_miniatura = coalesce(excluded.texto_miniatura, videos.texto_miniatura),
        fuente_tema = coalesce(excluded.fuente_tema, videos.fuente_tema),
        tendencia_origen = coalesce(excluded.tendencia_origen, videos.tendencia_origen),
        fecha_especial = coalesce(excluded.fecha_especial, videos.fecha_especial),
        costo_voz_usd = coalesce(excluded.costo_voz_usd, videos.costo_voz_usd),
        costo_ia_usd = coalesce(excluded.costo_ia_usd, videos.costo_ia_usd),
        tiempo_render_s = coalesce(excluded.tiempo_render_s, videos.tiempo_render_s);
    """
    c = con or obtener_conexion()
    try:
        c.execute(sql, vals)
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_guion(datos: dict[str, Any], con: Optional[sqlite3.Connection] = None) -> None:
    """Inserta o actualiza las características del guion."""
    campos = [
        "video_id", "palabras_totales", "legibilidad", "segundos_hasta_misterio",
        "n_preguntas_abiertas", "menciona_caso_real", "lugares", "fechas",
        "adelanta_siguiente", "tipo_gancho",
    ]
    vals = {k: datos.get(k) for k in campos}
    sql = f"""
    INSERT INTO guion ({', '.join(campos)})
    VALUES ({', '.join(':' + k for k in campos)})
    ON CONFLICT(video_id) DO UPDATE SET
        palabras_totales = excluded.palabras_totales,
        legibilidad = excluded.legibilidad,
        segundos_hasta_misterio = excluded.segundos_hasta_misterio,
        n_preguntas_abiertas = excluded.n_preguntas_abiertas,
        menciona_caso_real = excluded.menciona_caso_real,
        lugares = excluded.lugares,
        fechas = excluded.fechas,
        adelanta_siguiente = excluded.adelanta_siguiente,
        tipo_gancho = excluded.tipo_gancho;
    """
    c = con or obtener_conexion()
    try:
        c.execute(sql, vals)
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_escenas(video_id: str, lista_escenas: list[dict[str, Any]], con: Optional[sqlite3.Connection] = None) -> None:
    """Reemplaza la lista de escenas de un video."""
    c = con or obtener_conexion()
    try:
        c.execute("DELETE FROM escenas WHERE video_id = ?", (video_id,))
        for esc in lista_escenas:
            c.execute(
                """
                INSERT INTO escenas (video_id, n_escena, inicio_s, fin_s, tipo, texto, palabras_por_minuto, tiene_pregunta, tiene_cifra, emocion_voz)
                VALUES (:video_id, :n_escena, :inicio_s, :fin_s, :tipo, :texto, :palabras_por_minuto, :tiene_pregunta, :tiene_cifra, :emocion_voz)
                """,
                {
                    "video_id": video_id,
                    "n_escena": esc.get("n_escena", 1),
                    "inicio_s": esc.get("inicio_s", 0.0),
                    "fin_s": esc.get("fin_s", 0.0),
                    "tipo": esc.get("tipo", "desarrollo"),
                    "texto": esc.get("texto", ""),
                    "palabras_por_minuto": esc.get("palabras_por_minuto", 0.0),
                    "tiene_pregunta": 1 if esc.get("tiene_pregunta") else 0,
                    "tiene_cifra": 1 if esc.get("tiene_cifra") else 0,
                    "emocion_voz": esc.get("emocion_voz", "neutral"),
                },
            )
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_tomas(video_id: str, lista_tomas: list[dict[str, Any]], con: Optional[sqlite3.Connection] = None) -> None:
    """Reemplaza el listado de tomas con sus tiempos reales de corte."""
    c = con or obtener_conexion()
    try:
        c.execute("DELETE FROM tomas WHERE video_id = ?", (video_id,))
        for toma in lista_tomas:
            c.execute(
                """
                INSERT INTO tomas (video_id, n_escena, inicio_s, fin_s, archivo, sha1, fuente, autor, licencia, modo, brillo_medio, movimiento, aparece_host)
                VALUES (:video_id, :n_escena, :inicio_s, :fin_s, :archivo, :sha1, :fuente, :autor, :licencia, :modo, :brillo_medio, :movimiento, :aparece_host)
                """,
                {
                    "video_id": video_id,
                    "n_escena": toma.get("n_escena", 1),
                    "inicio_s": toma.get("inicio_s", 0.0),
                    "fin_s": toma.get("fin_s", 0.0),
                    "archivo": toma.get("archivo", ""),
                    "sha1": toma.get("sha1", ""),
                    "fuente": toma.get("fuente", "pixabay"),
                    "autor": toma.get("autor", ""),
                    "licencia": toma.get("licencia", "libre"),
                    "modo": toma.get("modo", "fill"),
                    "brillo_medio": toma.get("brillo_medio", 0.0),
                    "movimiento": toma.get("movimiento", "estatico"),
                    "aparece_host": 1 if toma.get("aparece_host") else 0,
                },
            )
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_ritmo(datos: dict[str, Any], con: Optional[sqlite3.Connection] = None) -> None:
    campos = ["video_id", "cortes_por_minuto", "duracion_media_toma_s", "apariciones_host", "subtitulos_resaltados"]
    vals = {k: datos.get(k) for k in campos}
    if isinstance(vals.get("apariciones_host"), (list, tuple)):
        vals["apariciones_host"] = json.dumps(vals["apariciones_host"])
    sql = f"""
    INSERT INTO ritmo ({', '.join(campos)})
    VALUES ({', '.join(':' + k for k in campos)})
    ON CONFLICT(video_id) DO UPDATE SET
        cortes_por_minuto = excluded.cortes_por_minuto,
        duracion_media_toma_s = excluded.duracion_media_toma_s,
        apariciones_host = excluded.apariciones_host,
        subtitulos_resaltados = excluded.subtitulos_resaltados;
    """
    c = con or obtener_conexion()
    try:
        c.execute(sql, vals)
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_audio(datos: dict[str, Any], con: Optional[sqlite3.Connection] = None) -> None:
    campos = ["video_id", "lufs", "musica", "efectos", "n_pausas", "pausa_media_s"]
    vals = {k: datos.get(k) for k in campos}
    if isinstance(vals.get("efectos"), (list, tuple)):
        vals["efectos"] = json.dumps(vals["efectos"], ensure_ascii=False)
    sql = f"""
    INSERT INTO audio ({', '.join(campos)})
    VALUES ({', '.join(':' + k for k in campos)})
    ON CONFLICT(video_id) DO UPDATE SET
        lufs = excluded.lufs,
        musica = excluded.musica,
        efectos = excluded.efectos,
        n_pausas = excluded.n_pausas,
        pausa_media_s = excluded.pausa_media_s;
    """
    c = con or obtener_conexion()
    try:
        c.execute(sql, vals)
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_miniatura(datos: dict[str, Any], con: Optional[sqlite3.Connection] = None) -> None:
    campos = ["video_id", "archivo", "n_palabras", "colores_dominantes", "tiene_cara", "emocion_cara", "tiene_rec"]
    vals = {k: datos.get(k) for k in campos}
    if isinstance(vals.get("colores_dominantes"), (list, tuple)):
        vals["colores_dominantes"] = json.dumps(vals["colores_dominantes"])
    sql = f"""
    INSERT INTO miniatura ({', '.join(campos)})
    VALUES ({', '.join(':' + k for k in campos)})
    ON CONFLICT(video_id) DO UPDATE SET
        archivo = excluded.archivo,
        n_palabras = excluded.n_palabras,
        colores_dominantes = excluded.colores_dominantes,
        tiene_cara = excluded.tiene_cara,
        emocion_cara = excluded.emocion_cara,
        tiene_rec = excluded.tiene_rec;
    """
    c = con or obtener_conexion()
    try:
        c.execute(sql, vals)
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_titulo_features(datos: dict[str, Any], con: Optional[sqlite3.Connection] = None) -> None:
    campos = ["video_id", "largo", "tiene_numero", "pct_mayusculas", "tiene_emoji", "tiene_signos"]
    vals = {k: datos.get(k) for k in campos}
    sql = f"""
    INSERT INTO titulo_features ({', '.join(campos)})
    VALUES ({', '.join(':' + k for k in campos)})
    ON CONFLICT(video_id) DO UPDATE SET
        largo = excluded.largo,
        tiene_numero = excluded.tiene_numero,
        pct_mayusculas = excluded.pct_mayusculas,
        tiene_emoji = excluded.tiene_emoji,
        tiene_signos = excluded.tiene_signos;
    """
    c = con or obtener_conexion()
    try:
        c.execute(sql, vals)
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_produccion(datos: dict[str, Any], con: Optional[sqlite3.Connection] = None) -> None:
    campos = ["video_id", "tomas_rechazadas_lente", "motivos_rechazo", "reclamos_content_id"]
    vals = {k: datos.get(k) for k in campos}
    if isinstance(vals.get("motivos_rechazo"), (list, tuple)):
        vals["motivos_rechazo"] = json.dumps(vals["motivos_rechazo"], ensure_ascii=False)
    sql = f"""
    INSERT INTO produccion ({', '.join(campos)})
    VALUES ({', '.join(':' + k for k in campos)})
    ON CONFLICT(video_id) DO UPDATE SET
        tomas_rechazadas_lente = excluded.tomas_rechazadas_lente,
        motivos_rechazo = excluded.motivos_rechazo,
        reclamos_content_id = excluded.reclamos_content_id;
    """
    c = con or obtener_conexion()
    try:
        c.execute(sql, vals)
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_publicacion(datos: dict[str, Any], con: Optional[sqlite3.Connection] = None) -> int:
    """Registra una subida a plataforma; si ya existe por url o id, actualiza."""
    c = con or obtener_conexion()
    try:
        # Verificar si ya existe por video_id y plataforma
        vid = datos["video_id"]
        plat = datos["plataforma"]
        cur = c.execute(
            "SELECT id FROM publicaciones WHERE video_id = ? AND plataforma = ? AND (url = ? OR video_platform_id = ?)",
            (vid, plat, datos.get("url"), datos.get("video_platform_id")),
        )
        fila = cur.fetchone()
        if fila:
            pub_id = fila["id"]
            c.execute(
                """
                UPDATE publicaciones SET
                    url = coalesce(?, url),
                    fecha_hora_publicacion = coalesce(?, fecha_hora_publicacion),
                    estado = coalesce(?, estado),
                    video_platform_id = coalesce(?, video_platform_id)
                WHERE id = ?
                """,
                (datos.get("url"), datos.get("fecha_hora_publicacion"), datos.get("estado"), datos.get("video_platform_id"), pub_id),
            )
        else:
            cur_ins = c.execute(
                """
                INSERT INTO publicaciones (video_id, plataforma, url, fecha_hora_publicacion, estado, video_platform_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (vid, plat, datos.get("url"), datos.get("fecha_hora_publicacion"), datos.get("estado", "publico"), datos.get("video_platform_id")),
            )
            pub_id = cur_ins.lastrowid
        if con is None:
            c.commit()
        return pub_id
    finally:
        if con is None:
            c.close()


def guardar_analitica_diaria(datos: dict[str, Any], con: Optional[sqlite3.Connection] = None) -> None:
    campos = [
        "video_id", "plataforma", "fecha", "vistas", "retencion_promedio_pct", "pct_pasa_3s",
        "likes", "comentarios", "compartidos", "ctr_miniatura", "suscriptores_ganados", "fuentes_trafico",
    ]
    vals = {k: datos.get(k) for k in campos}
    if isinstance(vals.get("fuentes_trafico"), (dict, list)):
        vals["fuentes_trafico"] = json.dumps(vals["fuentes_trafico"], ensure_ascii=False)
    sql = f"""
    INSERT INTO analiticas_diarias ({', '.join(campos)})
    VALUES ({', '.join(':' + k for k in campos)})
    ON CONFLICT(video_id, plataforma, fecha) DO UPDATE SET
        vistas = excluded.vistas,
        retencion_promedio_pct = excluded.retencion_promedio_pct,
        pct_pasa_3s = excluded.pct_pasa_3s,
        likes = excluded.likes,
        comentarios = excluded.comentarios,
        compartidos = excluded.compartidos,
        ctr_miniatura = excluded.ctr_miniatura,
        suscriptores_ganados = excluded.suscriptores_ganados,
        fuentes_trafico = excluded.fuentes_trafico,
        updated_at = CURRENT_TIMESTAMP;
    """
    c = con or obtener_conexion()
    try:
        c.execute(sql, vals)
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_curva_retencion(
    video_id: str,
    plataforma: str,
    puntos: list[tuple[float, float]],
    con: Optional[sqlite3.Connection] = None,
) -> None:
    """Guarda puntos (segundo_o_pct, audiencia_relativa) de la curva de retención."""
    if not puntos:
        return
    c = con or obtener_conexion()
    try:
        c.executemany(
            """
            INSERT INTO retencion_curva (video_id, plataforma, segundo_o_pct, audiencia_relativa)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(video_id, plataforma, segundo_o_pct) DO UPDATE SET
                audiencia_relativa = excluded.audiencia_relativa
            """,
            [(video_id, plataforma, float(p[0]), float(p[1])) for p in puntos],
        )
        if con is None:
            c.commit()
    finally:
        if con is None:
            c.close()


def guardar_comentarios(
    lista_comentarios: list[dict[str, Any]],
    con: Optional[sqlite3.Connection] = None,
) -> int:
    """Inserta o ignora comentarios por su comment_id."""
    if not lista_comentarios:
        return 0
    c = con or obtener_conexion()
    insertados = 0
    try:
        for com in lista_comentarios:
            cid = com.get("comment_id")
            if not cid:
                continue
            cur = c.execute(
                """
                INSERT OR IGNORE INTO comentarios (video_id, plataforma, fecha, texto, sentimiento, pide_segunda_parte, tema_sugerido, comment_id)
                VALUES (:video_id, :plataforma, :fecha, :texto, :sentimiento, :pide_segunda_parte, :tema_sugerido, :comment_id)
                """,
                {
                    "video_id": com["video_id"],
                    "plataforma": com.get("plataforma", "youtube"),
                    "fecha": com.get("fecha"),
                    "texto": com["texto"],
                    "sentimiento": com.get("sentimiento", "neutro"),
                    "pide_segunda_parte": 1 if com.get("pide_segunda_parte") else 0,
                    "tema_sugerido": com.get("tema_sugerido"),
                    "comment_id": cid,
                },
            )
            if cur.rowcount > 0:
                insertados += 1
        if con is None:
            c.commit()
        return insertados
    finally:
        if con is None:
            c.close()
