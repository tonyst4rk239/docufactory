"""Pruebas unitarias para el modulo de metricas YouTube.

Valida:
1. Inferencia de formatos (short, largo_original, recopilacion, novela_cap).
2. Idempotencia de los upserts en SQLite.
3. Calculo correcto de la bandera 'muestra_chica' en las consultas SQL.
4. Generacion del reporte Markdown con secciones de confianza y señales debiles.
"""
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.metricas.recolectar import (
    inicializar_db,
    inferir_formato_y_metadatos,
    cargar_etiquetas_csv,
    aplicar_etiquetas_manuales,
    upsert_video,
    upsert_metrica_diaria,
    upsert_retencion,
    upsert_trafico,
    iso_duracion_a_s,
)
from src.metricas.reporte import generar_reporte_md, ejecutar_consulta

RAIZ = Path(__file__).resolve().parent.parent
SCHEMA_PATH = RAIZ / "sql" / "schema.sql"
CONSULTAS_DIR = RAIZ / "sql" / "consultas"


class TestMetricas(unittest.TestCase):
    def setUp(self):
        # Crear base de datos temporal para pruebas aisladas
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_metricas.db"
        self.con = inicializar_db(db_path=self.db_path, schema_path=SCHEMA_PATH)

    def tearDown(self):
        self.con.close()
        self.temp_dir.cleanup()

    def test_iso_duracion_a_s(self):
        self.assertEqual(iso_duracion_a_s("PT45S"), 45.0)
        self.assertEqual(iso_duracion_a_s("PT3M15S"), 195.0)
        self.assertEqual(iso_duracion_a_s("PT1H2M3S"), 3723.0)
        self.assertEqual(iso_duracion_a_s(""), 0.0)

    def test_inferencia_formato(self):
        # Shorts por duracion o hashtag
        s1 = inferir_formato_y_metadatos("Misterio en el lago #shorts", 45.0)
        self.assertEqual(s1["formato"], "short")

        s2 = inferir_formato_y_metadatos("El secreto de Tesla", 55.0)
        self.assertEqual(s2["formato"], "short")

        # Novelas y capítulos
        n1 = inferir_formato_y_metadatos("Amor Prohibido | Capítulo 14", 350.0)
        self.assertEqual(n1["formato"], "novela_cap")
        self.assertEqual(n1["serie"], "Amor Prohibido")
        self.assertEqual(n1["capitulo"], 14)

        n2 = inferir_formato_y_metadatos("Venganza Oculta Cap. 3", 400.0, canal="Novelas Express MX")
        self.assertEqual(n2["formato"], "novela_cap")
        self.assertEqual(n2["capitulo"], 3)

        # Recopilaciones y maratones
        r1 = inferir_formato_y_metadatos("Maratón Top 5 Misterios Sin Resolver", 1800.0)
        self.assertEqual(r1["formato"], "recopilacion")

        r2 = inferir_formato_y_metadatos("Compilación de Todos los Casos de OVNI", 2400.0)
        self.assertEqual(r2["formato"], "recopilacion")

        # Largos originales
        l1 = inferir_formato_y_metadatos("El Enigma de la Atlántida Perdida", 650.0)
        self.assertEqual(l1["formato"], "largo_original")

    def test_etiquetas_manuales_csv(self):
        csv_file = Path(self.temp_dir.name) / "etiquetas.csv"
        csv_file.write_text(
            "video_id,formato,tema,serie,capitulo,voz,estilo_visual\n"
            "vid_123,recopilacion,Misterios Acuaticos,,,Alonso,cinematica\n",
            encoding="utf-8"
        )
        etiquetas = cargar_etiquetas_csv(csv_file)
        self.assertIn("vid_123", etiquetas)
        self.assertEqual(etiquetas["vid_123"]["formato"], "recopilacion")
        self.assertEqual(etiquetas["vid_123"]["voz"], "Alonso")

        meta = {"video_id": "vid_123", "formato": "largo_original", "tema": "Original"}
        meta_corregida = aplicar_etiquetas_manuales(meta, etiquetas)
        self.assertEqual(meta_corregida["formato"], "recopilacion")
        self.assertEqual(meta_corregida["tema"], "Misterios Acuaticos")
        self.assertEqual(meta_corregida["voz"], "Alonso")

    def test_upsert_idempotente(self):
        # 1. Upsert video inicial
        v1 = {
            "video_id": "V001",
            "canal": "Código OcultoTV",
            "titulo": "Prueba Inicial",
            "formato": "largo_original",
            "duracion_s": 600.0,
            "fecha_publicacion": "2026-10-25",
            "hora_publicacion": "18:00:00",
        }
        upsert_video(self.con, v1)
        self.con.commit()

        cur = self.con.execute("SELECT COUNT(*) FROM videos WHERE video_id = 'V001'")
        self.assertEqual(cur.fetchone()[0], 1)

        # 2. Re-ejecutar con actualizacion (idempotencia sin duplicados)
        v1_act = dict(v1)
        v1_act["titulo"] = "Prueba Actualizada"
        upsert_video(self.con, v1_act)
        self.con.commit()

        cur = self.con.execute("SELECT COUNT(*), titulo FROM videos WHERE video_id = 'V001'")
        row = cur.fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], "Prueba Actualizada")

        # 3. Upsert métricas diarias
        m1 = {
            "video_id": "V001",
            "fecha": "2026-10-26",
            "vistas": 150,
            "minutos_vistos": 600.0,
            "duracion_media_s": 240.0,
            "pct_visto_medio": 40.0,
            "likes": 12,
            "comentarios": 3,
            "suscriptores_ganados": 2,
        }
        upsert_metrica_diaria(self.con, m1)
        self.con.commit()

        # Re-ejecutar metrica con mas vistas
        m1["vistas"] = 300
        upsert_metrica_diaria(self.con, m1)
        self.con.commit()

        cur_m = self.con.execute("SELECT COUNT(*), vistas FROM metricas_diarias WHERE video_id = 'V001' AND fecha = '2026-10-26'")
        row_m = cur_m.fetchone()
        self.assertEqual(row_m[0], 1)
        self.assertEqual(row_m[1], 300)

        # 4. Upsert retención y tráfico
        ret_pts = [
            {"video_id": "V001", "fecha_corte": "2026-10-26", "segundo_relativo": 0.0, "pct_audiencia": 100.0},
            {"video_id": "V001", "fecha_corte": "2026-10-26", "segundo_relativo": 30.0, "pct_audiencia": 65.0},
        ]
        upsert_retencion(self.con, ret_pts)
        upsert_retencion(self.con, ret_pts)  # duplicado seguro
        self.con.commit()

        cur_r = self.con.execute("SELECT COUNT(*) FROM retencion WHERE video_id = 'V001'")
        self.assertEqual(cur_r.fetchone()[0], 2)

        traf_pts = [
            {"video_id": "V001", "fecha": "2026-10-26", "fuente": "YT_SEARCH", "vistas": 120},
        ]
        upsert_trafico(self.con, traf_pts)
        upsert_trafico(self.con, traf_pts)  # duplicado seguro
        self.con.commit()

        cur_t = self.con.execute("SELECT COUNT(*) FROM trafico WHERE video_id = 'V001'")
        self.assertEqual(cur_t.fetchone()[0], 1)

    def test_bandera_muestra_chica_y_consultas(self):
        # Poblar datos controlados:
        # Grupo 1 (Muestra chica): Canal Código OcultoTV, formato 'largo_original' (1 solo video, 100 vistas < 500)
        upsert_video(self.con, {
            "video_id": "V_CHICO_1",
            "canal": "Código OcultoTV",
            "titulo": "Enigma 1",
            "formato": "largo_original",
            "tema": "Enigmas",
            "duracion_s": 600.0,
            "fecha_publicacion": "2026-10-28",
            "hora_publicacion": "14:00:00",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "V_CHICO_1",
            "fecha": "2026-10-29",
            "vistas": 100,
            "minutos_vistos": 400.0,
            "duracion_media_s": 240.0,
            "pct_visto_medio": 40.0,
        })

        # Grupo 2 (Confiable): Canal Código OcultoTV, formato 'recopilacion' (3 videos, 300 vistas c/u = 900 vistas >= 500)
        for i in (1, 2, 3):
            vid = f"V_GRANDE_{i}"
            upsert_video(self.con, {
                "video_id": vid,
                "canal": "Código OcultoTV",
                "titulo": f"Compilacion {i}",
                "formato": "recopilacion",
                "tema": "Compilaciones",
                "duracion_s": 1200.0,
                "fecha_publicacion": "2026-10-28",
                "hora_publicacion": "18:00:00",
            })
            upsert_metrica_diaria(self.con, {
                "video_id": vid,
                "fecha": "2026-10-29",
                "vistas": 300,
                "minutos_vistos": 1500.0,
                "duracion_media_s": 300.0,
                "pct_visto_medio": 55.0,
            })

        # Grupo 3 (Novelas): Novelas Express MX, 2 capítulos consecutivos de una serie
        upsert_video(self.con, {
            "video_id": "NOV_01",
            "canal": "Novelas Express MX",
            "titulo": "Destino Fatal | Cap 1",
            "formato": "novela_cap",
            "serie": "Destino Fatal",
            "capitulo": 1,
            "tema": "Destino Fatal",
            "duracion_s": 500.0,
            "fecha_publicacion": "2026-10-27",
            "hora_publicacion": "20:00:00",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "NOV_01",
            "fecha": "2026-10-29",
            "vistas": 600,
            "minutos_vistos": 2500.0,
            "duracion_media_s": 250.0,
            "pct_visto_medio": 50.0,
        })

        upsert_video(self.con, {
            "video_id": "NOV_02",
            "canal": "Novelas Express MX",
            "titulo": "Destino Fatal | Cap 2",
            "formato": "novela_cap",
            "serie": "Destino Fatal",
            "capitulo": 2,
            "tema": "Destino Fatal",
            "duracion_s": 500.0,
            "fecha_publicacion": "2026-10-28",
            "hora_publicacion": "20:00:00",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "NOV_02",
            "fecha": "2026-10-29",
            "vistas": 450,
            "minutos_vistos": 1800.0,
            "duracion_media_s": 240.0,
            "pct_visto_medio": 48.0,
        })
        self.con.commit()

        # Probar formato_vs_retencion.sql
        cols, filas_fmt = ejecutar_consulta(self.con, CONSULTAS_DIR / "formato_vs_retencion.sql")
        self.assertIn("muestra_chica", cols)
        mapa_fmt = {f["formato"]: f for f in filas_fmt if f["canal"] == "Código OcultoTV"}
        self.assertEqual(mapa_fmt["largo_original"]["muestra_chica"], 1)  # Muestra chica (< 3 videos y < 500 v)
        self.assertEqual(mapa_fmt["recopilacion"]["muestra_chica"], 0)    # Confiable (3 videos, 900 v)

        # Probar novelas_por_capitulo.sql
        cols_nov, filas_nov = ejecutar_consulta(self.con, CONSULTAS_DIR / "novelas_por_capitulo.sql")
        self.assertIn("caida_retencion_vs_anterior", cols_nov)
        cap1 = [f for f in filas_nov if f["capitulo"] == 1][0]
        cap2 = [f for f in filas_nov if f["capitulo"] == 2][0]
        self.assertIsNone(cap1["caida_retencion_vs_anterior"])
        # Cap 2: 48.0 - 50.0 = -2.0
        self.assertEqual(cap2["caida_retencion_vs_anterior"], -2.0)

        # Probar ab_largos.sql
        cols_ab, filas_ab = ejecutar_consulta(self.con, CONSULTAS_DIR / "ab_largos.sql")
        self.assertIn("semana", cols_ab)
        self.assertIn("muestra_chica", cols_ab)

        # Probar horario.sql
        cols_h, filas_h = ejecutar_consulta(self.con, CONSULTAS_DIR / "horario.sql")
        self.assertIn("dia_semana", cols_h)
        self.assertIn("hora_publicacion", cols_h)

        # Probar top_temas.sql
        cols_t, filas_t = ejecutar_consulta(self.con, CONSULTAS_DIR / "top_temas.sql")
        self.assertIn("retencion_media", cols_t)

    def test_generacion_reporte_md(self):
        # Poblar al menos un video para probar el generador de reportes
        upsert_video(self.con, {
            "video_id": "REP_01",
            "canal": "Código OcultoTV",
            "titulo": "Reporte Test",
            "formato": "largo_original",
            "duracion_s": 400.0,
            "fecha_publicacion": "2026-10-28",
            "hora_publicacion": "15:00:00",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "REP_01",
            "fecha": "2026-10-29",
            "vistas": 120,
            "minutos_vistos": 300.0,
            "duracion_media_s": 150.0,
            "pct_visto_medio": 37.5,
        })
        self.con.commit()

        salida_md = Path(self.temp_dir.name) / "test_reporte.md"
        reporte_path = generar_reporte_md(
            db_path=self.db_path,
            consultas_dir=CONSULTAS_DIR,
            salida_md=salida_md,
        )
        self.assertTrue(reporte_path.exists())
        contenido = reporte_path.read_text(encoding="utf-8")

        self.assertIn("## Conclusiones con Confianza", contenido)
        self.assertIn("## Señales Débiles", contenido)
        self.assertIn("## Tablas Detalladas por Consulta", contenido)


if __name__ == "__main__":
    unittest.main()
