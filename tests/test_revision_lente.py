"""Pruebas unitarias completas para la Tarea 6: Pausa de revisión de B-roll (Lente)."""
import json
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import unittest
from pathlib import Path

from src import config
from src.estado import Proyecto
from src.revision import (
    aplicar_revision_cli,
    extraer_cuadros_revision,
    formatear_resumen_revision,
    generar_revision_broll,
    obtener_metricas_visuales,
    obtener_resumen_revision,
    parsear_lista_escenas,
    parsear_rechazos,
    verificar_aprobacion,
)


class TestRevisionBroll(unittest.TestCase):
    def setUp(self):
        self.test_slug = "test_revision_lente"
        self.carpeta = config.PROYECTOS / f"video_{self.test_slug}"
        if self.carpeta.exists():
            shutil.rmtree(self.carpeta, ignore_errors=True)
        self.p = Proyecto.crear("Test Revision Lente", minutos=0.5, lang="es", reusar=False)

        # Crear guion simulado de 3 escenas
        guion_data = {
            "titulo_trabajo": "Test Revision Lente",
            "formato": "16:9",
            "top_n": 3,
            "escenas": [
                {
                    "id": 1,
                    "puesto": 3,
                    "voz": "Primera escena sobre un manuscrito antiguo.",
                    "broll_queries_en": ["ancient manuscript parchment", "library archive"],
                },
                {
                    "id": 2,
                    "puesto": 2,
                    "voz": "Segunda escena sobre un elevador abandonado en penumbra.",
                    "broll_queries_en": ["dark abandoned elevator shaft"],
                },
                {
                    "id": 3,
                    "puesto": 1,
                    "voz": "Tercera escena final sobre un faro en la niebla.",
                    "broll_queries_en": ["lighthouse in thick fog night"],
                },
            ],
        }
        (self.p.ruta("guion") / "guion.json").write_text(json.dumps(guion_data, ensure_ascii=False), encoding="utf-8")

        # Generar clips de video sintéticos mínimos con FFmpeg para simular b_roll/
        ffmpeg = config.ffmpeg_bin("ffmpeg") or "ffmpeg"
        for i in (1, 2, 3):
            clip = self.p.ruta("b_roll", f"escena_{i:03d}.mp4")
            cmd = [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", f"color=c=0x1e2538:s=640x360:d=2.0",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                str(clip)
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def tearDown(self):
        if self.carpeta.exists():
            shutil.rmtree(self.carpeta, ignore_errors=True)

    def test_parsear_listas_y_rechazos(self):
        self.assertEqual(parsear_lista_escenas("1,2,4", max_escenas=5), [1, 2, 4])
        self.assertEqual(parsear_lista_escenas("1-3", max_escenas=5), [1, 2, 3])
        self.assertEqual(parsear_lista_escenas("all", max_escenas=3), [1, 2, 3])

        rechazos = parsear_rechazos(['3:"escalera no elevador"', '1:"muy brillante"'])
        self.assertEqual(rechazos.get(3), "escalera no elevador")
        self.assertEqual(rechazos.get(1), "muy brillante")

    def test_generacion_cuadros_y_revision_json(self):
        items = generar_revision_broll(self.p, formato="16:9")
        self.assertEqual(len(items), 3)

        # Verificar archivo revision.json
        archivo_rev = self.p.ruta("b_roll", "revision.json")
        self.assertTrue(archivo_rev.exists())

        # Verificar los 3 cuadros JPG por escena
        for i in (1, 2, 3):
            inicio = self.p.ruta("b_roll", "revision", f"escena_{i:03d}_inicio.jpg")
            mitad = self.p.ruta("b_roll", "revision", f"escena_{i:03d}_mitad.jpg")
            final = self.p.ruta("b_roll", "revision", f"escena_{i:03d}_final.jpg")
            self.assertTrue(inicio.exists(), f"Falta cuadro inicio escena {i}")
            self.assertTrue(mitad.exists(), f"Falta cuadro mitad escena {i}")
            self.assertTrue(final.exists(), f"Falta cuadro final escena {i}")

        # Estado inicial debe ser 'pendiente'
        self.assertTrue(all(it["estado"] == "pendiente" for it in items))

    def test_verificacion_y_rechazo_render(self):
        generar_revision_broll(self.p, formato="16:9")

        # Sin aprobar, el render debe negarse
        aprobado, no_aprobadas = verificar_aprobacion(self.p, forzar=False)
        self.assertFalse(aprobado)
        self.assertEqual(len(no_aprobadas), 3)

        # Con forzar=True, debe permitirlo
        aprobado_forzado, _ = verificar_aprobacion(self.p, forzar=True)
        self.assertTrue(aprobado_forzado)

    def test_flujo_revisar_cli(self):
        generar_revision_broll(self.p, formato="16:9")

        # Aprobar escenas 1 y 2, y rechazar escena 3
        ok, salida = aplicar_revision_cli(
            self.p,
            aprobar="1,2",
            rechazar=['3:"escalera en vez de elevador"'],
            formato="16:9",
        )
        self.assertTrue(ok)

        # Verificar que el estado del proyecto se actualizó a 'revisar'
        self.assertEqual(self.p.estado("revision"), "revisar")

        # Verificar rechazo en renderizar
        aprobado, no_aprobadas = verificar_aprobacion(self.p, forzar=False)
        self.assertFalse(aprobado)
        self.assertEqual(len(no_aprobadas), 1)
        self.assertEqual(no_aprobadas[0]["escena"], 3)
        self.assertEqual(no_aprobadas[0]["motivo_rechazo"], "escalera en vez de elevador")

        # Aprobar escena 3
        ok, _ = aplicar_revision_cli(self.p, aprobar="3", formato="16:9")
        self.assertTrue(ok)
        self.assertEqual(self.p.estado("revision"), "ok")

        # Ahora sí debe aprobar el render
        aprobado_final, no_ap = verificar_aprobacion(self.p, forzar=False)
        self.assertTrue(aprobado_final)
        self.assertEqual(len(no_ap), 0)

    def test_formatear_resumen(self):
        generar_revision_broll(self.p, formato="16:9")
        aplicar_revision_cli(self.p, aprobar="1", rechazar=['2:"demasiado claro"'], formato="16:9")
        txt = formatear_resumen_revision(self.p)
        self.assertIn("APROBADO", txt)
        self.assertIn("RECHAZADO", txt)
        self.assertIn("PENDIENTE", txt)
        self.assertIn("demasiado claro", txt)


if __name__ == "__main__":
    unittest.main()
