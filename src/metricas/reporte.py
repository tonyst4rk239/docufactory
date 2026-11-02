"""Generador de reportes ejecutivos de metricas para YouTube.

Ejecuta las consultas SQL de sql/consultas/, genera tablas formateadas en Markdown
y sintetiza las secciones de 'Conclusiones con confianza' y 'Señales debiles'.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sqlite3
import sys
from typing import Any, Optional

RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.metricas.recolectar import _fecha_local

DB_DEFAULT = RAIZ / "data" / "metricas.db"
DIR_CONSULTAS_DEFAULT = RAIZ / "sql" / "consultas"
DIR_REPORTES_DEFAULT = RAIZ / "reportes"


def ejecutar_consulta(con: sqlite3.Connection, ruta_sql: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """Ejecuta una consulta SQL y retorna los nombres de columna y lista de filas."""
    sql = ruta_sql.read_text(encoding="utf-8")
    cur = con.cursor()
    cur.execute(sql)
    columnas = [d[0] for d in cur.description] if cur.description else []
    filas = [dict(zip(columnas, row)) for row in cur.fetchall()]
    return columnas, filas


def generar_tabla_markdown(columnas: list[str], filas: list[dict[str, Any]]) -> str:
    """Convierte columnas y filas en una tabla con formato Markdown."""
    if not filas:
        return "_Sin datos suficientes para esta consulta._\n"

    # Encabezados legibles
    headers = [col.replace("_", " ").capitalize() for col in columnas]
    lineas = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]

    for fila in filas:
        valores = []
        for col in columnas:
            v = fila.get(col)
            if v is None:
                val_str = "-"
            elif col == "muestra_chica":
                val_str = "⚠️ Sí (<3 vids o <500 v.)" if v == 1 else "✅ No (Confiable)"
            elif isinstance(v, float):
                val_str = f"{v:.2f}"
            else:
                val_str = str(v)
            valores.append(val_str.replace("|", "\\|"))
        lineas.append("| " + " | ".join(valores) + " |")

    return "\n".join(lineas) + "\n"


def sintetizar_analisis(resultados: dict[str, list[dict[str, Any]]]) -> tuple[list[str], list[str]]:
    """Genera listas de conclusiones con confianza y señales débiles según muestra_chica."""
    conclusiones: list[str] = []
    senales_debiles: list[str] = []

    # 1. Formato vs Retención
    filas_formato = resultados.get("formato_vs_retencion", [])
    for f in filas_formato:
        formato = f.get("formato", "desconocido")
        canal = f.get("canal", "General")
        ret = f.get("promedio_pct_visto", 0.0)
        vistas = f.get("total_vistas", 0)
        n = f.get("n_videos", 0)
        texto = f"**{canal} - {formato}**: retención promedio de {ret}% con {vistas} vistas en {n} videos."

        if f.get("muestra_chica") == 0:
            conclusiones.append(f"{texto} Rendimiento respaldado con volumen suficiente.")
        else:
            senales_debiles.append(f"{texto} (Muestra chica: requiere más videos o vistas para ser concluyente).")

    # 2. Top Temas
    filas_temas = resultados.get("top_temas", [])
    for f in filas_temas:
        tema = f.get("tema", "")
        ret = f.get("retencion_media", 0.0)
        vistas = f.get("total_vistas", 0)
        n = f.get("n_videos", 0)
        texto = f"Tema **'{tema}'**: retención promedio de {ret}% ({vistas} vistas en {n} videos)."

        if f.get("muestra_chica") == 0:
            conclusiones.append(f"Tema destacado y validado: {texto}")
        else:
            senales_debiles.append(f"Tema promisorio pero exploratorio: {texto}")

    # 3. A/B Largos vs Recopilación
    filas_ab = resultados.get("ab_largos", [])
    for f in filas_ab:
        sem = f.get("semana", "")
        formato = f.get("formato", "")
        vistas = f.get("total_vistas", 0)
        ret = f.get("promedio_pct_visto", 0.0)
        texto = f"Semana {sem} ({formato}): {vistas} vistas, {ret}% retención."
        if f.get("muestra_chica") == 0:
            conclusiones.append(f"{texto} (Volumen suficiente).")
        else:
            senales_debiles.append(f"{texto} (Bajo volumen semanal).")

    # 4. Novelas por Capítulo
    filas_nov = resultados.get("novelas_por_capitulo", [])
    for f in filas_nov:
        serie = f.get("serie", "")
        cap = f.get("capitulo", 1)
        caida = f.get("caida_retencion_vs_anterior")
        ret = f.get("retencion_media", 0.0)
        caida_str = f" (variación vs cap anterior: {caida:+.2f}%)" if caida is not None else " (primer capítulo registrado)"
        texto = f"**{serie} - Cap. {cap}**: retención {ret}%{caida_str}."

        if f.get("muestra_chica") == 0:
            conclusiones.append(f"{texto}")
        else:
            senales_debiles.append(f"{texto} [Capítulo con muestra baja].")

    # 5. Horarios
    filas_hor = resultados.get("horario", [])
    for f in filas_hor:
        dia = f.get("dia_semana", "")
        hora = f.get("hora_publicacion", "")
        vistas = f.get("total_vistas", 0)
        ret = f.get("retencion_media", 0.0)
        texto = f"Publicación en **{dia} a las {hora}**: promedio {vistas} vistas, retención {ret}%."

        if f.get("muestra_chica") == 0:
            conclusiones.append(f"{texto} Horario estadísticamente significativo.")
        else:
            senales_debiles.append(f"{texto} (Pocos videos subidos en este intervalo).")

    # 6. Puntos de Fuga (Cruce de Retención con Escenas y B-roll)
    filas_fuga = resultados.get("puntos_de_fuga", [])
    for f in filas_fuga[:8]:
        titulo = f.get("titulo", "Video")
        seg = f.get("segundo_fuga", 0.0)
        caida = f.get("caida_pct", 0.0)
        ret = f.get("retencion_momento", 0.0)
        n_esc = f.get("n_escena", 0)
        narr = f.get("narracion_en_segundo", "")
        broll = f.get("broll_en_pantalla", "")
        broll_info = f" | B-roll: '{broll}'" if broll and broll != "desconocido" else ""
        texto = f"Punto crítico de fuga en **{titulo}**: en el segundo {seg:.1f}s la audiencia cayó {caida:+.2f}% (quedando {ret}%) durante Escena {n_esc} (\"{narr}\"{broll_info})."

        if f.get("muestra_chica") == 0:
            conclusiones.append(f"{texto}")
        else:
            senales_debiles.append(f"{texto}")

    return conclusiones, senales_debiles


def generar_reporte_md(
    db_path: Path = DB_DEFAULT,
    consultas_dir: Path = DIR_CONSULTAS_DEFAULT,
    salida_md: Optional[Path] = None,
) -> Path:
    """Genera el reporte Markdown consolidado y lo escribe en disco."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"No existe la base de datos en {db_path}. Corre primero: python src/metricas/recolectar.py")

    fecha_hoy = date.today().isoformat()
    if salida_md is None:
        salida_md = DIR_REPORTES_DEFAULT / f"metricas_{fecha_hoy}.md"
    salida_md = Path(salida_md)
    salida_md.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.create_function("fecha_local", 2, _fecha_local)

    orden_consultas = [
        "formato_vs_retencion",
        "top_temas",
        "ab_largos",
        "novelas_por_capitulo",
        "horario",
        "puntos_de_fuga",
    ]

    titulos_bloques = {
        "formato_vs_retencion": "1. Formato vs Retención (Últimas 4 Semanas)",
        "top_temas": "2. Top Temas por Retención Media",
        "ab_largos": "3. Comparativa A/B: Largo Original vs Recopilación",
        "novelas_por_capitulo": "4. Retención en Novelas por Capítulo y Caídas Consecutivas",
        "horario": "5. Rendimiento por Día y Hora de Publicación",
        "puntos_de_fuga": "6. Puntos Críticos de Fuga (Cruce Retención vs Escenas y B-roll)",
    }

    resultados_dict: dict[str, list[dict[str, Any]]] = {}
    bloques_tablas_md: list[str] = []

    try:
        for nombre in orden_consultas:
            ruta_sql = Path(consultas_dir) / f"{nombre}.sql"
            if not ruta_sql.exists():
                continue
            columnas, filas = ejecutar_consulta(con, ruta_sql)
            resultados_dict[nombre] = filas

            titulo = titulos_bloques.get(nombre, nombre.replace("_", " ").capitalize())
            tabla_md = generar_tabla_markdown(columnas, filas)
            bloques_tablas_md.append(f"### {titulo}\n\n{tabla_md}")

        # Sintetizar conclusiones
        conclusiones, senales = sintetizar_analisis(resultados_dict)

        # Armar documento Markdown
        lineas_doc: list[str] = [
            f"# Reporte de Métricas YouTube: Código OcultoTV y Novelas Express MX",
            f"**Fecha de generación:** {fecha_hoy} | **Base de datos:** `{db_path.name}`\n",
            "---",
            "## Conclusiones con Confianza",
            "> Métricas con volumen estadístico suficiente (al menos 3 videos y 500+ vistas).",
        ]

        if conclusiones:
            for c in conclusiones:
                lineas_doc.append(f"- {c}")
        else:
            lineas_doc.append("_Actualmente no hay muestras con >= 3 videos y >= 500 vistas en este periodo._")

        lineas_doc.extend([
            "",
            "## Señales Débiles",
            "> Tendencias preliminares con muestra chica (< 3 videos o < 500 vistas). Tomar como hipótesis de prueba, no como hechos probados.",
        ])

        if senales:
            for s in senales:
                lineas_doc.append(f"- {s}")
        else:
            lineas_doc.append("_No se detectaron señales débiles aisladas._")

        lineas_doc.extend([
            "",
            "---",
            "## Tablas Detalladas por Consulta",
            "",
        ])

        lineas_doc.extend(bloques_tablas_md)

        salida_md.write_text("\n".join(lineas_doc), encoding="utf-8")
        return salida_md
    finally:
        con.close()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Generador de reportes de métricas YouTube en Markdown")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT, help="Ruta de la base de datos SQLite")
    parser.add_argument("--consultas-dir", type=Path, default=DIR_CONSULTAS_DEFAULT, help="Directorio con consultas SQL")
    parser.add_argument("--salida", type=Path, default=None, help="Ruta del archivo Markdown de salida")

    args = parser.parse_args()

    try:
        archivo_generado = generar_reporte_md(
            db_path=args.db,
            consultas_dir=args.consultas_dir,
            salida_md=args.salida,
        )
        print(f"[OK] Reporte generado exitosamente en: {archivo_generado}")
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
