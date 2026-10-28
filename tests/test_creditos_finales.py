import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.creditos_finales as cf

CRED = [
    {"escena": 1, "tomas": [
        {"pagina": "https://commons.wikimedia.org/wiki/File:Grutas_de_Garc%C3%ADa_0804.jpg", "licencia": "CC BY-SA 4.0",
         "titulo": "Grutas de García 0804.jpg", "autor": "Phyrexian"},
        {"pagina": "https://pixabay.com/videos/id-1/", "licencia": "Pixabay Content License", "autor": "x / Pixabay"},
        {"pagina": "https://commons.wikimedia.org/wiki/File:Codex_Borgia_page_29.jpg", "licencia": "Public domain"},
        {"pagina": "https://commons.wikimedia.org/wiki/File:Mict.jpg", "licencia": "CC0"},
    ]},
    {"escena": 2, "tomas": [
        {"pagina": "https://commons.wikimedia.org/wiki/File:Grutas_de_Garc%C3%ADa_0804.jpg", "licencia": "CC BY-SA 4.0"},
        {"pagina": "https://commons.wikimedia.org/wiki/File:Xolo_sitting.jpg", "licencia": "CC BY 2.0", "autor": "Micyaotl"},
    ]},
]


def test_solo_cc_by_y_by_sa_sin_duplicados_en_orden():
    obras = cf.recolectar_obras(CRED)
    assert [o["licencia"] for o in obras] == ["CC BY-SA 4.0", "CC BY 2.0"]
    assert obras[0]["autor"] == "Phyrexian"
    assert obras[1]["titulo"] == "Xolo sitting.jpg"


def test_licencias():
    assert cf.requiere_atribucion("CC BY 3.0") and cf.requiere_atribucion("cc by-sa 2.0")
    for lic in ("CC0", "Public domain", "Dominio público (PD-Art)", "Pixabay Content License", ""):
        assert not cf.requiere_atribucion(lic)


def test_enlace_legible_decodifica():
    assert cf.enlace_legible("https://commons.wikimedia.org/wiki/File:Grutas_de_Garc%C3%ADa_0804.jpg") == \
        "commons.wikimedia.org/wiki/File:Grutas_de_García_0804.jpg"


def test_paginar():
    assert [len(g) for g in cf.paginar(list(range(20)), 9)] == [9, 9, 2]


def test_render_paginas_pngs(tmp_path):
    obras = [{"titulo": f"Obra {i} " + "x" * 200, "autor": "A", "licencia": "CC BY 4.0",
              "enlace": "https://commons.wikimedia.org/wiki/File:" + "y" * 90} for i in range(11)]
    rutas = cf.render_paginas(obras, tmp_path, ruta_fuente=Path("assets/fonts/bold.ttf"), por_pagina=9)
    assert len(rutas) == 2 and all(r.exists() for r in rutas)
    from PIL import Image
    with Image.open(rutas[0]) as im:
        assert im.size == (1920, 1080)


def _dur(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]))


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="requiere ffmpeg")
def test_anexar_creditos_finales_alarga_el_video(tmp_path):
    (tmp_path / "b_roll").mkdir()
    (tmp_path / "b_roll" / "creditos.json").write_text(json.dumps(CRED), "utf-8")
    video = tmp_path / "renders" / "v.mp4"
    video.parent.mkdir()
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=1920x1080:r=30:d=2", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=44100:duration=2", "-ac", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(video)], check=True, capture_output=True)
    p = SimpleNamespace(carpeta=tmp_path, ruta=lambda *a: tmp_path.joinpath(*a))
    tarjeta = cf.anexar_creditos_finales(p, [video], ffmpeg="ffmpeg",
                                         cfg={"creditos_finales": {"segundos_por_pagina": 1.5, "obras_por_pagina": 1}})
    assert tarjeta is not None and abs(_dur(tarjeta) - 3.0) < 0.2   # 2 obras x 1 página c/u x 1.5 s
    assert abs(_dur(video) - 5.0) < 0.3
    obras = json.loads((tmp_path / "renders" / "creditos_finales" / "obras.json").read_text("utf-8"))
    assert len(obras) == 2


def test_desactivado_no_toca_nada(tmp_path):
    p = SimpleNamespace(carpeta=tmp_path, ruta=lambda *a: tmp_path.joinpath(*a))
    assert cf.anexar_creditos_finales(p, [], ffmpeg="ffmpeg", cfg={"creditos_finales": {"enabled": False}}) is None


def _rms_db(f, ss=0.0, t=None):
    out = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(ss), *(["-t", str(t)] if t else []), "-i", str(f), "-af", "astats=measure_overall=RMS_level", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    vals = [l.split(":")[-1].strip() for l in out.splitlines() if "RMS level dB" in l]
    return float(vals[-1]) if vals and vals[-1] not in ("-inf", "inf") else float("-inf")


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="requiere ffmpeg")
def test_tarjeta_con_cama_musical_bajita(tmp_path):
    from PIL import Image
    pag = tmp_path / "p1.png"
    Image.new("RGB", (1920, 1080), "black").save(pag)
    musica = tmp_path / "m.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100:duration=1",
                    "-ac", "2", str(musica)], check=True)
    silencio = cf.video_desde_paginas([pag], tmp_path / "s.mp4", seg_por_pagina=4.0)
    con = cf.video_desde_paginas([pag], tmp_path / "c.mp4", seg_por_pagina=4.0, musica=musica, musica_volumen=0.12)
    assert _rms_db(silencio) == float("-inf") or _rms_db(silencio) < -80
    medio = _rms_db(con, ss=2.0, t=0.5)      # la pista dura 1 s: sólo suena aquí si va en bucle
    assert -50 < medio < -25                 # suena, y bajita (0.12 = -18 dB sobre la pista)
    assert abs(_dur(con) - 4.0) < 0.2


def test_clips_citados_de_redes_uno_por_publicacion():
    cred = [
        {"escena": 1, "tomas": [
            {"fuente": "real", "url": "https://www.tiktok.com/@a/video/1", "credito": "TikTok @a"},
            {"fuente": "stock", "url": "https://cdn.pixabay.com/x.mp4"},
        ]},
        {"escena": 2, "tomas": [
            {"fuente": "real", "url": "https://www.tiktok.com/@a/video/1/", "credito": "TikTok @a"},
            {"fuente": "real", "url": "https://x.com/b/status/2", "credito": "X @b"},
        ]},
    ]
    clips = cf.recolectar_clips_citados(cred)
    assert [c["autor"] for c in clips] == ["TikTok @a", "X @b"]
    assert all(c["licencia"] == cf.LICENCIA_CLIP_CITADO for c in clips)
    assert cf.recolectar_obras(cred) == []


def test_gfdl_tambien_pide_atribucion():
    assert cf.requiere_atribucion("GFDL 1.2") and cf.requiere_atribucion("GNU Free Documentation License 1.2")
    obras = cf.recolectar_obras([{"tomas": [{"licencia": "GFDL 1.2", "pagina": "https://commons.wikimedia.org/wiki/File:X.jpg", "autor": "Ralf Roletschek"}]}])
    assert len(obras) == 1 and obras[0]["licencia"] == "GFDL 1.2"
