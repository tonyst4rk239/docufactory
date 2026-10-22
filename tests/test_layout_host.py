"""Tarea 1: los textos (.ass TOP #N / texto_pantalla) nunca solapan la caja del host."""
import unittest

from src import config
from src.layout import (
    ALTO, ANCHO, ajustar_fuente, caja_bloque, caja_host, partir_en_lineas, zona_texto,
)

TITULOS = ["TOP #5", "LA BARRERA QUE SE MUEVE SOLA", "AFIRMACIÓN DE MAUSSAN · SIN PRUEBAS",
           "LA CRIATURA DEL VALLE DE JUÁREZ", "OCTUBRE 2026"]


class TestLayoutHost(unittest.TestCase):
    def test_sin_solape_todas_las_poses(self):
        for pose in config.POSES:
            for lado in ("izquierda", "derecha"):
                host = caja_host(pose, lado)
                zona = zona_texto(host)
                self.assertFalse(zona.solapa(host), f"zona solapa host ({pose}, {lado})")
                cx = int(zona.x + zona.w / 2)
                for t in TITULOS:
                    lineas = partir_en_lineas(t, 116, zona.w)
                    fs = ajustar_fuente([f"  {l}  " for l in lineas], 184, zona.w)
                    bloque = caja_bloque([(f"  {l}  ", fs) for l in lineas], cx, 70)
                    self.assertFalse(bloque.solapa(host), f"'{t}' solapa host ({pose}, {lado})")
                    self.assertGreaterEqual(bloque.x, 0)
                    self.assertLessEqual(bloque.x2, ANCHO)
                    if lado == "izquierda":
                        self.assertGreater(bloque.x, host.x2)
                    else:
                        self.assertLess(bloque.x2, host.x)

    def test_sin_host_usa_pantalla_completa(self):
        z = zona_texto(caja_host("explicando", "izquierda", visible=False))
        self.assertGreater(z.w, ANCHO * 0.9)

    def test_parte_titulos_largos(self):
        zona = zona_texto(caja_host("duda", "izquierda"))
        self.assertEqual(len(partir_en_lineas("AFIRMACIÓN DE MAUSSAN · SIN PRUEBAS", 116, zona.w)), 2)

    def test_host_pegado_abajo(self):
        h = caja_host("explicando", "derecha")
        self.assertEqual(h.y2, ALTO)
        self.assertEqual(h.x2, ANCHO - 80)


if __name__ == "__main__":
    unittest.main()
