import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts import metricas_semanales as m


class TestMetricasSemanales(unittest.TestCase):
    def test_duracion_iso(self):
        self.assertEqual(m.iso_duracion_a_s("PT9M44S"), 584)
        self.assertEqual(m.iso_duracion_a_s("PT1H2M"), 3720)
        self.assertEqual(m.iso_duracion_a_s("PT45S"), 45)
        self.assertEqual(m.iso_duracion_a_s("basura"), 0)

    def test_utc_a_merida(self):
        self.assertEqual(m.utc_a_merida("2026-10-23T20:45:32Z").strftime("%Y-%m-%d %H:%M"), "2026-10-23 14:45")

    def test_semana_anterior(self):
        self.assertEqual(m.semana_anterior(date(2026, 10, 26)), (date(2026, 10, 19), date(2026, 10, 25)))
        self.assertEqual(m.semana_anterior(date(2026, 11, 1)), (date(2026, 10, 19), date(2026, 10, 25)))

    def test_ssml(self):
        self.assertEqual(m.limpiar_ssml('Hola. <break time="400ms"/> Mundo'), "Hola. Mundo")

    def test_checkpoints_sin_inventar(self):
        c = m.evaluar_checkpoints(1, 103, None, date(2026, 10, 26))
        self.assertEqual(c["semana_de_prueba"], 1)
        self.assertFalse(c["semana4"]["subs_ok"])
        self.assertIsNone(c["semana4"]["max_reel_conocido"])
        self.assertIsInstance(c["semana8"]["subs_por_dia_actual"], str)  # desconocido, no 0
        self.assertTrue(m.evaluar_checkpoints(150, 1500, None, date(2026, 11, 16))["semana4"]["vistas_ok"])

    def test_inventario_y_emparejar(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "video_arca_20261023_0720"
            (d / "guion").mkdir(parents=True)
            (d / "proyecto.json").write_text(json.dumps({"formato": "16:9", "creado": "2026-10-23T07:20:18"}), encoding="utf-8")
            (d / "guion" / "guion.json").write_text(json.dumps({
                "titulo_trabajo": "Un robot bajó bajo el Arca de Noé", "tono": "misterio",
                "youtube_metadata": {"titulos": ['Un robot bajó bajo el "Arca de Noé"… esto es lo que encontraron']},
                "escenas": [{"id": 1, "voz": "x", "host_visible": True, "clips_fuente": [{"url": "u"}]}]}), encoding="utf-8")
            (Path(t) / "video_test_revision_lente_1").mkdir()
            inv = m.inventario(Path(t))
            self.assertEqual(len(inv), 1)
            self.assertEqual(inv[0]["clips_reales"], 1)
            self.assertEqual(inv[0]["usar_avatar"], "True (default)")
            it = m.emparejar('Un robot bajó bajo el "Arca de Noé"… esto es lo que encontraron (y lo que no)', inv)
            self.assertIsNotNone(it)
            self.assertIsNone(m.emparejar("Los Privilegios Ocultos de Diddy en Prisión", inv))

    def test_logs(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "upload.log").write_text(
                "🚀 PUBLICANDO VIDEO MULTI-PLATAFORMA\n📝 Título: La barrera\n🌐 Plataformas: FB, TT\n"
                "🔗 Enlace: https://www.facebook.com/reel/2666932750431288\n✅ ¡Video subido a TikTok con éxito!\n", encoding="utf-8")
            s = m.subidas_en_logs([Path(t)])
            self.assertEqual(s[0]["titulo"], "La barrera")
            self.assertEqual(s[0]["fb"], ["facebook.com/reel/2666932750431288"])
            self.assertTrue(s[0]["tiktok_ok"])


if __name__ == "__main__":
    unittest.main()
