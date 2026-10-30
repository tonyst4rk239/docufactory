"""Pruebas unitarias para la normalización automática de brillo entre escenas."""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.edicion import (
    calcular_ajustes_luminancia,
    construir_filtro_color_textura,
    medir_luminancia_media,
)


class TestNormalizarBrillo(unittest.TestCase):
    def test_calcular_ajustes_sin_escenas_o_una_sola(self):
        self.assertEqual(calcular_ajustes_luminancia([]), [])
        self.assertEqual(calcular_ajustes_luminancia([120.0]), [0.0])

    def test_salto_pequeno_sin_ajuste(self):
        # Salto de 15 puntos <= 40: no debe alterar ninguna escena
        lums = [100.0, 115.0]
        ajustes = calcular_ajustes_luminancia(lums, umbral_salto=40.0)
        self.assertEqual(ajustes, [0.0, 0.0])

    def test_salto_grande_ajusta_escena_brillante_posterior(self):
        # Escena 1 (60) a Escena 2 (180): salto de 120 > 40
        # Escena 2 es la más brillante y debe ajustarse a 120.0
        lums = [60.0, 180.0]
        ajustes = calcular_ajustes_luminancia(lums, umbral_salto=40.0, target_y=120.0)
        self.assertEqual(len(ajustes), 2)
        self.assertEqual(ajustes[0], 0.0)
        # delta = (120 - 180) / 255 = -60 / 255 = -0.23529...
        self.assertAlmostEqual(ajustes[1], -60.0 / 255.0, places=3)

    def test_salto_grande_ajusta_escena_brillante_anterior(self):
        # Escena 1 (175) a Escena 2 (70): salto de 105 > 40
        # Escena 1 es la más brillante y debe ajustarse a 120.0
        lums = [175.0, 70.0]
        ajustes = calcular_ajustes_luminancia(lums, umbral_salto=40.0, target_y=120.0)
        self.assertEqual(len(ajustes), 2)
        self.assertAlmostEqual(ajustes[0], -55.0 / 255.0, places=3)
        self.assertEqual(ajustes[1], 0.0)

    def test_ambas_escenas_brillantes_sin_choque(self):
        # Escenas 1 (170) y 2 (180): salto de 10 <= 40: no hay choque brusco entre ellas
        lums = [170.0, 180.0]
        ajustes = calcular_ajustes_luminancia(lums, umbral_salto=40.0)
        self.assertEqual(ajustes, [0.0, 0.0])

    def test_escena_brillante_ya_en_rango_target(self):
        # Escena 1 (50) a Escena 2 (120): salto de 70 > 40, pero la brillante (120) ya está en 115-125
        lums = [50.0, 120.0]
        ajustes = calcular_ajustes_luminancia(lums, umbral_salto=40.0, target_y=120.0, rango_target=(115.0, 125.0))
        self.assertEqual(ajustes, [0.0, 0.0])

    def test_secuencia_con_varias_escenas_y_saltos(self):
        # Secuencia: oscura (50) -> brillante (190) -> oscura (50) -> muy brillante (200)
        lums = [50.0, 190.0, 50.0, 200.0]
        ajustes = calcular_ajustes_luminancia(lums, umbral_salto=40.0, target_y=120.0)
        self.assertEqual(len(ajustes), 4)
        self.assertEqual(ajustes[0], 0.0)
        self.assertAlmostEqual(ajustes[1], (120.0 - 190.0) / 255.0, places=3)
        self.assertEqual(ajustes[2], 0.0)
        self.assertAlmostEqual(ajustes[3], (120.0 - 200.0) / 255.0, places=3)

    def test_manejo_valores_none(self):
        # Si alguna toma no pudo medirse (None), usa valor objetivo neutral sin fallar
        lums = [50.0, None, 190.0]
        ajustes = calcular_ajustes_luminancia(lums, umbral_salto=40.0, target_y=120.0)
        self.assertEqual(len(ajustes), 3)

    def test_construir_filtro_color_respeta_tono_y_aplica_ajuste(self):
        # Con tono "misterio": base brightness es -0.01, contrast 1.06, saturation 0.85
        filtro_base = construir_filtro_color_textura(mood="misterio", tono="misterio", ajuste_brillo=0.0)
        filtro_ajustado = construir_filtro_color_textura(mood="misterio", tono="misterio", ajuste_brillo=-0.20)

        self.assertIn("eq=saturation=0.85:contrast=1.06:brightness=-0.01", filtro_base)
        self.assertIn("eq=saturation=0.85:contrast=1.06:brightness=-0.21", filtro_ajustado)

        # El balance de color y curves deben mantenerse idénticos (respetando el tono)
        self.assertIn("colorbalance=rs=-0.03:gs=0.00:bs=0.05", filtro_base)
        self.assertIn("colorbalance=rs=-0.03:gs=0.00:bs=0.05", filtro_ajustado)
        self.assertIn("curves=master='0/0.02 0.18/0.18 0.50/0.50 0.85/0.86 1/1'", filtro_base)
        self.assertIn("curves=master='0/0.02 0.18/0.18 0.50/0.50 0.85/0.86 1/1'", filtro_ajustado)

    def test_medir_luminancia_archivo_inexistente(self):
        self.assertIsNone(medir_luminancia_media(Path("archivo_inexistente_123.mp4")))

    def test_medir_luminancia_asset_real_con_ffmpeg(self):
        ruta_img = Path("assets/host/explicando_cerrada.png")
        if ruta_img.exists():
            lum = medir_luminancia_media(ruta_img)
            self.assertIsNotNone(lum)
            self.assertGreater(lum, 10.0)
            self.assertLess(lum, 100.0)




class TestNormalizacionPostGrado(unittest.TestCase):
    def test_aclara_toma_casi_negra(self):
        aj = calcular_ajustes_luminancia([20.0, 110.0], umbral_salto=40.0, umbral_oscuro=45.0, target_oscuro=70.0)
        self.assertAlmostEqual(aj[0], 50.0 / 255.0, places=3)
        self.assertEqual(aj[1], 0.0)

    def test_no_toca_oscura_moderada(self):
        # 73 -> 120: salto > 40 pero ninguna fuera de rango (73 > umbral_oscuro, 120 en rango)
        self.assertEqual(calcular_ajustes_luminancia([73.0, 120.0]), [0.0, 0.0])

    def test_normalizar_clips_usa_luma_renderizada_y_refina(self):
        from unittest import mock
        import src.edicion as ed
        estado = {"a": 73.0, "b": 155.0}
        ajustes_hechos = {}

        def medir(ruta, ffmpeg=None):
            return estado[str(ruta)]

        def rerender(i, ajuste):
            ajustes_hechos[i] = ajuste
            # respuesta no lineal: el grado atenúa el cambio
            estado["b"] = 155.0 + ajuste * 255.0 * 0.8

        with mock.patch.object(ed, "medir_luminancia_media", side_effect=medir):
            aj = ed.normalizar_brillo_clips(["a", "b"], rerender, cfg_nb={})
        self.assertEqual(aj[0], 0.0)
        self.assertTrue(115.0 <= estado["b"] <= 125.0, estado["b"])
        self.assertNotIn(0, ajustes_hechos)


if __name__ == "__main__":
    unittest.main()
