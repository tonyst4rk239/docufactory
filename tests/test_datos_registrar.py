"""Pruebas unitarias para datos/registrar.py y deducción de slug."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from datos.db import inicializar_db
from datos.registrar import registrar_proyecto_completo
from src.estado import Proyecto
from subir_video import _deducir_slug


class TestDatosRegistrar(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.raiz = Path(self.temp_dir.name)
        self.db_path = self.raiz / "test.db"
        self.con = sqlite3.connect(str(self.db_path))
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON;")
        inicializar_db(con=self.con)

    def tearDown(self):
        self.con.close()
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

        # Verificar en base de datos real o por defecto
        # Comprobar que no arrojó excepciones y procesó el proyecto


if __name__ == "__main__":
    unittest.main()
