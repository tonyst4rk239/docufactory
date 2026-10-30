"""Pruebas unitarias para datos/registrar.py y deducción de slug."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import datos.db as db_mod
from datos.db import (
    _normalizar_estado,
    extraer_lugares,
    guardar_publicacion,
    inicializar_db,
    obtener_conexion,
)
from datos.registrar import registrar_proyecto_completo
from src.estado import Proyecto
from subir_video import _deducir_slug


class TestDatosRegistrar(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.raiz = Path(self.temp_dir.name)
        self.db_path = self.raiz / "test.db"
        # Todas las escrituras (incluidas las de registrar/guardar_*) van a la base temporal
        self._env_previo = os.environ.get("DOCUFACTORY_DB")
        os.environ["DOCUFACTORY_DB"] = str(self.db_path)
        self._real_mtime = db_mod.DB_PATH.stat().st_mtime if db_mod.DB_PATH.exists() else None
        self.con = sqlite3.connect(str(self.db_path))
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON;")
        inicializar_db(con=self.con)

    def tearDown(self):
        self.con.close()
        if self._env_previo is None:
            os.environ.pop("DOCUFACTORY_DB", None)
        else:
            os.environ["DOCUFACTORY_DB"] = self._env_previo
        # La base real no se toca
        real_mtime = db_mod.DB_PATH.stat().st_mtime if db_mod.DB_PATH.exists() else None
        self.assertEqual(real_mtime, self._real_mtime)
        self.temp_dir.cleanup()

    def test_deducir_slug(self):
        p1 = Path("proyectos/video_el_secreto_de_diddy/renders/video_con_voz_ia.mp4")
        self.assertEqual(_deducir_slug(p1), "el_secreto_de_diddy")

        p2 = Path("output/mi_video_especial_con_voz_ia.mp4")
        self.assertEqual(_deducir_slug(p2), "mi_video_especial")

    def test_registrar_proyecto_mock(self):
        # Crear estructura mínima de proyecto
        proj_dir = self.raiz / "video_misterio_prueba"
        proj_dir.mkdir(parents=True)
        (proj_dir / "guion").mkdir()
        (proj_dir / "b_roll").mkdir()
        (proj_dir / "renders").mkdir()

        # proyecto.json
        (proj_dir / "proyecto.json").write_text(json.dumps({
            "slug": "misterio_prueba",
            "tema": "El Misterio Prueba",
            "minutos": 1.0,
            "creado": "2026-10-29T12:00:00",
            "voz_usada": "es-US-AlonsoNeural",
        }), encoding="utf-8")

        # guion.json
        (proj_dir / "guion" / "guion.json").write_text(json.dumps({
            "titulo": "El Misterio de la Cámara Oculta",
            "tono": "misterio",
            "mood": "tension",
            "metadatos_youtube": {
                "titulos": ["El Misterio de la Cámara Oculta"],
                "descripcion": "Descripción del misterio #misterio #historia",
                "tags": ["misterio", "historia"],
            },
            "escenas": [
                {"id": 1, "voz": "¿Qué encontraron dentro?", "puesto": None, "host_visible": True, "music_mood": "tension"},
                {"id": 2, "voz": "Un cofre de 1920 con documentos oficiales.", "puesto": 1, "puesto_titulo": "EL COFRE", "host_visible": False, "music_mood": "misterio"},
            ],
        }), encoding="utf-8")

        p = Proyecto(proj_dir)
        ok = registrar_proyecto_completo(p, duraciones={1: 5.0, 2: 7.0})
        self.assertTrue(ok)

        fila = self.con.execute("SELECT * FROM videos WHERE id = 'misterio_prueba'").fetchone()
        self.assertIsNotNone(fila)
        self.assertIsNone(fila["costo_voz_usd"])
        self.assertIsNone(fila["tiempo_render_s"])
        mini = self.con.execute("SELECT * FROM miniatura WHERE video_id = 'misterio_prueba'").fetchone()
        self.assertIsNone(mini["archivo"])
        self.assertIsNone(mini["emocion_cara"])
        self.assertIsNone(mini["colores_dominantes"])
        aud = self.con.execute("SELECT * FROM audio WHERE video_id = 'misterio_prueba'").fetchone()
        self.assertIsNone(aud["pausa_media_s"])

    def test_reel_creditos_host_y_caption(self):
        proj = self.raiz / "video_reel_prueba"
        for d in ("guion", "b_roll", "renders", "publicacion"):
            (proj / d).mkdir(parents=True)
        (proj / "proyecto.json").write_text(json.dumps({
            "slug": "reel_prueba", "tema": "Reel prueba", "creado": "2026-10-29T12:00:00",
            "voz_reel": {"motor": "gemini", "voz": "Charon", "motivo_respaldo": None},
        }), encoding="utf-8")
        (proj / "guion" / "guion_tiktok.json").write_text(json.dumps({
            "titulo": "Reel prueba", "usar_avatar": False,
            "escenas": [{"id": 1, "voz": "Hola [pausa corta] mundo"}, {"id": 2, "voz": "Adiós"}],
        }), encoding="utf-8")
        (proj / "b_roll" / "creditos.json").write_text(json.dumps([
            {"escena": 1, "fuente": "Wikimedia Commons", "credito": "Canarian / Wikimedia Commons (CC BY-SA 4.0)",
             "url": "https://commons.wikimedia.org/wiki/File:X.jpg"},
            {"escena": 2, "fuente": "Pixabay", "credito": "antonlukin / Pixabay", "url": "https://pixabay.com/videos/id-1/",
             "encuadre": "fill"},
        ]), encoding="utf-8")
        (proj / "publicacion" / "caption.txt").write_text("Texto del reel #mictlan #xolo", encoding="utf-8")
        ok = registrar_proyecto_completo(Proyecto(proj), duraciones={1: 4.0, 2: 3.0})
        self.assertTrue(ok)
        v = self.con.execute("SELECT * FROM videos WHERE id = 'reel_prueba'").fetchone()
        self.assertEqual(v["voz"], "gemini:Charon")
        self.assertEqual(v["hashtags"], "#mictlan #xolo")
        from datos.registrar import _ahora_merida_iso
        self.assertTrue(_ahora_merida_iso(0).startswith("1969-12-31T18:00:00-06:00"))
        tomas = self.con.execute("SELECT * FROM tomas WHERE video_id = 'reel_prueba' ORDER BY inicio_s").fetchall()
        self.assertEqual([(t["inicio_s"], t["fin_s"]) for t in tomas], [(0.0, 4.0), (4.0, 7.0)])
        self.assertEqual(tomas[0]["fuente"], "commons")
        self.assertEqual(tomas[0]["autor"], "Canarian")
        self.assertEqual(tomas[0]["licencia"], "CC BY-SA 4.0")
        self.assertEqual(tomas[1]["fuente"], "pixabay")
        self.assertEqual(tomas[1]["licencia"], "Pixabay Content License")
        self.assertEqual(tomas[1]["modo"], "fill")
        self.assertEqual({t["aparece_host"] for t in tomas}, {0})
        self.assertEqual(self.con.execute("SELECT n_pausas FROM audio WHERE video_id='reel_prueba'").fetchone()[0], 1)

    def test_publicacion_sin_video_previo_y_estado(self):
        guardar_publicacion({"video_id": "nuevo_x", "plataforma": "youtube", "url": "https://youtu.be/abc",
                             "estado": "unlisted", "descripcion": "Hola #a #b"})
        guardar_publicacion({"video_id": "nuevo_x", "plataforma": "tiktok", "url": "https://www.tiktok.com/@c",
                             "estado": "publico"})
        filas = self.con.execute("SELECT plataforma, url, estado FROM publicaciones ORDER BY plataforma").fetchall()
        self.assertEqual([tuple(f) for f in filas],
                         [("tiktok", "https://www.tiktok.com/@c", "publico"), ("youtube", "https://youtu.be/abc", "oculto")])
        v = self.con.execute("SELECT hashtags FROM videos WHERE id='nuevo_x'").fetchone()
        self.assertEqual(v["hashtags"], "#a #b")

    def test_estado_y_lugares(self):
        self.assertEqual(_normalizar_estado("public"), "publico")
        self.assertEqual(_normalizar_estado("private"), "oculto")
        lug = extraer_lugares("En el Día de Muertos, según Sahagún, el perro cruzaba hacia el Mictlán en Oaxaca.")
        self.assertIn("Mictlán", lug)
        self.assertIn("Oaxaca", lug)
        self.assertNotIn("Muertos", lug)
        self.assertNotIn("Sahagún", lug)


if __name__ == "__main__":
    unittest.main()
