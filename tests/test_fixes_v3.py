"""Pruebas: pausa de importar, revision.json sin SSML y modelos Gemini vigentes."""
import importlib
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import make_video
from src import config
from src.revision import _sin_ssml


class TestSinSSML(unittest.TestCase):
    def test_quita_breaks(self):
        t = 'Hola. <break time="400ms"/> Hoy veremos <emphasis>tres</emphasis> casos.'
        self.assertEqual(_sin_ssml(t), "Hola. Hoy veremos tres casos.")

    def test_vacio(self):
        self.assertEqual(_sin_ssml(None), "")


class TestModelos(unittest.TestCase):
    def test_default_y_retirado(self):
        with mock.patch.dict(os.environ, {"MODELO_GUION": "gemini-2.5-pro", "MODELO_ESTRUCTURA": ""}):
            importlib.reload(config)
            self.assertEqual(config.MODELO_GUION, "gemini-3.1-pro-preview")
            self.assertEqual(config.MODELO_ESTRUCTURA, "gemini-3.1-pro-preview")
        importlib.reload(config)

    def test_sin_referencias_2_5_pro(self):
        from pathlib import Path
        raiz = Path(config.__file__).resolve().parent.parent
        for f in list((raiz / "src").rglob("*.py")) + list((raiz / "src_tiktok").rglob("*.py")) + [raiz / "make_video.py", raiz / "make_tiktok.py"]:
            txt = f.read_text(encoding="utf-8")
            if f.name == "config.py":
                txt = txt.split("MODELOS_RETIRADOS")[0]
            self.assertNotIn("gemini-2.5-pro", txt, f"{f} referencia gemini-2.5-pro")


class TestImportarPausa(unittest.TestCase):
    def _args(self, auto):
        return SimpleNamespace(guion_json="x.json", auto=auto, solo_guion=False, reusar=False, sin_host=False)

    def _run(self, auto):
        p = SimpleNamespace(carpeta="c", datos={"slug": "s"}, ruta=lambda *a: "r")
        g = SimpleNamespace(titulo_trabajo="t", escenas=[1], top_n=3)
        with mock.patch("src.guion.importar_guion_archivo", return_value=(p, g, [])), \
             mock.patch.object(make_video, "cmd_preparar", return_value=0) as prep, \
             mock.patch.object(make_video, "cmd_continuar", return_value=0) as cont:
            self.assertEqual(make_video.cmd_importar(self._args(auto)), 0)
        return prep, cont

    def test_sin_auto_pausa(self):
        prep, cont = self._run(False)
        prep.assert_called_once()
        cont.assert_not_called()

    def test_con_auto_completo(self):
        prep, cont = self._run(True)
        cont.assert_called_once()
        prep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
