"""Estilos de clips reales (evidencia/completo/dividido/congelado), recorte y realce de tomas oscuras."""
import subprocess
from pathlib import Path

import pytest

from src.tomas import ESTILOS_REALES, _filtro_previo, transformar_real
from src.guion import ClipFuente


def _clip(tmp: Path, brillo: str = "gray") -> Path:
    f = tmp / "raw.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={brillo}:s=360x640:d=4",
                    "-pix_fmt", "yuv420p", str(f)], check=True)
    return f


def test_schema_estilo_y_recorte():
    c = ClipFuente(url="https://x.com/i/status/1", estilo="dividido", recorte=[0, 0.1, 1, 0.5])
    assert c.estilo == "dividido" and c.recorte == [0, 0.1, 1, 0.5]
    assert ClipFuente(url="https://x.com/i/status/1").estilo == "evidencia"


def test_realce_oscuro_y_recorte():
    f = _filtro_previo([0, 0.25, 1, 0.5], 12.0, {"yavg_realce": 55})
    assert f.startswith("crop=") and "gamma=" in f
    assert _filtro_previo(None, 120.0, {"yavg_realce": 55}) == ""


@pytest.mark.parametrize("estilo", ESTILOS_REALES)
def test_transformar_estilos(tmp_path, estilo):
    raw = _clip(tmp_path)
    out = tmp_path / f"{estilo}.mp4"
    assert transformar_real(raw, out, 4.0, "TikTok @prueba", "EVIDENCIA", estilo, [0, 0.1, 1, 0.6],
                            "explicando", "izquierda", True, [0.2, 0.2, 0.4, 0.4])
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                               capture_output=True, text=True).stdout)
    assert abs(dur - 4.0) < 0.2
