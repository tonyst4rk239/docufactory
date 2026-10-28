import shutil
import subprocess

import pytest

import src.edicion as ed

requiere_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="requiere ffmpeg")


def _yavg_max(ruta):
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ruta), "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                          "-f", "null", "-"], capture_output=True, text=True, check=True).stdout
    return max(float(l.split("=")[1]) for l in out.splitlines() if "YAVG=" in l)


def test_36784_tiene_rango_por_defecto_y_config_lo_sobrescribe():
    assert ed.rango_util_overlay("glitch_pixabay_36784.mp4") == (0.1, 13.7)
    assert ed.rango_util_overlay("glitch_pixabay_27228.mp4") is None
    assert ed.rango_util_overlay("x.mp4", {"rangos_utiles": {"X.mp4": [1, 2]}}) == (1.0, 2.0)
    with pytest.raises(ValueError):
        ed.rango_util_overlay("x.mp4", {"rangos_utiles": {"x.mp4": [3, 2]}})


def test_sin_rango_devuelve_el_mismo_archivo(tmp_path):
    f = tmp_path / "glitch" / "limpio.mp4"
    f.parent.mkdir()
    f.write_bytes(b"0")
    assert ed.preparar_overlay_util(f) == f


@requiere_ffmpeg
def test_recorte_quita_el_destello_blanco(tmp_path):
    # overlay oscuro de 3 s con destello blanco en 0-0.1 s y desde 2.5 s (como 36784)
    src = tmp_path / "glitch" / "flash.mp4"
    src.parent.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x101010:s=320x180:r=30:d=3",
                    "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='lt(t,0.1)+gte(t,2.5)'",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    assert _yavg_max(src) > 200
    cfg = {"rangos_utiles": {"flash.mp4": [0.2, 2.4]}}
    out = ed.preparar_overlay_util(src, cfg, ffmpeg="ffmpeg")
    assert out != src and out.parent.name == "_recortes" and out.exists()
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)]))
    assert 2.0 <= dur <= 2.3
    assert _yavg_max(out) < 40
    assert ed.preparar_overlay_util(src, cfg, ffmpeg="ffmpeg") == out   # cacheado
    # el recorte queda fuera de las carpetas por tipo: no entra al pool
    assert out not in ed.listar_archivos_overlay(src.parent)


@requiere_ffmpeg
def test_36784_real_recortado_no_tiene_destello():
    from src import config
    src = config.OVERLAYS_DIR / "glitch" / "glitch_pixabay_36784.mp4"
    if not src.exists():
        pytest.skip("asset no presente")
    out = ed.preparar_overlay_util(src)
    assert _yavg_max(src) > 200 and _yavg_max(out) < 120
