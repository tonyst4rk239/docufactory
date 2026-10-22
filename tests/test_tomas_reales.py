"""Tareas 2 y 3: clips reales EVIDENCIA (clips_fuente) y rotación de tomas de 3-5 s."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src import config
from src.guion import ClipFuente, Escena, validar_json_externo
from src.layout import caja_host
from src.tomas import (
    consultas_cortas, geometria_panel, misma_serie, montar_fondo_escena, planificar_cortes,
    planificar_segmentos, transformar_evidencia,
)

FFMPEG = config.ffmpeg_bin("ffmpeg") or "ffmpeg"


def _clip(ruta: Path, dur: float, color: str = "red", size: str = "640x360"):
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c={color}:s={size}:r=30", "-t", f"{dur}",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(ruta)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def _dur(ruta: Path) -> float:
    out = subprocess.run([config.ffmpeg_bin("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(ruta)], capture_output=True, text=True).stdout
    return float(out.strip() or 0)


class TestPlanificacion(unittest.TestCase):
    def test_cortes_3_a_5(self):
        for dur in (7.0, 12.3, 30.31, 34.42, 21.86):
            cortes = planificar_cortes(dur, 3.0, 5.0)
            self.assertAlmostEqual(sum(cortes), dur, places=2)
            for c in cortes:
                self.assertGreaterEqual(c, 3.0 - 1e-6)
                self.assertLessEqual(c, 5.0 + 1e-6)

    def test_reales_primero(self):
        cortes = planificar_cortes(30.0, 3.0, 5.0, fijos=[6.0, 4.0])
        self.assertEqual(cortes[:2], [6.0, 4.0])
        self.assertAlmostEqual(sum(cortes), 30.0, places=2)

    def test_consultas_cortas(self):
        qs = consultas_cortas(["dark empty desert highway night fog", "concrete road barriers highway overcast"])
        self.assertTrue(all(2 <= len(q.split()) <= 3 for q in qs))
        self.assertEqual(len(qs), len(set(qs)))

    def test_series_pixabay(self):
        self.assertTrue(misma_serie("pixabay:63974", {"pixabay:63970"}))
        self.assertFalse(misma_serie("pixabay:73290", {"pixabay:63970"}))

    def test_segmentos_sin_repetir_consecutivo(self):
        man = {"tomas": [
            {"archivo": "r1.mp4", "fuente": "real", "duracion": 5.0},
            {"archivo": "a.mp4", "fuente": "stock", "duracion_archivo": 20},
            {"archivo": "b.mp4", "fuente": "stock", "duracion_archivo": 20},
            {"archivo": "c.mp4", "fuente": "stock", "duracion_archivo": 20},
        ]}
        segs = planificar_segmentos(man, 30.0)
        self.assertEqual(segs[0]["fuente"], "real")
        for a, b in zip(segs, segs[1:]):
            self.assertNotEqual(a["archivo"], b["archivo"])
        self.assertAlmostEqual(sum(s["dur"] for s in segs), 30.0, places=2)


class TestEsquema(unittest.TestCase):
    def _guion(self, cf):
        return {"titulo": "T", "formato": "16:9", "mood": "misterio", "top_n": 1,
                "youtube_metadata": {"titulos": ["t"], "descripcion": "d", "tags": ["x"]},
                "capitulos": [{"escena_id": 1, "titulo": "c"}],
                "escenas": [{"id": 1, "puesto": 1, "puesto_titulo": "X", "voz": "Hola mundo.", "pose": "pensativo",
                             "broll_queries_en": ["dark night fog"], "broll_mood_keywords": ["dark"],
                             "broll_avoid_keywords": ["beach", "sunny", "happy"], "music_mood": "misterio",
                             "sfx": "ninguno", "clips_fuente": cf}],
                "fuentes_video": [{"url": "https://example.com/v", "credito": "x"}]}

    def _validar(self, datos):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "g.json"
            f.write_text(json.dumps(datos), encoding="utf-8")
            return validar_json_externo(f)

    def test_clips_fuente_valido(self):
        g, errores, avisos = self._validar(self._guion([{"url": "https://www.tiktok.com/@a/video/1", "inicio": 2, "duracion": 8, "credito": "TikTok @a"}]))
        self.assertEqual(errores, [])
        self.assertTrue(any("3-6" in a for a in avisos))
        self.assertEqual(g.escenas[0].clips_fuente[0].credito, "TikTok @a")
        self.assertEqual(len(g.fuentes_video), 1)

    def test_clips_fuente_url_invalida(self):
        _g, errores, _a = self._validar(self._guion([{"url": "ftp://nada", "duracion": 4}]))
        self.assertTrue(any("clips_fuente[0].url" in e for e in errores))


class TestRenderTomas(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "b_roll").mkdir()
        (self.tmp / "render").mkdir()
        self.p = SimpleNamespace(ruta=lambda *a: self.tmp.joinpath(*a), datos={"sin_host": False})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_panel_no_solapa_host(self):
        for pose in config.POSES:
            for lado in ("izquierda", "derecha"):
                cx, cy, w, h = geometria_panel(pose, lado, True)
                host = caja_host(pose, lado)
                if lado == "izquierda":
                    self.assertGreater(cx - w / 2, host.x2)
                else:
                    self.assertLess(cx + w / 2, host.x)

    def test_evidencia_y_montaje(self):
        raw = self.tmp / "raw.mp4"
        _clip(raw, 8, "blue", "360x640")  # vertical, como TikTok
        ev = self.tmp / "b_roll" / "escena_001_real_01.mp4"
        self.assertTrue(transformar_evidencia(raw, ev, 4.0, "TikTok @prueba", pose="duda", host_lado="izquierda"))
        self.assertAlmostEqual(_dur(ev), 4.0, delta=0.2)
        for n, col in (("escena_001.mp4", "red"), ("escena_001_t02.mp4", "green")):
            _clip(self.tmp / "b_roll" / n, 12, col)
        man = {"escena": 1, "tomas": [
            {"archivo": ev.name, "fuente": "real", "duracion": 4.0, "url": "https://x", "credito": "TikTok @prueba"},
            {"archivo": "escena_001.mp4", "fuente": "stock", "duracion_archivo": 12},
            {"archivo": "escena_001_t02.mp4", "fuente": "stock", "duracion_archivo": 12},
        ]}
        (self.tmp / "b_roll" / "escena_001_tomas.json").write_text(json.dumps(man), encoding="utf-8")
        esc = Escena(id=1, voz="x", pose="duda", clips_fuente=[ClipFuente(url="https://x")])
        out = montar_fondo_escena(self.p, esc, 13.0, self.tmp / "render" / "fondo.mp4")
        self.assertIsNotNone(out)
        self.assertAlmostEqual(_dur(out), 13.0, delta=0.25)
        segs = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(segs[0]["fuente"], "real")
        self.assertGreaterEqual(len(segs), 3)


if __name__ == "__main__":
    unittest.main()


class TestRespaldoDescarga(unittest.TestCase):
    def test_respaldo_sin_rango_si_falla_corte(self):
        """Si el corte por rango falla (p. ej. X/HLS), se reintenta descargando a temporal y recortando."""
        from unittest import mock
        import src.tomas as t
        llamadas = []

        class FakeYDL:
            def __init__(self, opts):
                self.opts = opts
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def extract_info(self, url, download=False):
                return {"duration": 57}
            def download(self, urls):
                llamadas.append("rango" if "download_ranges" in self.opts else "completo")
                destino = Path(self.opts["outtmpl"].replace("%(ext)s", "mp4"))
                if "download_ranges" in self.opts:
                    destino.write_bytes(b"x" * 261)  # archivo basura como el de X
                else:
                    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30", "-t", "10",
                                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(destino)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        with tempfile.TemporaryDirectory() as d, mock.patch("yt_dlp.YoutubeDL", FakeYDL):
            out = Path(d) / "frag.mp4"
            ok, err = t.descargar_fragmento_real("https://x.com/i/status/1", 3.0, 4.0, out)
            self.assertTrue(ok, err)
            self.assertEqual(llamadas, ["rango", "completo"])
            self.assertAlmostEqual(_dur(out), 4.0, delta=0.2)
            # El temporal completo no queda en disco: solo el fragmento
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["frag.mp4"])
