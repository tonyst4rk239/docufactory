import unittest

from src.edicion import construir_filtro_color_textura
from src.guion import Guion
from src.miniatura import elegir_estilo_miniatura, acortar_titulo

ESC = [{"id": 1, "voz": "hola", "broll_query_en": "x"}]


class TestTonoMiniatura(unittest.TestCase):
    def test_defaults_retrocompatibles(self):
        g = Guion.model_validate({"titulo_trabajo": "t", "escenas": ESC})
        self.assertEqual(g.tono, "misterio")
        self.assertTrue(g.usar_avatar)
        self.assertIsNone(g.miniatura)

    def test_usar_avatar_false_oculta_host(self):
        g = Guion.model_validate({"titulo_trabajo": "t", "usar_avatar": False, "escenas": ESC})
        self.assertFalse(g.escenas[0].host_visible)

    def test_tono_invalido(self):
        with self.assertRaises(Exception):
            Guion.model_validate({"titulo_trabajo": "t", "tono": "alegre", "escenas": ESC})
        self.assertEqual(Guion.model_validate({"titulo_trabajo": "t", "tono": "Polémica", "escenas": ESC}).tono, "polemica")

    def test_misterio_identico(self):
        self.assertEqual(construir_filtro_color_textura("tension"), construir_filtro_color_textura("tension", tono="misterio"))
        self.assertNotEqual(construir_filtro_color_textura("misterio"), construir_filtro_color_textura("misterio", tono="humor"))

    def test_estilo_determinista_y_sin_repetir(self):
        a = elegir_estilo_miniatura("slug1", "polemica")
        self.assertEqual(a, elegir_estilo_miniatura("slug1", "polemica"))
        b = elegir_estilo_miniatura("slug1", "polemica", evitar=a)
        self.assertNotEqual(a["layout"], b["layout"])
        self.assertEqual(elegir_estilo_miniatura("s", "humor", usar_avatar=False)["layout"], "sin_avatar")

    def test_acortar(self):
        self.assertLessEqual(len(acortar_titulo("5 videos paranormales captados en México este octubre… ¿qué hay detrás?")), 40)


if __name__ == "__main__":
    unittest.main()
