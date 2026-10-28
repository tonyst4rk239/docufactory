"""Voz de Reels: Gemini Charon con respaldo Jorge, etiquetas [susurro]/[pausa corta] y caché por escena."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import config
from src.guion import _contar_palabras_habladas
from src.voz import limpiar_tags_ssml, preparar_texto_con_pausas
from src_tiktok import voz_gemini, voz_tt
from src_tiktok.guion_tt import GuionTikTok
from src_tiktok.render_tt import generar_subtitulos_vertical_ass

TEXTO = 'Los pescadores oían un grito: <break time="300ms"/> [susurro] ay, mis hijos. [pausa corta] Nadie sabía [Pausa] de dónde.'
FFMPEG = config.ffmpeg_bin("ffmpeg") or shutil.which("ffmpeg")


class _Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data


def _resp_429(cuota_id, retry="7s"):
    return _Resp(429, {"error": {"code": 429, "message": "Quota exceeded", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": cuota_id}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry},
    ]}})


def _resp_audio(segundos=1.0):
    import base64
    pcm = b"\x00\x00" * int(24000 * segundos)
    return _Resp(200, {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(pcm).decode()}}]}}]})


class _ProyectoFalso:
    def __init__(self, carpeta: Path):
        self.carpeta = carpeta
        self.datos = {"etapas": {}}

    def ruta(self, *partes):
        return self.carpeta.joinpath(*partes)

    def marcar(self, etapa, estado):
        self.datos["etapas"][etapa] = estado


def _guion(tono="misterio"):
    return GuionTikTok.model_validate({"titulo": "Prueba", "tono": tono, "escenas": [
        {"id": 1, "voz": "Algo camina en dos patas. [pausa corta] Y nadie lo explica."},
        {"id": 2, "voz": "[susurro] Dicen que vuelve cada noche."},
    ]})


def _mp3_silencio(destino: Path, segundos: float):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", f"{segundos}", "-c:a", "libmp3lame", str(destino)], check=True)


class TestEtiquetas(unittest.TestCase):
    def test_subtitulos_y_conteo_sin_etiquetas(self):
        limpio = limpiar_tags_ssml(TEXTO)
        self.assertNotIn("[", limpio)
        self.assertNotIn("susurro", limpio.lower())
        self.assertNotIn("pausa", limpio.lower())
        self.assertEqual(_contar_palabras_habladas(TEXTO), len(limpio.split()))

    def test_edge_no_lee_etiquetas(self):
        t = preparar_texto_con_pausas(TEXTO)
        self.assertNotIn("[", t)
        self.assertNotIn("susurro", t.lower())
        self.assertNotIn("pausa", t.lower())

    def test_gemini_conserva_solo_etiquetas_conocidas(self):
        t = voz_gemini.texto_para_gemini(TEXTO + " [risa] Fin.")
        self.assertIn("[susurro]", t)
        self.assertEqual(t.count("[pausa corta]"), 2)
        self.assertNotIn("risa", t)
        self.assertNotIn("<", t)

    def test_ass_vertical_sin_etiquetas(self):
        with tempfile.TemporaryDirectory() as d:
            p = _ProyectoFalso(Path(d))
            ruta = generar_subtitulos_vertical_ass(p, _guion(), {1: 3.0, 2: 2.0})
            contenido = ruta.read_text(encoding="utf-8").split("[Events]")[1]
            self.assertNotIn("SUSURRO", contenido)
            self.assertNotIn("PAUSA", contenido)
            self.assertIn("NOCHE", contenido)


class TestInstrucciones(unittest.TestCase):
    def test_tonos(self):
        for tono in ("misterio", "leyenda", "terror", "investigacion", "polemica", "controversia",
                     "humor", "epico", "drama", "curiosidad", "otro", None):
            ins = voz_gemini.instruccion_para_tono(tono)
            self.assertIn("Ritmo ágil", ins)
            self.assertIn("corchetes", ins)
        self.assertIn("grave y contenida", voz_gemini.instruccion_para_tono("leyenda"))
        self.assertIn("periodista", voz_gemini.instruccion_para_tono("investigacion"))
        self.assertIn("incisivo", voz_gemini.instruccion_para_tono("polemica"))
        self.assertIn("ligero", voz_gemini.instruccion_para_tono("humor"))
        self.assertIn("solemne", voz_gemini.instruccion_para_tono("epico"))

    def test_peticion(self):
        cuerpo = voz_gemini.armar_peticion("Hola [susurro] mundo", "misterio", "Charon")
        cfg = cuerpo["generationConfig"]
        self.assertEqual(cfg["responseModalities"], ["AUDIO"])
        self.assertEqual(cfg["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"], "Charon")
        self.assertTrue(cuerpo["contents"][0]["parts"][0]["text"].endswith("Hola [susurro] mundo"))


class TestPeticionGemini(unittest.TestCase):
    def setUp(self):
        self._clave = mock.patch.object(config, "GEMINI_API_KEY", "clave-falsa")
        self._clave.start()

    def tearDown(self):
        self._clave.stop()

    def test_cuota_diaria_es_cuota_agotada(self):
        post = mock.Mock(return_value=_resp_429("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
        with self.assertRaises(voz_gemini.GeminiCuotaAgotada):
            voz_gemini.pedir_pcm("hola", "misterio", post=post, dormir=lambda s: None)
        self.assertEqual(post.call_count, 1)

    def test_limite_por_minuto_espera_y_reintenta(self):
        esperas = []
        post = mock.Mock(side_effect=[_resp_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"), _resp_audio()])
        pcm = voz_gemini.pedir_pcm("hola", "misterio", post=post, dormir=esperas.append)
        self.assertEqual(len(pcm), 48000)
        self.assertEqual(esperas, [8.0])

    def test_limite_por_minuto_persistente(self):
        post = mock.Mock(return_value=_resp_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"))
        with self.assertRaises(voz_gemini.GeminiCuotaAgotada):
            voz_gemini.pedir_pcm("hola", "misterio", post=post, dormir=lambda s: None, reintentos_429=2)
        self.assertEqual(post.call_count, 3)

    def test_sin_clave(self):
        with mock.patch.object(config, "GEMINI_API_KEY", ""):
            with self.assertRaises(voz_gemini.GeminiTTSError):
                voz_gemini.pedir_pcm("hola", "misterio")

    @unittest.skipUnless(FFMPEG, "requiere ffmpeg")
    def test_recorta_pausas_largas(self):
        import base64
        import math
        tono = b"".join(int(8000 * math.sin(2 * math.pi * 220 * i / 24000)).to_bytes(2, "little", signed=True)
                        for i in range(24000))
        pcm = tono + b"\x00\x00" * (24000 * 3) + tono
        with tempfile.TemporaryDirectory() as d:
            dur = voz_gemini.pcm_a_mp3(pcm, Path(d) / "x.mp3")
        self.assertLess(dur, 2.8)  # 1 s + 3 s de silencio + 1 s -> la pausa queda en ~0.5 s
        self.assertGreater(dur, 2.2)


@unittest.skipUnless(FFMPEG, "requiere ffmpeg")
class TestEtapaVozReel(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.p = _ProyectoFalso(Path(self.dir.name))
        self.llamadas_gemini = []
        self.llamadas_edge = []

    def tearDown(self):
        self.dir.cleanup()

    def _gemini_ok(self, texto, tono, destino, voz="Charon"):
        self.llamadas_gemini.append((texto, tono, voz))
        _mp3_silencio(destino, 1.5)
        return 1.5

    def _edge(self, guion, carpeta, voz):
        self.llamadas_edge.append(voz)
        for e in guion.escenas:
            _mp3_silencio(carpeta / f"escena_{e.id:03d}.mp3", 1.0)

    def test_resolver(self):
        self.assertEqual(voz_tt.resolver_voz_reel("gemini:Charon"), voz_tt.VozReel("gemini", "Charon"))
        self.assertEqual(voz_tt.resolver_voz_reel("edge:es-MX-JorgeNeural"), voz_tt.VozReel("edge", "es-MX-JorgeNeural"))
        self.assertEqual(voz_tt.resolver_voz_reel("jorge"), voz_tt.VozReel("edge", "es-MX-JorgeNeural"))
        self.assertEqual(voz_tt.resolver_voz_reel("gemini"), voz_tt.VozReel("gemini", "Charon"))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VOZ_REEL", None)
            self.assertEqual(voz_tt.resolver_voz_reel(), voz_tt.VozReel("gemini", "Charon"))

    def test_gemini_y_cache_entre_preparar_y_renderizar(self):
        g = _guion("investigacion")
        with mock.patch.dict(os.environ, {"VOZ_REEL": "gemini:Charon"}):
            dur = voz_tt.etapa_voz_tiktok(self.p, g, sintetizar_gemini=self._gemini_ok, sintetizar_edge=self._edge)
            self.assertEqual(len(self.llamadas_gemini), 2)
            self.assertEqual({t for _, t, _ in self.llamadas_gemini}, {"investigacion"})
            self.assertAlmostEqual(dur[1], 1.5, delta=0.1)
            self.assertEqual(self.p.datos["voz_reel"]["voz"], "Charon")
            self.assertIsNone(self.p.datos["voz_reel"]["motivo_respaldo"])
            # Segunda pasada (renderizar): no gasta peticiones
            voz_tt.etapa_voz_tiktok(self.p, g, sintetizar_gemini=self._gemini_ok, sintetizar_edge=self._edge)
            self.assertEqual(len(self.llamadas_gemini), 2)
            # Cambia el texto de una escena -> se regenera
            g.escenas[1].voz = "Otro texto distinto."
            voz_tt.etapa_voz_tiktok(self.p, g, sintetizar_gemini=self._gemini_ok, sintetizar_edge=self._edge)
            self.assertEqual(len(self.llamadas_gemini), 4)
        self.assertEqual(self.llamadas_edge, [])
        self.assertIn("gemini:Charon", (self.p.carpeta / "voz" / "VOZ_USADA.txt").read_text(encoding="utf-8"))

    def test_respaldo_jorge_si_se_agota_la_cuota(self):
        def _falla_en_la_segunda(texto, tono, destino, voz="Charon"):
            if self.llamadas_gemini:
                raise voz_gemini.GeminiCuotaAgotada("429: cuota diaria del nivel gratis agotada")
            return self._gemini_ok(texto, tono, destino, voz)

        with mock.patch.dict(os.environ, {"VOZ_REEL": "gemini:Charon"}):
            voz_tt.etapa_voz_tiktok(self.p, _guion(), sintetizar_gemini=_falla_en_la_segunda, sintetizar_edge=self._edge)
        self.assertEqual(self.llamadas_edge, ["es-MX-JorgeNeural"])  # TODO el Reel con Jorge
        info = self.p.datos["voz_reel"]
        self.assertEqual((info["motor"], info["voz"]), ("edge", "es-MX-JorgeNeural"))
        self.assertIn("cuota agotada", info["motivo_respaldo"])
        self.assertIn("RESPALDO", (self.p.carpeta / "voz" / "VOZ_USADA.txt").read_text(encoding="utf-8"))

    def test_edge_directo(self):
        with mock.patch.dict(os.environ, {"VOZ_REEL": "edge:es-MX-JorgeNeural"}):
            voz_tt.etapa_voz_tiktok(self.p, _guion(), sintetizar_gemini=self._gemini_ok, sintetizar_edge=self._edge)
        self.assertEqual(self.llamadas_gemini, [])
        self.assertEqual(self.llamadas_edge, ["es-MX-JorgeNeural"])
        meta = json.loads((self.p.carpeta / "voz" / "voz_meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["motor"], "edge")


if __name__ == "__main__":
    unittest.main()
