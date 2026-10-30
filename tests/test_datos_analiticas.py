import unittest
from datos.analiticas import (
    clasificar_sentimiento,
    detectar_pide_segunda_parte,
    detectar_tema_sugerido,
    actualizar_facebook,
    actualizar_tiktok,
)


class TestAnaliticas(unittest.TestCase):
    def test_clasificar_sentimiento(self):
        self.assertEqual(clasificar_sentimiento("Excelente documental, me encantó la edición"), "+")
        self.assertEqual(clasificar_sentimiento("Muy aburrido y falso, puro clickbait y pérdida de tiempo"), "-")
        self.assertEqual(clasificar_sentimiento("El caso ocurrió en 1994 en un poblado de Canadá."), "=")

    def test_detectar_pide_segunda_parte(self):
        self.assertTrue(detectar_pide_segunda_parte("Por favor haz la parte 2 ya!"))
        self.assertTrue(detectar_pide_segunda_parte("Esperando con ansias la segunda parte"))
        self.assertTrue(detectar_pide_segunda_parte("Habrá pt 2 de esta historia?"))
        self.assertFalse(detectar_pide_segunda_parte("Me pareció un caso muy curioso."))

    def test_detectar_tema_sugerido(self):
        tema1 = detectar_tema_sugerido("Haz un video sobre el caso de las niñas de Alcàsser")
        self.assertIsNotNone(tema1)
        self.assertIn("Alcàsser", tema1)

        tema2 = detectar_tema_sugerido("Para la próxima habla del misterio del paso Dyatlov")
        self.assertIsNotNone(tema2)
        self.assertIn("Dyatlov", tema2)

        self.assertIsNone(detectar_tema_sugerido("Buen video amigos sigan así."))

    def test_stubs_redes(self):
        import os
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"DOCUFACTORY_DB": os.path.join(tmp, "t.db")}):
            res_fb = actualizar_facebook()
            self.assertIn("videos_procesados", res_fb)
            res_tt = actualizar_tiktok()
            self.assertIn("videos_procesados", res_tt)


if __name__ == "__main__":
    unittest.main()
