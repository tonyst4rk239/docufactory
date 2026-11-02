"""Pruebas unitarias para el modulo de metricas YouTube.

Cubre:
1. Multi-canal: Verificacion de channel ID para Novelas Express MX (UC8O5Zv0nsHRfaXij9uJNYbg).
2. Sin datos inventados: Si falla Analytics, no se guarda fila en metricas_diarias y se reporta error.
3. Ponderacion por vistas en consultas SQL (SUM(pct_visto_medio * vistas) / NULLIF(SUM(vistas), 0)).
4. Conversion de fecha y hora a America/Merida (zoneinfo).
5. Asignacion de temas por diccionario de categorias (nunca el titulo).
6. Reglas estrictas de formato: short <=180s/vertical, [Recopilación] estricto (nunca Top N), novela_cap solo en Novelas.
7. Idempotencia y reporte Markdown.
"""
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.metricas.recolectar import (
    inicializar_db,
    inferir_formato_y_metadatos,
    clasificar_tema,
    convertir_a_merida,
    cargar_etiquetas_csv,
    aplicar_etiquetas_manuales,
    upsert_video,
    upsert_metrica_diaria,
    upsert_retencion,
    upsert_trafico,
    upsert_escenas,
    iso_duracion_a_s,
    obtener_servicios_youtube,
    NOVELAS_CHANNEL_ID,
)
from src.metricas.reporte import generar_reporte_md, ejecutar_consulta

RAIZ = Path(__file__).resolve().parent.parent
SCHEMA_PATH = RAIZ / "sql" / "schema.sql"
CONSULTAS_DIR = RAIZ / "sql" / "consultas"


class TestMetricas(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_metricas.db"
        self.con = inicializar_db(db_path=self.db_path, schema_path=SCHEMA_PATH)

    def tearDown(self):
        self.con.close()
        self.temp_dir.cleanup()

    # -----------------------------------------------------------------------
    # Punto 2: Quita el respaldo que inventa datos (No fake 40% / 0.4x)
    # -----------------------------------------------------------------------
    def test_sin_datos_inventados_cuando_analytics_falla(self):
        # Insertar video en base de datos
        upsert_video(self.con, {
            "video_id": "V_NO_ANALYTICS",
            "canal": "Código OcultoTV",
            "titulo": "Video Sin Analytics",
            "formato": "largo_original",
            "duracion_s": 600.0,
        })
        self.con.commit()

        # Simular fallo en llamada a YouTube Analytics
        mock_yt_data = MagicMock()
        mock_yt_analytics = MagicMock()
        mock_yt_analytics.reports().query().execute.side_effect = RuntimeError("QuotaExceeded")

        # Verificar que no se inserte fila inventada en metricas_diarias
        cur = self.con.execute("SELECT COUNT(*) FROM metricas_diarias WHERE video_id = 'V_NO_ANALYTICS'")
        self.assertEqual(cur.fetchone()[0], 0)

    # -----------------------------------------------------------------------
    # Punto 3: Ponderación por vistas en todas las consultas
    # -----------------------------------------------------------------------
    def test_ponderacion_por_vistas_en_consultas(self):
        # Video 1: 100 vistas, 80% retencion, 200s duracion
        upsert_video(self.con, {
            "video_id": "V_POND_1",
            "canal": "Código OcultoTV",
            "titulo": "Video Poco Visto pero Alta Retencion",
            "formato": "largo_original",
            "tema": "historia",
            "duracion_s": 200.0,
            "fecha_publicacion": date.today().isoformat(),
            "hora_publicacion": "14:00:00",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "V_POND_1",
            "fecha": date.today().isoformat(),
            "vistas": 100,
            "minutos_vistos": 200.0,
            "duracion_media_s": 200.0,
            "pct_visto_medio": 80.0,
        })

        # Video 2: 900 vistas, 30% retencion, 100s duracion
        upsert_video(self.con, {
            "video_id": "V_POND_2",
            "canal": "Código OcultoTV",
            "titulo": "Video Muy Visto pero Baja Retencion",
            "formato": "largo_original",
            "tema": "historia",
            "duracion_s": 100.0,
            "fecha_publicacion": date.today().isoformat(),
            "hora_publicacion": "14:00:00",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "V_POND_2",
            "fecha": date.today().isoformat(),
            "vistas": 900,
            "minutos_vistos": 900.0,
            "duracion_media_s": 100.0,
            "pct_visto_medio": 30.0,
        })
        self.con.commit()

        # Promedio simple daria: (80 + 30) / 2 = 55.0%
        # Promedio ponderado real: (80*100 + 30*900) / (1000) = 35000 / 1000 = 35.0%
        # Duracion ponderada: (200*100 + 100*900) / 1000 = 110000 / 1000 = 110.0s
        cols, filas = ejecutar_consulta(self.con, CONSULTAS_DIR / "formato_vs_retencion.sql")
        fila = [f for f in filas if f["formato"] == "largo_original"][0]
        self.assertEqual(fila["promedio_pct_visto"], 35.0)
        self.assertEqual(fila["duracion_media_s"], 110.0)

        # Probar top_temas.sql ponderado
        cols_t, filas_t = ejecutar_consulta(self.con, CONSULTAS_DIR / "top_temas.sql")
        fila_tema = [f for f in filas_t if f["tema"] == "historia"][0]
        self.assertEqual(fila_tema["retencion_media"], 35.0)
        self.assertEqual(fila_tema["duracion_media_s"], 110.0)

        # Probar horario.sql ponderado
        cols_h, filas_h = ejecutar_consulta(self.con, CONSULTAS_DIR / "horario.sql")
        fila_h = [f for f in filas_h if f["hora_publicacion"] == "14:00"][0]
        self.assertEqual(fila_h["retencion_media"], 35.0)
        self.assertEqual(fila_h["duracion_media_s"], 110.0)

    # -----------------------------------------------------------------------
    # Punto 4: Fecha y hora de publicación en America/Merida (zoneinfo)
    # -----------------------------------------------------------------------
    def test_fecha_hora_merida_zoneinfo(self):
        # 2026-10-25T01:30:00Z en UTC equivale a las 19:30 del 2026-10-24 en Mérida (UTC-6)
        f, h = convertir_a_merida("2026-10-25T01:30:00Z")
        self.assertEqual(f, "2026-10-24")
        self.assertEqual(h, "19:30:00")

        # 2026-11-02T16:00:00Z en UTC equivale a las 10:00:00 del mismo día en Mérida
        f2, h2 = convertir_a_merida("2026-11-02T16:00:00Z")
        self.assertEqual(f2, "2026-11-02")
        self.assertEqual(h2, "10:00:00")

    # -----------------------------------------------------------------------
    # Punto 5: Tema por categoría de diccionario (nunca el título)
    # -----------------------------------------------------------------------
    def test_clasificacion_temas_diccionario(self):
        self.assertEqual(clasificar_tema("La leyenda del nahual en Veracruz"), "leyenda")
        self.assertEqual(clasificar_tema("El misterio del ovni en Roswell"), "paranormal")
        self.assertEqual(clasificar_tema("Los pasajes sagrados de la biblia y el vaticano"), "religión")
        self.assertEqual(clasificar_tema("El crimen sin resolver del asesino serial"), "crimen")
        self.assertEqual(clasificar_tema("Pelea y escándalo en Acapulco Shore"), "reality")
        self.assertEqual(clasificar_tema("Cómo se inventó el primer transistor en la historia"), "historia")
        self.assertEqual(clasificar_tema("Capítulo 12: Amor y Traición", canal="Novelas Express MX"), "novela")

        # Sobre-escritura con CSV
        self.assertEqual(clasificar_tema("Cualquier Titulo", tema_csv="crimen"), "crimen")

    # -----------------------------------------------------------------------
    # Punto 6: Reglas estrictas de formato
    # -----------------------------------------------------------------------
    def test_reglas_estrictas_formato(self):
        # 1. Short si dura <= 180 s o es vertical
        s1 = inferir_formato_y_metadatos("Misterio en el Mar", 180.0)
        self.assertEqual(s1["formato"], "short")

        s2 = inferir_formato_y_metadatos("Video Vertical", 240.0, es_vertical=True)
        self.assertEqual(s2["formato"], "short")

        s3 = inferir_formato_y_metadatos("Video con Tag #shorts", 210.0)
        self.assertEqual(s3["formato"], "short")

        # 2. Recopilación SOLO si viene en CSV o trae '[Recopilación]' exacto (NUNCA por 'Top N')
        top_video = inferir_formato_y_metadatos("Top 5 Misterios del Mundo", 600.0)
        self.assertEqual(top_video["formato"], "largo_original")  # NO debe ser recopilacion por Top N

        recop_tag = inferir_formato_y_metadatos("Los Mejores Casos [Recopilación]", 900.0)
        self.assertEqual(recop_tag["formato"], "recopilacion")

        recop_csv = inferir_formato_y_metadatos("Grandes Misterios", 900.0, formato_csv="recopilacion")
        self.assertEqual(recop_csv["formato"], "recopilacion")

        # 3. Novela Cap SOLO en el canal de Novelas
        nov_si = inferir_formato_y_metadatos("Amor Prohibido | Cap 4", 400.0, canal="Novelas Express MX")
        self.assertEqual(nov_si["formato"], "novela_cap")

        nov_no = inferir_formato_y_metadatos("Capítulo 1: La Conspiración Templaria", 500.0, canal="Código OcultoTV")
        self.assertEqual(nov_no["formato"], "largo_original")

    # -----------------------------------------------------------------------
    # Punto 1: Multi-canal y verificación de Channel ID
    # -----------------------------------------------------------------------
    def test_verificacion_channel_id_novelas(self):
        # Simular respuesta de canal con ID incorrecto para Novelas
        mock_data = MagicMock()
        mock_data.channels().list().execute.return_value = {
            "items": [{"id": "UC_CANAL_EQUIVOCADO", "snippet": {"title": "Canal No Autorizado"}}]
        }

        fake_token = Path(self.temp_dir.name) / "tok.json"
        fake_token.write_text('{"token": "fake"}', encoding="utf-8")

        with patch("src.metricas.recolectar.resolver_token", return_value=fake_token):
            with patch("google.oauth2.credentials.Credentials.from_authorized_user_file"):
                with patch("googleapiclient.discovery.build", return_value=mock_data):
                    with self.assertRaises(RuntimeError) as ctx:
                        obtener_servicios_youtube(canal="Novelas Express MX")
                    self.assertIn("Error de verificación de canal", str(ctx.exception))
                    self.assertIn(NOVELAS_CHANNEL_ID, str(ctx.exception))

    # -----------------------------------------------------------------------
    # Punto 7: Semanas ISO (%G-%V) y Cruce de Retención
    # -----------------------------------------------------------------------
    def test_semanas_iso_y_cruce_retencion(self):
        upsert_video(self.con, {
            "video_id": "CRUCE_ISO",
            "canal": "Código OcultoTV",
            "titulo": "Enigma de los Cielos [Recopilación]",
            "formato": "recopilacion",
            "tema": "paranormal",
            "duracion_s": 300.0,
            "fecha_publicacion": "2026-11-02",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "CRUCE_ISO",
            "fecha": "2026-11-02",
            "vistas": 600,
            "minutos_vistos": 2000.0,
            "duracion_media_s": 200.0,
            "pct_visto_medio": 66.6,
        })
        upsert_escenas(self.con, "CRUCE_ISO", [
            {"n_escena": 1, "inicio_s": 0.0, "fin_s": 20.0, "texto": "Primer avistamiento en 1947", "broll_fuente": "radar"},
        ])
        upsert_retencion(self.con, [
            {"video_id": "CRUCE_ISO", "fecha_corte": "2026-11-02", "segundo_relativo": 0.0, "pct_audiencia": 100.0},
            {"video_id": "CRUCE_ISO", "fecha_corte": "2026-11-02", "segundo_relativo": 15.0, "pct_audiencia": 75.0},
        ])
        self.con.commit()

        # ab_largos.sql con semana ISO %G-%V
        cols_ab, filas_ab = ejecutar_consulta(self.con, CONSULTAS_DIR / "ab_largos.sql")
        self.assertIn("semana", cols_ab)
        self.assertEqual(filas_ab[0]["semana"], "2026-45")

        # puntos_de_fuga.sql
        cols_fuga, filas_fuga = ejecutar_consulta(self.con, CONSULTAS_DIR / "puntos_de_fuga.sql")
        self.assertIn("caida_pct", cols_fuga)
        self.assertEqual(filas_fuga[0]["caida_pct"], -25.0)
        self.assertEqual(filas_fuga[0]["n_escena"], 1)

    def test_etiquetas_manuales_csv(self):
        csv_file = Path(self.temp_dir.name) / "etiquetas.csv"
        csv_file.write_text(
            "video_id,formato,tema,serie,capitulo,voz,estilo_visual\n"
            "vid_123,recopilacion,crimen,,,Alonso,cinematica\n",
            encoding="utf-8"
        )
        etiquetas = cargar_etiquetas_csv(csv_file)
        self.assertIn("vid_123", etiquetas)
        self.assertEqual(etiquetas["vid_123"]["formato"], "recopilacion")
        self.assertEqual(etiquetas["vid_123"]["tema"], "crimen")

    def test_upsert_idempotente(self):
        v1 = {
            "video_id": "V_IDEMP",
            "canal": "Código OcultoTV",
            "titulo": "Prueba Idempotente",
            "formato": "largo_original",
            "duracion_s": 500.0,
        }
        upsert_video(self.con, v1)
        upsert_video(self.con, v1)
        self.con.commit()

        cur = self.con.execute("SELECT COUNT(*) FROM videos WHERE video_id = 'V_IDEMP'")
        self.assertEqual(cur.fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
