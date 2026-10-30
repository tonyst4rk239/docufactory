"""Pruebas unitarias para datos/db.py y el esquema SQLite."""
import sqlite3
import unittest
from pathlib import Path

from datos.db import (
    analizar_caracteristicas_titulo,
    analizar_legibilidad_guion,
    guardar_audio,
    guardar_escenas,
    guardar_guion,
    guardar_miniatura,
    guardar_produccion,
    guardar_publicacion,
    guardar_ritmo,
    guardar_titulo_features,
    guardar_tomas,
    guardar_video,
    guardar_analitica_diaria,
    guardar_curva_retencion,
    guardar_comentarios,
    inicializar_db,
)


class TestDatosDB(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON;")
        inicializar_db(con=self.con)

    def tearDown(self):
        self.con.close()

    def test_tablas_creadas(self):
        cur = self.con.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tablas = {r["name"] for r in cur.fetchall()}
        esperadas = {
            "videos", "guion", "escenas", "tomas", "ritmo", "audio",
            "miniatura", "titulo_features", "produccion", "publicaciones",
            "analiticas_diarias", "retencion_curva", "comentarios",
        }
        self.assertTrue(esperadas.issubset(tablas))

    def test_guardar_video_y_relaciones(self):
        vid_id = "test_video_001"
        guardar_video({
            "id": vid_id,
            "slug": vid_id,
            "formato": "largo",
            "tema": "El Misterio de la Atlántida",
            "tono": "misterio",
            "duracion_s": 540.0,
            "voz": "es-US-AlonsoNeural",
        }, con=self.con)

        # Verificar video
        r = self.con.execute("SELECT * FROM videos WHERE id = ?", (vid_id,)).fetchone()
        self.assertIsNotNone(r)
        self.assertEqual(r["tema"], "El Misterio de la Atlántida")

        # Guardar guion
        guardar_guion({
            "video_id": vid_id,
            "palabras_totales": 1250,
            "legibilidad": 65.5,
            "tipo_gancho": "pregunta",
        }, con=self.con)
        rg = self.con.execute("SELECT * FROM guion WHERE video_id = ?", (vid_id,)).fetchone()
        self.assertEqual(rg["palabras_totales"], 1250)

        # Guardar escenas
        guardar_escenas(vid_id, [
            {"n_escena": 1, "inicio_s": 0.0, "fin_s": 15.0, "tipo": "gancho", "texto": "¿Existió realmente?"},
            {"n_escena": 2, "inicio_s": 15.0, "fin_s": 45.0, "tipo": "desarrollo", "texto": "Los relatos de Platón..."},
        ], con=self.con)
        resc = self.con.execute("SELECT COUNT(*) as c FROM escenas WHERE video_id = ?", (vid_id,)).fetchone()
        self.assertEqual(resc["c"], 2)

        # Guardar tomas
        guardar_tomas(vid_id, [
            {"n_escena": 1, "inicio_s": 0.0, "fin_s": 4.5, "archivo": "mar.mp4", "brillo_medio": 118.2},
            {"n_escena": 1, "inicio_s": 4.5, "fin_s": 15.0, "archivo": "ruinas.mp4", "brillo_medio": 95.0},
        ], con=self.con)
        rt = self.con.execute("SELECT COUNT(*) as c FROM tomas WHERE video_id = ?", (vid_id,)).fetchone()
        self.assertEqual(rt["c"], 2)

        # Guardar ritmo y audio
        guardar_ritmo({"video_id": vid_id, "cortes_por_minuto": 12.5, "duracion_media_toma_s": 4.2}, con=self.con)
        guardar_audio({"video_id": vid_id, "lufs": -16.0, "musica": "misterio_track_1"}, con=self.con)

        # Guardar miniatura y titulo_features
        guardar_miniatura({"video_id": vid_id, "archivo": "miniatura.jpg", "tiene_cara": 1}, con=self.con)
        guardar_titulo_features({"video_id": vid_id, "largo": 45, "tiene_numero": 1}, con=self.con)

        # Guardar produccion
        guardar_produccion({"video_id": vid_id, "tomas_rechazadas_lente": 3, "motivos_rechazo": ["muy oscuro"]}, con=self.con)

        # Guardar publicaciones
        pub_id = guardar_publicacion({
            "video_id": vid_id,
            "plataforma": "youtube",
            "url": "https://youtu.be/abcd1234efg",
            "video_platform_id": "abcd1234efg",
        }, con=self.con)
        self.assertGreater(pub_id, 0)

        # Guardar analiticas diarias
        guardar_analitica_diaria({
            "video_id": vid_id,
            "plataforma": "youtube",
            "fecha": "2026-10-25",
            "vistas": 1500,
            "likes": 120,
            "ctr_miniatura": 8.5,
        }, con=self.con)

        # Guardar curva de retención
        guardar_curva_retencion(vid_id, "youtube", [(0.0, 1.0), (10.0, 0.85), (30.0, 0.72)], con=self.con)
        r_curva = self.con.execute("SELECT COUNT(*) as c FROM retencion_curva WHERE video_id = ?", (vid_id,)).fetchone()
        self.assertEqual(r_curva["c"], 3)

        # Guardar comentarios
        guardar_comentarios([{
            "video_id": vid_id,
            "plataforma": "youtube",
            "fecha": "2026-10-26",
            "texto": "Excelente documental, ¿podrían hacer una parte 2?",
            "sentimiento": "positivo",
            "pide_segunda_parte": 1,
            "comment_id": "comm_999",
        }], con=self.con)
        r_com = self.con.execute("SELECT * FROM comentarios WHERE comment_id = 'comm_999'").fetchone()
        self.assertEqual(r_com["pide_segunda_parte"], 1)

    def test_analizar_caracteristicas_titulo(self):
        tit = "¡TOP 5 Misterios del Triángulo de las Bermudas! 😱"
        feat = analizar_caracteristicas_titulo(tit)
        self.assertEqual(feat["tiene_numero"], 1)
        self.assertEqual(feat["tiene_emoji"], 1)
        self.assertEqual(feat["tiene_signos"], 1)
        self.assertGreater(feat["pct_mayusculas"], 10.0)

    def test_analizar_legibilidad_guion(self):
        texto = "En 1945, cinco aviones desaparecieron cerca de Florida. ¿Qué ocurrió realmente? Documentos desclasificados de la CIA revelan detalles."
        info = analizar_legibilidad_guion(texto)
        self.assertGreater(info["palabras_totales"], 10)
        self.assertEqual(info["menciona_caso_real"], 1)
        self.assertIn("1945", info["fechas"])
        self.assertGreaterEqual(info["n_preguntas_abiertas"], 1)


if __name__ == "__main__":
    unittest.main()
